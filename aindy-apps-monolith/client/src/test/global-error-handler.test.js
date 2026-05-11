import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/operator.js", () => ({
  reportClientError: vi.fn(),
}));

vi.mock("../api/_core.js", () => ({
  getStoredToken: vi.fn(() => null),
}));

import {
  installGlobalErrorHandlers,
  uninstallGlobalErrorHandlers,
} from "../lib/globalErrorHandler.js";

function makeUnhandledRejectionEvent(reason) {
  const event = new Event("unhandledrejection", { cancelable: true });
  Object.defineProperty(event, "reason", {
    configurable: true,
    value: reason,
  });
  return event;
}

describe("installGlobalErrorHandlers", () => {
  beforeEach(() => {
    uninstallGlobalErrorHandlers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    uninstallGlobalErrorHandlers();
  });

  it("installs without throwing", () => {
    expect(() => installGlobalErrorHandlers()).not.toThrow();
  });

  it("is idempotent and does not double-register", async () => {
    const { reportClientError } = await import("../api/operator.js");
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    installGlobalErrorHandlers();
    installGlobalErrorHandlers();
    window.dispatchEvent(makeUnhandledRejectionEvent(new Error("one error")));

    expect(reportClientError).toHaveBeenCalledTimes(1);
    errorSpy.mockRestore();
  });

  it("reports unhandled promise rejections", async () => {
    const { reportClientError } = await import("../api/operator.js");
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    installGlobalErrorHandlers();
    window.dispatchEvent(makeUnhandledRejectionEvent(new Error("test rejection")));

    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({
        error_type: "unhandled_rejection",
        error_message: "test rejection",
      }),
    );

    errorSpy.mockRestore();
  });

  it("suppresses AbortError rejections", async () => {
    const { reportClientError } = await import("../api/operator.js");
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const abortError = new Error("AbortError: The user aborted");
    abortError.name = "AbortError";

    installGlobalErrorHandlers();
    window.dispatchEvent(makeUnhandledRejectionEvent(abortError));

    expect(reportClientError).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
