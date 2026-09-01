"""End-to-end tests for the affiliate clip pipeline, with a fake Telegram."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.affiliate import products as prod
from src.affiliate import script as scriptlib
from src.affiliate import store as st
from src.affiliate import video as videolib
from src.affiliate.pipeline import Pipeline
from src.affiliate.telegram import Update


class FakeClient:
    """Records everything the pipeline sends and fakes photo downloads."""

    def __init__(self):
        self.messages: list[tuple[int, str, dict | None]] = []
        self.videos: list[str] = []
        self.documents: list[str] = []
        self.answered: list[str] = []

    def send_message(self, chat_id, text, buttons=None):
        self.messages.append((chat_id, text, buttons))
        return {"message_id": len(self.messages)}

    def send_video(self, chat_id, path, caption="", buttons=None):
        self.videos.append(path)
        self.messages.append((chat_id, caption, buttons))
        return {"message_id": len(self.messages)}

    def send_document(self, chat_id, path, caption=""):
        self.documents.append(path)
        return {"message_id": len(self.messages)}

    def answer_callback(self, callback_id, text=""):
        self.answered.append(callback_id)

    def download_file(self, file_id, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(b"fake-jpeg-bytes")
        return dest

    # --- assertions helpers ---
    def last_text(self) -> str:
        return self.messages[-1][1] if self.messages else ""

    def buttons(self) -> list[str]:
        """callback_data of every button on the most recent message."""
        markup = self.messages[-1][2] if self.messages else None
        if not markup:
            return []
        return [b["callback_data"] for row in markup["inline_keyboard"] for b in row]


class StubVideoMaker:
    name = "stub"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def render(self, image_path, script, out_path):
        self.calls += 1
        if self.fail:
            raise videolib.VideoError("stub failure")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(b"fake-mp4")
        return out_path


def photo_update(update_id=1, chat_id=7):
    return Update(update_id=update_id, chat_id=chat_id, photo_file_id="file-1")


def text_update(text, update_id=2, chat_id=7):
    return Update(update_id=update_id, chat_id=chat_id, text=text)


def tap(data, update_id=3, chat_id=7):
    return Update(update_id=update_id, chat_id=chat_id, callback_data=data,
                  callback_id="cb")


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = FakeClient()
        self.store = st.JobStore(os.path.join(self.tmp.name, "state.json"))
        self.pipeline = Pipeline(self.client, self.store, {
            "affiliate": {"work_dir": os.path.join(self.tmp.name, "jobs")}
        })
        self.pipeline.video_maker = StubVideoMaker()
        # No API key in tests: the bot must fall back to manual entry.
        self.pipeline.vision.api_key = ""

    def job(self) -> st.Job:
        job = self.store.active_for_chat(7)
        self.assertIsNotNone(job)
        return job

    # --- the happy path --------------------------------------------------

    def test_full_flow_photo_to_delivery(self):
        self.pipeline.handle(photo_update())
        job = self.job()
        self.assertEqual(job.state, st.CONFIRM_PRODUCT)
        self.assertIn("ลิงก์สินค้า", self.client.last_text())

        self.pipeline.handle(text_update(
            "กระติกน้ำ A | https://lazada.co.th/a | 199 | 1200 | 8\n"
            "กระติกน้ำ B | https://lazada.co.th/b | 149 | 300 | 15"
        ))
        self.assertEqual(len(self.job().candidates), 2)
        self.assertIn(f"{self.job().id}:product_ok", self.client.buttons())

        self.pipeline.handle(tap(f"{self.job().id}:product_ok"))
        self.assertEqual(self.job().state, st.CONFIRM_VIDEO)
        self.assertEqual(len(self.client.videos), 1)

        self.pipeline.handle(tap(f"{self.job().id}:video_ok"))
        self.assertEqual(self.job().state, st.CHOOSE_LINK)
        self.assertIn(f"{self.job().id}:pick:cheapest", self.client.buttons())

        self.pipeline.handle(tap(f"{self.job().id}:pick:top_commission"))
        job = self.job()
        self.assertEqual(job.state, st.FINAL_CONFIRM)
        # B earns 149*15% = 22.35 vs A's 199*8% = 15.92.
        self.assertEqual(job.chosen["url"], "https://lazada.co.th/b")

        self.pipeline.handle(tap(f"{job.id}:publish"))
        self.assertEqual(self.store.get(job.id).state, st.DELIVERED)
        self.assertEqual(len(self.client.documents), 1)

    def test_cheapest_and_best_selling_pick_different_links(self):
        self.pipeline.handle(photo_update())
        self.pipeline.handle(text_update(
            "A | https://x.test/a | 199 | 1200 | 8\nB | https://x.test/b | 149 | 300 | 15"
        ))
        job_id = self.job().id
        self.pipeline.handle(tap(f"{job_id}:product_ok"))
        self.pipeline.handle(tap(f"{job_id}:video_ok"))

        self.pipeline.handle(tap(f"{job_id}:pick:cheapest"))
        self.assertEqual(self.store.get(job_id).chosen["url"], "https://x.test/b")

        self.pipeline.handle(tap(f"{job_id}:relink"))
        self.pipeline.handle(tap(f"{job_id}:pick:best_selling"))
        self.assertEqual(self.store.get(job_id).chosen["url"], "https://x.test/a")

    # --- guard rails -----------------------------------------------------

    def test_bare_urls_need_no_metadata_and_skip_the_chooser(self):
        self.pipeline.handle(photo_update())
        self.pipeline.handle(text_update("https://lazada.co.th/only"))
        job_id = self.job().id
        self.pipeline.handle(tap(f"{job_id}:product_ok"))
        self.pipeline.handle(tap(f"{job_id}:video_ok"))
        job = self.store.get(job_id)
        self.assertEqual(job.state, st.FINAL_CONFIRM)
        self.assertEqual(job.chosen["url"], "https://lazada.co.th/only")

    def test_video_failure_marks_job_failed_and_tells_the_user(self):
        self.pipeline.video_maker = StubVideoMaker(fail=True)
        self.pipeline.handle(photo_update())
        self.pipeline.handle(text_update("https://x.test/a"))
        job_id = self.job().id if self.job() else None
        self.pipeline.handle(tap(f"{job_id}:product_ok"))
        self.assertEqual(self.store.get(job_id).state, st.FAILED)
        self.assertIn("ทำคลิปไม่สำเร็จ", self.client.last_text())

    def test_retry_rerenders_the_clip(self):
        self.pipeline.handle(photo_update())
        self.pipeline.handle(text_update("https://x.test/a"))
        job_id = self.job().id
        self.pipeline.handle(tap(f"{job_id}:product_ok"))
        self.pipeline.handle(tap(f"{job_id}:video_retry"))
        self.assertEqual(self.pipeline.video_maker.calls, 2)

    def test_cancel_stops_the_job(self):
        self.pipeline.handle(photo_update())
        job_id = self.job().id
        self.pipeline.handle(tap(f"{job_id}:cancel"))
        self.assertEqual(self.store.get(job_id).state, st.CANCELLED)
        self.assertIsNone(self.store.active_for_chat(7))

    def test_unknown_job_does_not_crash(self):
        self.assertEqual(self.pipeline.handle(tap("deadbeef:publish")),
                         "callback: unknown job")

    def test_text_before_any_photo_asks_for_one(self):
        self.pipeline.handle(text_update("มีอะไรขายบ้าง"))
        self.assertIn("ส่งรูปสินค้า", self.client.last_text())


class ProductPickTest(unittest.TestCase):
    def setUp(self):
        self.items = [
            prod.Product(title="A", url="a", price=199, sold=1200, commission_pct=8),
            prod.Product(title="B", url="b", price=149, sold=300, commission_pct=15),
            prod.Product(title="C", url="c"),
        ]

    def test_strategies(self):
        self.assertEqual(prod.pick(self.items, prod.CHEAPEST).url, "b")
        self.assertEqual(prod.pick(self.items, prod.BEST_SELLING).url, "a")
        self.assertEqual(prod.pick(self.items, prod.TOP_COMMISSION).url, "b")

    def test_commission_ranks_by_baht_not_headline_pct(self):
        items = [
            prod.Product(title="cheap high %", url="a", price=100, commission_pct=20),
            prod.Product(title="pricey low %", url="b", price=1000, commission_pct=5),
        ]
        self.assertEqual(prod.pick(items, prod.TOP_COMMISSION).url, "b")

    def test_strategy_unavailable_without_data(self):
        bare = [prod.Product(title="C", url="c")]
        self.assertIsNone(prod.pick(bare, prod.CHEAPEST))
        self.assertEqual(prod.available_strategies(bare), [])
        self.assertEqual(len(prod.available_strategies(self.items)), 3)

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            prod.pick(self.items, "random")


class ManualParseTest(unittest.TestCase):
    def setUp(self):
        self.finder = prod.ManualFinder()

    def test_bare_url(self):
        [item] = self.finder.parse("https://www.lazada.co.th/products/x-i123.html")
        self.assertEqual(item.platform, "lazada")
        self.assertIsNone(item.price)

    def test_pipe_fields_and_thousands_separator(self):
        [item] = self.finder.parse("หูฟัง XM5 | https://x.test/p | 1,290 | 4,500 | 12.5")
        self.assertEqual(item.title, "หูฟัง XM5")
        self.assertEqual(item.price, 1290.0)
        self.assertEqual(item.sold, 4500)
        self.assertEqual(item.commission_pct, 12.5)

    def test_lines_without_links_are_dropped(self):
        self.assertEqual(self.finder.parse("อยากได้กระติกน้ำ\n/cancel"), [])


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "state.json")

    def test_roundtrip_and_offset(self):
        store = st.JobStore(self.path)
        job = store.create(7, st.CONFIRM_PRODUCT, query="กระติกน้ำ")
        store.offset = 42
        store.save()

        reloaded = st.JobStore(self.path)
        self.assertEqual(reloaded.offset, 42)
        self.assertEqual(reloaded.get(job.id).query, "กระติกน้ำ")

    def test_corrupt_state_does_not_raise(self):
        with open(self.path, "w") as fh:
            fh.write("{not json")
        self.assertEqual(st.JobStore(self.path).offset, 0)

    def test_prune_only_removes_old_terminal_jobs(self):
        store = st.JobStore(self.path)
        live = store.create(7, st.CONFIRM_VIDEO)
        old = store.create(7, st.DELIVERED)
        old.updated_at = 0
        store._data["jobs"][old.id]["updated_at"] = 0
        self.assertEqual(store.prune(), 1)
        self.assertIsNotNone(store.get(live.id))
        self.assertIsNone(store.get(old.id))

    def test_state_file_is_utf8_readable(self):
        store = st.JobStore(self.path)
        store.create(7, st.CONFIRM_PRODUCT, query="กระติกน้ำเก็บความเย็น")
        store.save()
        with open(self.path, encoding="utf-8") as fh:
            self.assertIn("กระติกน้ำ", json.load(fh)["jobs"].popitem()[1]["query"])


class ScriptTest(unittest.TestCase):
    def test_beats_cover_exactly_eight_seconds(self):
        clip = scriptlib.build(prod.Product(title="กระติกน้ำ", url="x", price=199))
        lines = clip.lines()
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[0][0], 0.0)
        self.assertEqual(lines[-1][1], 8.0)
        for (_, end, _), (start, _, _) in zip(lines, lines[1:]):
            self.assertEqual(end, start)  # no gaps between beats

    def test_price_line_falls_back_without_a_price(self):
        clip = scriptlib.build(prod.Product(title="x", url="y"))
        self.assertEqual(clip.price, "ราคาในตะกร้า")

    def test_caption_avoids_the_downranked_phrase(self):
        clip = scriptlib.build(prod.Product(title="x", url="y", price=99))
        self.assertNotIn("ลิงก์ในไบโอ", clip.caption)
        self.assertIn("กดตะกร้า", clip.caption)

    def test_hashtags_are_unique(self):
        tags = scriptlib.hashtags(prod.Product(title="Anker Anker", url="y"),
                                 extra=["ของมันต้องมี", "#ติดตะกร้า"])
        self.assertEqual(len(tags), len(set(tags)))

    def test_thai_hashtags_keep_vowel_and_tone_marks(self):
        tags = scriptlib.hashtags(prod.Product(title="ตัวอย่างสินค้า", url="y"))
        self.assertIn("#ตัวอย่างสินค้า", tags)

    def test_hashtags_drop_punctuation(self):
        tags = scriptlib.hashtags(prod.Product(title="XM-5 (ของแท้)", url="y"))
        self.assertIn("#XM5", tags)

    def test_script_survives_a_store_roundtrip(self):
        clip = scriptlib.build(prod.Product(title="กระติก", url="y", price=250))
        self.assertEqual(scriptlib.ClipScript.from_dict(clip.to_dict()).caption,
                         clip.caption)


class VideoConfigTest(unittest.TestCase):
    def test_ai_without_endpoint_falls_back_to_ffmpeg(self):
        maker = videolib.make({"provider": "ai", "ai": {"submit_url": ""}})
        self.assertEqual(maker.name, "ffmpeg")

    def test_ai_with_endpoint_is_selected(self):
        maker = videolib.make({"provider": "ai",
                               "ai": {"submit_url": "https://api.test/v1/video"}})
        self.assertEqual(maker.name, "ai")

    def test_env_vars_expand_in_headers_and_urls(self):
        os.environ["AFFILIATE_TEST_KEY"] = "secret-123"
        self.addCleanup(os.environ.pop, "AFFILIATE_TEST_KEY", None)
        maker = videolib.AIVideoMaker({
            "submit_url": "https://api.test/v1",
            "headers": {"Authorization": "Bearer ${AFFILIATE_TEST_KEY}"},
        })
        self.assertEqual(maker._headers()["Authorization"], "Bearer secret-123")

    def test_result_path_digs_through_lists(self):
        payload = {"data": {"output": [{"url": "https://cdn.test/a.mp4"}]}}
        self.assertEqual(videolib._dig(payload, "data.output.0.url"),
                         "https://cdn.test/a.mp4")
        self.assertIsNone(videolib._dig(payload, "data.missing.url"))

    def test_payload_placeholders_are_filled(self):
        filled = videolib._fill({"image": "{image_b64}", "n": 8, "p": "{prompt}"},
                                {"image_b64": "AAA", "prompt": "hi"})
        self.assertEqual(filled, {"image": "AAA", "n": 8, "p": "hi"})

    def test_drawtext_escaping(self):
        self.assertEqual(videolib._escape("199:- ,ok"), "199\\:- \\,ok")

    def test_thai_text_is_not_burned_with_a_non_thai_font(self):
        maker = videolib.FfmpegVideoMaker(font_path="/usr/share/fonts/DejaVuSans.ttf")
        clip = scriptlib.build(prod.Product(title="กระติกน้ำ", url="y", price=199))
        self.assertEqual(maker._text_filters(clip), [])

    def test_thai_text_is_burned_with_a_thai_font(self):
        maker = videolib.FfmpegVideoMaker(font_path="/usr/share/fonts/tlwg/Loma.ttf")
        clip = scriptlib.build(prod.Product(title="กระติกน้ำ", url="y", price=199))
        self.assertEqual(len(maker._text_filters(clip)), 4)

    def test_ffmpeg_reports_a_missing_source_image(self):
        maker = videolib.FfmpegVideoMaker(burn_text=False)
        clip = scriptlib.build(prod.Product(title="x", url="y"))
        with self.assertRaises(videolib.VideoError):
            maker.render("/nonexistent/image.jpg", clip, "/tmp/out.mp4")


if __name__ == "__main__":
    unittest.main(verbosity=2)
