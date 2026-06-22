# Access analytics

The site includes `assets/access-analytics.js` on public pages, the reserved area, and generated HTML reports.

## What is tracked

- `page_view`: page title, path, referrer, viewport, language, user agent.
- `link_click`: PDF/report/email/outbound links.
- `access_granted`: successful reserved-area password access.
- `access_denied`: invalid password or valid password with no enabled markets.
- `access_restored`: reserved-area session restored from browser session storage.

The tracker does not send passwords. It only attaches the subscriber display ID already stored in the browser session and the enabled market list.

## Enable collection

Set an HTTPS endpoint in one of two ways.

Option A: edit `assets/access-analytics.js` and set:

```js
var DEFAULT_ENDPOINT = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec";
```

Option B: set it before `access-analytics.js` loads on a page:

```html
<script>
  window.TA_ANALYTICS_ENDPOINT = "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec";
</script>
<script defer src="assets/access-analytics.js"></script>
```

If no endpoint is configured, events are queued locally in `localStorage` under `ta_access_analytics_queue`.

## Exclude your browser

Open the site once with `?ta_no_track=1` to stop analytics from the current browser:

```text
https://tradingalgo.it/?ta_no_track=1
```

Open it once with `?ta_track=1` to enable analytics again for the current browser:

```text
https://tradingalgo.it/?ta_track=1
```

## Google Sheets receiver

Use `tools/access_analytics_google_apps_script.js` as a Google Apps Script Web App receiver.

Deploy it as:

1. Execute as: `Me`.
2. Who has access: `Anyone`.
3. Copy the `/exec` URL into `window.TA_ANALYTICS_ENDPOINT`.
