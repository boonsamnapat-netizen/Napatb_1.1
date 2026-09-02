"""The approval state machine.

    photo ──▶ confirm product ──▶ confirm clip ──▶ choose link ──▶ final ──▶ deliver

Every transition is driven by an inline-keyboard tap or a text reply, and the
job state is persisted after each update so a scheduled runner can resume.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from . import products as prod
from . import script as scriptlib
from . import store as st
from . import video as videolib
from .telegram import Button, TelegramClient, Update, keyboard
from .vision import ProductVision

log = logging.getLogger(__name__)

HELP = (
    "🛒 <b>บอททำคลิปปักตะกร้า</b>\n\n"
    "1. ส่ง <b>รูปสินค้า</b> เข้ามาในแชทนี้\n"
    "2. ยืนยันว่าเจอสินค้าถูกตัว\n"
    "3. ตรวจคลิป 8 วิ แล้วกด OK\n"
    "4. เลือกลิงก์: ถูกสุด / ขายดีสุด / คอมเยอะสุด\n"
    "5. ยืนยันอีกครั้ง แล้วบอทส่งไฟล์ + แคปชั่นให้เอาไปโพสต์\n\n"
    "คำสั่ง: /start /status /cancel"
)

# Which callback actions each state will accept. Anything else is a stale tap
# (a double-click, or a scroll back to a message from a finished step) and is
# rejected — without this, tapping "make the clip" twice pays for two renders.
ALLOWED_ACTIONS: dict[str, set[str]] = {
    st.CONFIRM_PRODUCT: {"product_ok", "product_manual"},
    st.CONFIRM_VIDEO: {"video_ok", "video_retry"},
    st.CHOOSE_LINK: {"pick"},
    st.FINAL_CONFIRM: {"publish", "relink"},
}

STALE_TAP = "ขั้นตอนนี้ผ่านไปแล้วครับ"

MANUAL_PROMPT = (
    "🔎 <b>วิธีหาสินค้าที่แม่นที่สุด</b> — ใช้ค้นด้วยรูปในแอปเอง:\n"
    "• TikTok Shop → Creator Toolkit → Search by Image\n"
    "• Lazada → ไอคอนสแกน (Image Search, ใช้ได้ในแอปมือถือ)\n"
    "แล้วก๊อปลิงก์สินค้าที่เจอมาวางที่นี่ (บรรทัดละ 1 ลิงก์ ใส่ได้หลายอัน)\n\n"
    "อยากให้เทียบ ถูกสุด / ขายดีสุด / คอมเยอะสุด ให้ใส่ตัวเลขคั่นด้วย <code>|</code>:\n"
    "<code>ชื่อสินค้า | ลิงก์ | ราคา | ยอดขาย | คอม%</code>"
)


class Pipeline:
    """Handles one Telegram update at a time against the persisted job store."""

    def __init__(self, client: TelegramClient, store: st.JobStore,
                 config: dict[str, Any] | None = None):
        self.client = client
        self.store = store
        self.cfg = (config or {}).get("affiliate", config or {}) or {}
        self.work_dir = self.cfg.get("work_dir", "data/affiliate")
        self.allowed_user_ids = {int(u) for u in self.cfg.get("allowed_user_ids", []) or []}
        self.daily_render_limit = int(self.cfg.get("daily_render_limit", 50))
        self.vision = ProductVision(
            model=self.cfg.get("vision", {}).get("model", "claude-sonnet-4-6")
        )
        self.video_maker = videolib.make(self.cfg.get("video", {}))
        self.manual = prod.ManualFinder()
        self.finders = self._build_finders()

    def _build_finders(self) -> list[prod.ProductFinder]:
        finders: list[prod.ProductFinder] = []
        cfg = self.cfg.get("finders", {}) or {}
        if cfg.get("lazada", {}).get("enabled"):
            finders.append(prod.LazadaFinder(**_creds(cfg["lazada"])))
        if cfg.get("tiktok", {}).get("enabled"):
            finders.append(prod.TikTokFinder(**_creds(cfg["tiktok"])))
        for name in ("involve_asia", "accesstrade"):
            if cfg.get(name, {}).get("enabled"):
                entry = cfg[name]
                finders.append(prod.NetworkFinder(
                    name, api_key=str(entry.get("api_key", "")),
                    api_secret=str(entry.get("api_secret", "")),
                    endpoint=str(entry.get("endpoint", ""))))
        return finders

    # --- entry point -----------------------------------------------------

    def handle(self, update: Update) -> str:
        """Advance whatever the update refers to. Returns a log line."""
        if update.chat_id is None:
            return "ignored: no chat"
        if not self._permitted(update):
            self.client.send_message(
                update.chat_id,
                f"บอทนี้ใช้ได้เฉพาะเจ้าของครับ (user id ของคุณคือ <code>{update.user_id}</code>)")
            return f"denied: user {update.user_id}"
        try:
            if update.callback_data:
                return self._on_callback(update)
            if update.photo_file_id:
                return self._on_photo(update)
            if update.text:
                return self._on_text(update)
        except Exception as exc:  # one bad job must not stall the queue
            log.exception("update %s failed", update.update_id)
            self.client.send_message(update.chat_id, f"⚠️ เกิดข้อผิดพลาด: {exc}")
            return f"error: {exc}"
        return "ignored: nothing actionable"

    def _permitted(self, update: Update) -> bool:
        """An empty whitelist leaves the bot open — logged loudly, not silently."""
        if not self.allowed_user_ids:
            log.warning("allowed_user_ids is empty: anyone who finds this bot can "
                        "trigger a render. Set affiliate.allowed_user_ids.")
            return True
        return update.user_id in self.allowed_user_ids

    # --- inbound ---------------------------------------------------------

    def _on_photo(self, update: Update) -> str:
        job = self.store.create(update.chat_id, st.CONFIRM_PRODUCT)
        path = os.path.join(self.work_dir, job.id, "source.jpg")
        self.client.download_file(update.photo_file_id, path)
        job.photo_path = path

        described = self.vision.describe(path)
        job.query = described.query if described else (update.text or "").strip() or None
        benefit = described.benefit if described else None
        if benefit:
            job.script = {"benefit": benefit}

        candidates = self._search(job.query) if job.query else []
        job.candidates = [p.to_dict() for p in candidates]
        self.store.put(job)
        self.store.save()

        if candidates:
            self._ask_product(job, candidates)
            return f"job {job.id}: {len(candidates)} candidates"
        self.client.send_message(
            update.chat_id,
            (f"📷 รับรูปแล้ว (งาน <code>{job.id}</code>)\n"
             + (f"อ่านได้ว่า: <b>{job.query}</b>\n\n" if job.query else
                "อ่านชื่อสินค้าอัตโนมัติไม่ได้ (ยังไม่ได้ตั้ง ANTHROPIC_API_KEY)\n\n")
             + MANUAL_PROMPT),
        )
        return f"job {job.id}: awaiting manual links"

    def _on_text(self, update: Update) -> str:
        text = update.text.strip()
        lowered = text.lower()
        if lowered.startswith(("/start", "/help")):
            self.client.send_message(update.chat_id, HELP)
            return "help"
        if lowered.startswith("/status"):
            return self._status(update.chat_id)
        if lowered.startswith("/cancel"):
            return self._cancel(update.chat_id)

        job = self.store.active_for_chat(update.chat_id)
        if not job:
            self.client.send_message(update.chat_id, "ส่งรูปสินค้าเข้ามาก่อนนะครับ 📷")
            return "no active job"
        if job.state != st.CONFIRM_PRODUCT:
            self.client.send_message(update.chat_id,
                                     "ตอนนี้รอให้กดปุ่มด้านบนอยู่ครับ (หรือ /cancel)")
            return f"job {job.id}: text ignored in {job.state}"

        pasted = self.manual.parse(text)
        if pasted:
            job.candidates = [p.to_dict() for p in pasted]
            self.store.put(job)
            self.store.save()
            self._ask_product(job, pasted)
            return f"job {job.id}: {len(pasted)} manual candidates"

        # No links in the message — treat it as a corrected search query.
        job.query = text
        found = self._search(text)
        job.candidates = [p.to_dict() for p in found]
        self.store.put(job)
        self.store.save()
        if found:
            self._ask_product(job, found)
            return f"job {job.id}: {len(found)} candidates for '{text}'"
        self.client.send_message(update.chat_id,
                                 "ยังหาไม่เจอครับ " + MANUAL_PROMPT)
        return f"job {job.id}: no candidates for '{text}'"

    def _on_callback(self, update: Update) -> str:
        job_id, _, action = update.callback_data.partition(":")
        job = self.store.get(job_id)
        if update.callback_id:
            self.client.answer_callback(update.callback_id)
        if not job:
            self.client.send_message(update.chat_id, "งานนี้หมดอายุแล้ว ส่งรูปใหม่ได้เลยครับ")
            return "callback: unknown job"
        if not _action_allowed(job.state, action):
            if update.callback_id:
                self.client.answer_callback(update.callback_id, STALE_TAP)
            return f"job {job.id}: stale '{action}' in state {job.state}"
        # The step is being consumed now: take its keyboard away so the same
        # message cannot be tapped again while this run is still working.
        if update.message_id:
            self.client.clear_keyboard(update.chat_id, update.message_id)

        if action == "cancel":
            job.state = st.CANCELLED
            self.store.put(job)
            self.store.save()
            self.client.send_message(job.chat_id, f"❌ ยกเลิกงาน <code>{job.id}</code> แล้ว")
            return f"job {job.id}: cancelled"
        if action == "product_ok":
            return self._make_video(job)
        if action == "product_manual":
            job.state = st.CONFIRM_PRODUCT
            self.store.put(job)
            self.store.save()
            self.client.send_message(job.chat_id, MANUAL_PROMPT)
            return f"job {job.id}: manual link entry"
        if action == "video_retry":
            return self._make_video(job)
        if action == "video_ok":
            return self._ask_link(job)
        if action.startswith("pick:"):
            return self._on_pick(job, action.split(":", 1)[1])
        if action == "relink":
            return self._ask_link(job)
        if action == "publish":
            return self._deliver(job)
        return f"callback: unhandled action '{action}'"

    # --- steps -----------------------------------------------------------

    def _search(self, query: str | None) -> list[prod.Product]:
        if not query:
            return []
        found: list[prod.Product] = []
        for finder in self.finders:
            try:
                found.extend(finder.search(query))
            except prod.ProviderNotConfigured as exc:
                log.info("finder %s unavailable: %s", finder.name, exc)
            except Exception as exc:
                log.warning("finder %s failed: %s", finder.name, exc)
        return found

    def _ask_product(self, job: st.Job, candidates: list[prod.Product]) -> None:
        job.state = st.CONFIRM_PRODUCT
        self.store.put(job)
        self.store.save()
        listing = "\n\n".join(f"{i + 1}. {p.summary()}"
                              for i, p in enumerate(candidates[:5]))
        self.client.send_message(
            job.chat_id,
            f"🔍 เจอสินค้า {len(candidates)} รายการ:\n\n{listing}\n\nใช่สินค้านี้ไหมครับ?",
            keyboard(
                [Button("✅ ใช่ ทำคลิปเลย", f"{job.id}:product_ok")],
                [Button("✍️ ส่งลิงก์เอง", f"{job.id}:product_manual"),
                 Button("❌ ยกเลิก", f"{job.id}:cancel")],
            ),
        )

    def _make_video(self, job: st.Job) -> str:
        candidates = [prod.Product.from_dict(c) for c in job.candidates]
        anchor = candidates[0] if candidates else prod.Product(
            title=job.query or "สินค้า", url="")
        clip = scriptlib.build(anchor, benefit=(job.script or {}).get("benefit"))
        job.script = clip.to_dict()

        used = self.store.renders_today()
        if self.daily_render_limit and used >= self.daily_render_limit:
            self.store.put(job)
            self.store.save()
            self.client.send_message(
                job.chat_id,
                f"🛑 วันนี้เรนเดอร์ครบโควตาแล้ว ({used}/{self.daily_render_limit}) "
                "ลองใหม่พรุ่งนี้ หรือแก้ affiliate.daily_render_limit")
            return f"job {job.id}: daily render cap reached"
        # Counted before the call: a paid render that then fails still cost money.
        self.store.record_render()
        self.store.save()
        self.client.send_message(job.chat_id, "🎬 กำลังทำคลิป 8 วิ… รอสักครู่")
        out = os.path.join(self.work_dir, job.id, "clip.mp4")
        try:
            job.video_path = self.video_maker.render(job.photo_path, clip, out)
        except videolib.VideoError as exc:
            job.state = st.FAILED
            job.error = str(exc)
            self.store.put(job)
            self.store.save()
            self.client.send_message(job.chat_id, f"⚠️ ทำคลิปไม่สำเร็จ: {exc}")
            return f"job {job.id}: video failed"

        job.state = st.CONFIRM_VIDEO
        self.store.put(job)
        self.store.save()
        self.client.send_video(
            job.chat_id, job.video_path,
            caption="🎬 คลิป 8 วิ\n\n" + scriptlib.storyboard(clip),
            buttons=keyboard(
                [Button("✅ OK ใช้คลิปนี้", f"{job.id}:video_ok")],
                [Button("🔄 ทำใหม่", f"{job.id}:video_retry"),
                 Button("❌ ยกเลิก", f"{job.id}:cancel")],
            ),
        )
        return f"job {job.id}: video ready"

    def _ask_link(self, job: st.Job) -> str:
        candidates = [prod.Product.from_dict(c) for c in job.candidates]
        usable = prod.available_strategies(candidates)
        job.state = st.CHOOSE_LINK
        self.store.put(job)
        self.store.save()

        if not usable:
            # Nothing to rank on: fall through with whatever single link exists.
            if candidates:
                return self._on_pick(job, prod.CHEAPEST, fallback=candidates[0])
            self.client.send_message(job.chat_id,
                                     "ยังไม่มีลิงก์สินค้าเลยครับ " + MANUAL_PROMPT)
            job.state = st.CONFIRM_PRODUCT
            self.store.put(job)
            self.store.save()
            return f"job {job.id}: no links to choose"

        rows = [[Button(prod.STRATEGY_LABELS[s], f"{job.id}:pick:{s}")] for s in usable]
        rows.append([Button("❌ ยกเลิก", f"{job.id}:cancel")])
        missing = [prod.STRATEGY_LABELS[s] for s in prod.STRATEGY_LABELS if s not in usable]
        note = ("\n\n<i>ตัวเลือกที่ยังเลือกไม่ได้ (ไม่มีข้อมูล): "
                + ", ".join(missing) + "</i>") if missing else ""
        self.client.send_message(job.chat_id, "🔗 เลือกลิงก์ที่จะใช้:" + note,
                                 keyboard(*rows))
        return f"job {job.id}: awaiting link choice"

    def _on_pick(self, job: st.Job, strategy: str,
                 fallback: prod.Product | None = None) -> str:
        candidates = [prod.Product.from_dict(c) for c in job.candidates]
        chosen = prod.pick(candidates, strategy) or fallback
        if not chosen:
            self.client.send_message(job.chat_id, "ไม่มีข้อมูลพอสำหรับตัวเลือกนี้ครับ")
            return f"job {job.id}: strategy {strategy} unavailable"
        job.chosen = chosen.to_dict()
        job.strategy = strategy
        job.state = st.FINAL_CONFIRM
        self.store.put(job)
        self.store.save()
        self.client.send_message(job.chat_id, self._summary(job, chosen),
                                 keyboard(
                                     [Button("✅ ยืนยัน ส่งไฟล์ให้เลย",
                                             f"{job.id}:publish")],
                                     [Button("🔄 เปลี่ยนลิงก์", f"{job.id}:relink"),
                                      Button("❌ ยกเลิก", f"{job.id}:cancel")],
                                 ))
        return f"job {job.id}: awaiting final confirm ({strategy})"

    def _summary(self, job: st.Job, chosen: prod.Product) -> str:
        clip = scriptlib.ClipScript.from_dict(job.script or {})
        candidates = [prod.Product.from_dict(c) for c in job.candidates]
        caveat = ""
        if job.strategy == prod.TOP_COMMISSION and prod.commission_is_flat(candidates):
            caveat = ("\n<i>⚠️ ทุกตัวคอม % เท่ากัน — อันนี้เลยกลายเป็น "
                      "\"ราคาแพงสุด\" ไม่ใช่ \"คอมเยอะสุด\" จริง ๆ</i>")
        return "\n".join([
            "🧾 <b>ตรวจครั้งสุดท้าย</b>",
            "",
            f"🔗 ลิงก์ ({prod.STRATEGY_LABELS.get(job.strategy, job.strategy)}):"
            + caveat,
            chosen.summary(),
            "",
            "📝 แคปชั่น:",
            f"<code>{clip.caption}</code>",
            "",
            " ".join(clip.hashtags),
            "",
            "กดยืนยันแล้วบอทจะส่งไฟล์คลิป + แคปชั่นให้เอาไปโพสต์เอง",
        ])

    def _deliver(self, job: st.Job) -> str:
        clip = scriptlib.ClipScript.from_dict(job.script or {})
        chosen = prod.Product.from_dict(job.chosen or {})
        job.state = st.DELIVERED
        self.store.put(job)
        self.store.save()
        if job.video_path and os.path.exists(job.video_path):
            self.client.send_document(job.chat_id, job.video_path,
                                      caption="✅ ไฟล์คลิปพร้อมโพสต์")
        # Caption sent separately and unformatted so it can be copied in one tap.
        self.client.send_message(
            job.chat_id,
            "📋 ก็อปแคปชั่นนี้ไปวางได้เลย:\n\n"
            f"<code>{clip.caption}\n\n{' '.join(clip.hashtags)}</code>\n\n"
            f"🔗 ลิงก์ปักตะกร้า: {chosen.url}",
        )
        return f"job {job.id}: delivered"

    # --- commands --------------------------------------------------------

    def _status(self, chat_id: int) -> str:
        job = self.store.active_for_chat(chat_id)
        if not job:
            self.client.send_message(chat_id, "ตอนนี้ไม่มีงานค้างครับ ส่งรูปได้เลย 📷")
            return "status: idle"
        self.client.send_message(
            chat_id, f"งาน <code>{job.id}</code> — สถานะ: <b>{job.state}</b>")
        return f"status: {job.id} {job.state}"

    def _cancel(self, chat_id: int) -> str:
        job = self.store.active_for_chat(chat_id)
        if not job:
            self.client.send_message(chat_id, "ไม่มีงานให้ยกเลิกครับ")
            return "cancel: nothing"
        job.state = st.CANCELLED
        self.store.put(job)
        self.store.save()
        self.client.send_message(chat_id, f"❌ ยกเลิกงาน <code>{job.id}</code> แล้ว")
        return f"job {job.id}: cancelled"


def _action_allowed(state: str, action: str) -> bool:
    """Cancelling is always fine; every other action must match the state."""
    if state in st.TERMINAL:
        return False
    if action == "cancel":
        return True
    return action.split(":", 1)[0] in ALLOWED_ACTIONS.get(state, set())


def _creds(cfg: dict[str, Any]) -> dict[str, str]:
    return {k: str(cfg.get(k, "")) for k in ("app_key", "app_secret", "endpoint")}


def drain(client: TelegramClient, store: st.JobStore, pipeline: Pipeline,
          limit: int = 50, poll_timeout: int = 0) -> list[str]:
    """Process every pending update once, advancing the stored offset."""
    updates = client.get_updates(offset=store.offset or None, limit=limit,
                                 poll_timeout=poll_timeout)
    results = []
    for update in updates:
        results.append(pipeline.handle(update))
        # Advance past this update even if it failed, so it cannot loop forever.
        store.offset = update.update_id + 1
        store.save()
    return results
