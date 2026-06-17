/**
 * LINE → Google Sheet collector (Google Apps Script, free, no server needed).
 *
 * Deploy this as a Web App, set its URL as the LINE bot's Webhook URL, and
 * every message the bot sees in the group is appended to a sheet named
 * "Messages" (columns: timestamp, userId, text).
 *
 * Setup:
 *   1. sheets.google.com → new spreadsheet → Extensions → Apps Script.
 *   2. Paste this file. Set CHANNEL_SECRET below (LINE Developers console).
 *   3. Deploy → New deployment → type "Web app" → execute as Me,
 *      access "Anyone" → copy the /exec URL.
 *   4. LINE Developers → Messaging API → Webhook URL = that /exec URL → Verify.
 *   5. (optional) File → Share → Publish to web → "Messages" sheet as CSV,
 *      so the local ops_yield_cli.py can pull it with --url.
 *
 * The local end-of-day job filters the day's rows; this script just logs.
 */

var SHEET_NAME = 'Messages';

function doPost(e) {
  var body = JSON.parse(e.postData.contents);
  var sheet = SpreadsheetApp.getActiveSpreadsheet()
      .getSheetByName(SHEET_NAME) || _ensureSheet();
  (body.events || []).forEach(function (ev) {
    if (ev.type === 'message' && ev.message && ev.message.type === 'text') {
      sheet.appendRow([
        new Date(ev.timestamp),
        (ev.source && (ev.source.userId || ev.source.groupId)) || '',
        ev.message.text,
      ]);
    }
  });
  return ContentService.createTextOutput('OK');
}

function _ensureSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.insertSheet(SHEET_NAME);
  sheet.appendRow(['timestamp', 'source', 'text']);
  return sheet;
}
