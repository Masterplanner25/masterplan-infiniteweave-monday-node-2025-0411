import { ApiError, request, unwrapEnvelope } from "../api/_core.js";

function mockResponse({ ok, status, body = "", headers = {} }) {
  return {
    ok,
    status,
    text: vi.fn().mockResolvedValue(typeof body === "string" ? body : JSON.stringify(body)),
    headers: {
      get: vi.fn((key) => headers[key] ?? headers[key?.toLowerCase?.()] ?? null),
    },
  };
}

describe("api core transport behavior", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("unwraps execution envelopes via unwrapEnvelope", () => {
    expect(
      unwrapEnvelope({
        data: { items: [1, 2] },
        error: null,
        trace_id: "abc123",
        eu_id: "eu_1",
      }),
    ).toEqual({ items: [1, 2] });
  });

  it("throws ApiError for domain-level envelope errors", () => {
    expect(() =>
      unwrapEnvelope({
        data: null,
        error: "Something went wrong in the service",
        trace_id: "abc123",
      }),
    ).toThrowError(ApiError);

    try {
      unwrapEnvelope({
        data: null,
        error: "Something went wrong in the service",
        trace_id: "abc123",
      });
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error.status).toBe(200);
      expect(error.message).toBe("Something went wrong in the service");
    }
  });

  it("normalizes raw network errors into ApiError(0)", async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(request("/health")).rejects.toMatchObject({
      status: 0,
      message: "Network error. Check your connection.",
    });
  });

  it("retries once on 503 with Retry-After", async () => {
    vi.useFakeTimers();
    global.fetch = vi.fn()
      .mockResolvedValueOnce(
        mockResponse({
          ok: false,
          status: 503,
          body: "queue saturated",
          headers: { "Retry-After": "1" },
        }),
      )
      .mockResolvedValueOnce(
        mockResponse({
          ok: true,
          status: 200,
          body: { ok: true },
        }),
      );

    const promise = request("/health");
    await vi.advanceTimersByTimeAsync(1000);
    await expect(promise).resolves.toEqual({ ok: true });
    expect(global.fetch).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("does not retry again when _isRetry is true", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      mockResponse({
        ok: false,
        status: 503,
        body: "queue saturated",
        headers: { "Retry-After": "1" },
      }),
    );

    await expect(request("/health", { _isRetry: true })).rejects.toBeInstanceOf(ApiError);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("does not retry when Retry-After exceeds 60 seconds", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      mockResponse({
        ok: false,
        status: 503,
        body: "queue saturated",
        headers: { "Retry-After": "61" },
      }),
    );

    await expect(request("/health")).rejects.toBeInstanceOf(ApiError);
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
