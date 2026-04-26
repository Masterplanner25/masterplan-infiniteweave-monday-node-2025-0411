import { afterEach, describe, expect, it, vi } from "vitest";

import { checkApiCompatibility } from "../api/version";

describe("checkApiCompatibility", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete globalThis.__AINDY_APP_VERSION_OVERRIDE__;
  });

  it("returns compatible when major versions match", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "1.3.0";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            api_version: "1.2.0",
            min_client_version: "1.0.0",
            breaking_change_policy: "policy",
          }),
      }),
    );

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({ status: "compatible", apiVersion: "1.2.0" });
  });

  it("returns major_mismatch when major versions differ", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "1.3.0";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            api_version: "2.0.0",
            min_client_version: "2.0.0",
            breaking_change_policy: "policy",
          }),
      }),
    );

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({
      status: "major_mismatch",
      apiVersion: "2.0.0",
      clientVersion: "1.3.0",
    });
  });

  it("returns unreachable when fetch throws", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "1.3.0";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({
      status: "unreachable",
      error: "Error: network down",
    });
  });
});
