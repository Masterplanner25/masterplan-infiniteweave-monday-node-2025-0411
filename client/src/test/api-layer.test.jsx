import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/_core.js";
import { getFlowStrategies } from "../api/operator.js";

describe("getFlowStrategies", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("sends the stored token under the primary key", async () => {
    window.localStorage.setItem("token", "primary-token-value");

    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: () => Promise.resolve(JSON.stringify({ strategies: [], count: 0 })),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await getFlowStrategies();

    const [, opts] = fetchSpy.mock.calls[0];
    expect(opts.headers?.Authorization).toBe("Bearer primary-token-value");
  });

  it("returns ApiError on 404 for caller-level empty-state handling", async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve("Not Found"),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(getFlowStrategies()).rejects.toBeInstanceOf(ApiError);
  });
});
