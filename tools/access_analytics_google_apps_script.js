var SHEET_NAME = "access_events";

function doPost(e) {
  var sheet = getSheet_();
  var payload = parsePayload_(e);

  sheet.appendRow([
    new Date(),
    payload.occurred_at || "",
    payload.event || "",
    payload.site || "",
    payload.session_id || "",
    payload.subscriber_id || "",
    (payload.markets || []).join(", "),
    payload.page_title || "",
    payload.path || "",
    payload.referrer || "",
    payload.language || "",
    payload.user_agent || "",
    JSON.stringify(payload.viewport || {}),
    JSON.stringify(payload.details || {})
  ]);

  return ContentService
    .createTextOutput(JSON.stringify({ ok: true }))
    .setMimeType(ContentService.MimeType.JSON);
}

function getSheet_() {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
    sheet.appendRow([
      "received_at",
      "occurred_at",
      "event",
      "site",
      "session_id",
      "subscriber_id",
      "markets",
      "page_title",
      "path",
      "referrer",
      "language",
      "user_agent",
      "viewport",
      "details"
    ]);
  }
  return sheet;
}

function parsePayload_(e) {
  try {
    return JSON.parse(e.postData.contents || "{}");
  } catch (error) {
    return {};
  }
}
