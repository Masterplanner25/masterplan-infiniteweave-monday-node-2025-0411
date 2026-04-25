import { getStoredToken } from "../api/_core.js";
import { reportClientError } from "../api/operator.js";

let _isInstalled = false;
let _errorListener = null;
let _rejectionListener = null;

function _extractUserId() {
  try {
    const token = getStoredToken();
    if (!token) return null;
    const [, payload = ""] = token.split(".");
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    return JSON.parse(window.atob(padded))?.sub ?? null;
  } catch {
    return null;
  }
}

function _reportGlobalError(errorType, message, detail = null) {
  try {
    reportClientError({
      error_message: message,
      component_stack: detail || "",
      route: typeof window !== "undefined" ? window.location.pathname : "",
      user_agent: typeof navigator !== "undefined" ? navigator.userAgent : "",
      error_type: errorType,
      user_id: _extractUserId(),
      trace_id: null,
    });
  } catch {
    // Reporting must never throw.
  }
}

export function installGlobalErrorHandlers() {
  if (_isInstalled || typeof window === "undefined") return;
  _isInstalled = true;

  _errorListener = (event) => {
    try {
      const message = event.error?.message || event.message || "Unknown error";
      const stack = event.error?.stack || "";
      console.error("[GlobalErrorHandler] Uncaught error:", event.error ?? event);
      _reportGlobalError("uncaught_error", message, stack);
    } catch {
      // Error handling must never throw.
    }
  };

  _rejectionListener = (event) => {
    try {
      const reason = event.reason;
      const message =
        reason instanceof Error
          ? reason.message
          : typeof reason === "string"
            ? reason
            : "Unhandled promise rejection";
      const stack = reason instanceof Error ? (reason.stack || "") : "";

      if (
        message.includes("AbortError") ||
        message.includes("The user aborted") ||
        message.includes("NetworkError when attempting to fetch")
      ) {
        return;
      }

      console.error("[GlobalErrorHandler] Unhandled rejection:", reason);
      _reportGlobalError("unhandled_rejection", message, stack);
    } catch {
      // Rejection handling must never throw.
    }
  };

  window.addEventListener("error", _errorListener);
  window.addEventListener("unhandledrejection", _rejectionListener);
}

export function uninstallGlobalErrorHandlers() {
  if (typeof window !== "undefined") {
    if (_errorListener) {
      window.removeEventListener("error", _errorListener);
    }
    if (_rejectionListener) {
      window.removeEventListener("unhandledrejection", _rejectionListener);
    }
  }
  _errorListener = null;
  _rejectionListener = null;
  _isInstalled = false;
}
