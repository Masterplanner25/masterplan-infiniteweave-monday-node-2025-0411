import { reportClientVitals } from "../api/operator.js";

const SESSION_ID = Math.random().toString(36).slice(2);
const _vitals = { lcp_ms: null, cls_score: null, inp_ms: null };
let _sendScheduled = false;

function sendVitals(metrics) {
  if (!metrics.lcp_ms && !metrics.cls_score && !metrics.inp_ms) return;
  reportClientVitals({
    ...metrics,
    route: window.location.pathname,
    session_id: SESSION_ID,
  });
}

function _scheduleSend() {
  if (_sendScheduled) return;
  _sendScheduled = true;
  setTimeout(() => {
    sendVitals(_vitals);
    _sendScheduled = false;
  }, 10_000);
}

export function initVitals() {
  if (typeof window === "undefined" || typeof PerformanceObserver === "undefined") return;

  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1];
      if (last) {
        _vitals.lcp_ms = Math.round(last.startTime);
        _scheduleSend();
      }
    }).observe({ type: "largest-contentful-paint", buffered: true });
  } catch {}

  try {
    let clsScore = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) {
          clsScore += entry.value;
        }
      }
      _vitals.cls_score = Math.round(clsScore * 1000) / 1000;
      _scheduleSend();
    }).observe({ type: "layout-shift", buffered: true });
  } catch {}

  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.duration > (_vitals.inp_ms || 0)) {
          _vitals.inp_ms = Math.round(entry.duration);
        }
      }
      _scheduleSend();
    }).observe({ type: "event", buffered: true, durationThreshold: 40 });
  } catch {}
}
