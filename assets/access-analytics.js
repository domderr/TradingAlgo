(function () {
  "use strict";

  var STORAGE_KEY = "ta_access_analytics_queue";
  var SESSION_KEY = "ta_access_session_id";
  var ACCESS_KEY = "ta_reserved_authorized_markets";
  var DEFAULT_ENDPOINT = "";

  function nowIso() {
    return new Date().toISOString();
  }

  function uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "s-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
  }

  function sessionId() {
    var existing = sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    var created = uuid();
    sessionStorage.setItem(SESSION_KEY, created);
    return created;
  }

  function getStoredAccess() {
    try {
      return JSON.parse(sessionStorage.getItem(ACCESS_KEY) || "{}");
    } catch (error) {
      return {};
    }
  }

  function safePath(href) {
    try {
      var url = new URL(href, window.location.href);
      return url.pathname + url.search + url.hash;
    } catch (error) {
      return String(href || "");
    }
  }

  function basePayload(eventName, details) {
    var stored = getStoredAccess();
    return {
      event: eventName,
      occurred_at: nowIso(),
      site: "TradingAlgo",
      session_id: sessionId(),
      subscriber_id: stored.first_name || "",
      markets: Array.isArray(stored.markets) ? stored.markets : [],
      page_title: document.title || "",
      path: window.location.pathname,
      referrer: document.referrer || "",
      user_agent: navigator.userAgent || "",
      language: navigator.language || "",
      viewport: {
        width: window.innerWidth || 0,
        height: window.innerHeight || 0
      },
      details: details || {}
    };
  }

  function readQueue() {
    try {
      var queue = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
      return Array.isArray(queue) ? queue : [];
    } catch (error) {
      return [];
    }
  }

  function writeQueue(queue) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(queue.slice(-200)));
    } catch (error) {}
  }

  function endpoint() {
    return window.TA_ANALYTICS_ENDPOINT || DEFAULT_ENDPOINT;
  }

  function send(payload) {
    var url = endpoint();
    if (!url) {
      var queue = readQueue();
      queue.push(payload);
      writeQueue(queue);
      if (window.TA_ANALYTICS_DEBUG) console.info("TA analytics queued", payload);
      return;
    }

    var body = JSON.stringify(payload);
    if (navigator.sendBeacon) {
      var sent = navigator.sendBeacon(url, new Blob([body], { type: "text/plain;charset=UTF-8" }));
      if (sent) return;
    }

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=UTF-8" },
      body: body,
      keepalive: true
    }).catch(function () {
      var queue = readQueue();
      queue.push(payload);
      writeQueue(queue);
    });
  }

  function track(eventName, details) {
    send(basePayload(eventName, details));
  }

  function flushQueue() {
    if (!endpoint()) return;
    var queue = readQueue();
    if (!queue.length) return;
    writeQueue([]);
    queue.forEach(send);
  }

  function linkKind(anchor) {
    var href = anchor.getAttribute("href") || "";
    if (/\.pdf(?:[#?]|$)/i.test(href)) return "pdf";
    if (/reports_html\//i.test(href) || /Report_[^/]+\.html/i.test(href)) return "html_report";
    if (/^mailto:/i.test(href)) return "email";
    if (/^https?:\/\//i.test(href) && anchor.hostname !== window.location.hostname) return "outbound";
    return "internal";
  }

  function setupAutomaticTracking() {
    document.addEventListener("click", function (event) {
      var anchor = event.target && event.target.closest ? event.target.closest("a[href]") : null;
      if (!anchor) return;
      var kind = linkKind(anchor);
      if (kind === "internal") return;
      track("link_click", {
        kind: kind,
        href: safePath(anchor.href),
        label: (anchor.textContent || "").trim().slice(0, 120)
      });
    }, true);

    track("page_view", {});
    flushQueue();
  }

  window.TAAnalytics = {
    track: track,
    flushQueue: flushQueue
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupAutomaticTracking);
  } else {
    setupAutomaticTracking();
  }
}());
