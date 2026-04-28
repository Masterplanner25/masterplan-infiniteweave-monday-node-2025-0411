import { act, renderHook, waitFor } from "@testing-library/react";
import { ApiError } from "../api/_core.js";
import { useApiCall } from "../lib/useApiCall.js";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useApiCall", () => {
  it("sets data on success and clears loading and error", async () => {
    const apiFn = vi.fn().mockResolvedValue({ items: [1, 2, 3] });
    const { result } = renderHook(() => useApiCall(apiFn, { domain: "tasks" }));

    let response;
    await act(async () => {
      response = await result.current.execute();
    });

    expect(response).toEqual({ items: [1, 2, 3] });
    expect(result.current.data).toEqual({ items: [1, 2, 3] });
    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("sets error state on failure", async () => {
    const error = new ApiError(500, "boom", { error: "boom" });
    const apiFn = vi.fn().mockRejectedValue(error);
    const { result } = renderHook(() => useApiCall(apiFn, { domain: "analytics" }));

    await act(async () => {
      await result.current.execute();
    });

    expect(result.current.error).toBe(error);
    expect(result.current.error.status).toBe(500);
    expect(result.current.loading).toBe(false);
  });

  it("adds the configured domain to errors", async () => {
    const error = new ApiError(503, "unavailable", null);
    const apiFn = vi.fn().mockRejectedValue(error);
    const { result } = renderHook(() => useApiCall(apiFn, { domain: "ARM" }));

    await act(async () => {
      await result.current.execute();
    });

    expect(result.current.error.domain).toBe("ARM");
  });

  it("does not set error state for 401 responses", async () => {
    const error = new ApiError(401, "expired", null);
    const apiFn = vi.fn().mockRejectedValue(error);
    const { result } = renderHook(() => useApiCall(apiFn, { domain: "tasks" }));

    await act(async () => {
      await result.current.execute();
    });

    expect(result.current.error).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("aborts on unmount without calling success or error callbacks", async () => {
    const pending = deferred();
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const apiFn = vi.fn((options = {}) => {
      options.signal?.addEventListener("abort", () => {
        pending.reject(new DOMException("Aborted", "AbortError"));
      }, { once: true });
      return pending.promise;
    });

    const { result, unmount } = renderHook(() =>
      useApiCall(apiFn, { domain: "tasks", onSuccess, onError })
    );

    act(() => {
      result.current.execute();
    });

    unmount();

    await act(async () => {
      await Promise.resolve();
    });

    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it("tracks loading while the request is in flight", async () => {
    const pending = deferred();
    const apiFn = vi.fn().mockReturnValue(pending.promise);
    const { result } = renderHook(() => useApiCall(apiFn, { domain: "tasks" }));

    act(() => {
      result.current.execute();
    });

    expect(result.current.loading).toBe(true);

    await act(async () => {
      pending.resolve(["a"]);
      await pending.promise;
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });
  });
});
