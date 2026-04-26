import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, adminRequest, authRequest } from "../api/_core.js";
import { getFlowStrategies } from "../api/operator.js";

function makeToken(payload) {
  const encoded = btoa(JSON.stringify(payload)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  return `header.${encoded}.signature`;
}

describe("getFlowStrategies", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("sends the stored token under the primary key", async () => {
    window.localStorage.setItem("token", makeToken({ is_admin: true }));

    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: () => Promise.resolve(JSON.stringify({ strategies: [], count: 0 })),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await getFlowStrategies();

    const [, opts] = fetchSpy.mock.calls[0];
    expect(opts.headers?.Authorization).toMatch(/^Bearer header\./);
  });

  it("returns ApiError on 404 for caller-level empty-state handling", async () => {
    window.localStorage.setItem("token", makeToken({ is_admin: true }));
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve("Not Found"),
    });
    vi.stubGlobal("fetch", fetchSpy);

    await expect(getFlowStrategies()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("adminRequest", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("resolves when token contains is_admin=true", async () => {
    window.localStorage.setItem("token", makeToken({ is_admin: true }));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      text: () => Promise.resolve(JSON.stringify({ data: "ok" })),
    }));

    await expect(adminRequest("/test", { method: "GET" })).resolves.toEqual({ data: "ok" });
  });

  it("rejects with 403 when token is missing", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    await expect(adminRequest("/test")).rejects.toMatchObject({ status: 403 });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("rejects with 403 when token has is_admin=false", async () => {
    window.localStorage.setItem("token", makeToken({ is_admin: false }));
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    await expect(adminRequest("/test")).rejects.toMatchObject({ status: 403 });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("version warning header handling", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("dispatches aindy:version-warning when the response includes X-Version-Warning", async () => {
    const eventSpy = vi.fn();
    window.addEventListener("aindy:version-warning", eventSpy);

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: (name) => (name === "X-Version-Warning" ? "backend updated" : null) },
      text: () => Promise.resolve(JSON.stringify({ ok: true })),
    }));

    await authRequest("/test", { method: "GET" });

    expect(eventSpy).toHaveBeenCalledTimes(1);
    expect(eventSpy.mock.calls[0][0].detail).toEqual({ message: "backend updated" });

    window.removeEventListener("aindy:version-warning", eventSpy);
  });
});
