import { afterEach, describe, expect, it, vi } from "vitest";

import {
  checkApiCompatibility,
  isActionableVersionMismatch,
  isAdvisoryVersionMismatch,
} from "../api/version";

describe("checkApiCompatibility", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete globalThis.__AINDY_APP_VERSION_OVERRIDE__;
  });

  it("returns compatible when versions match exactly", async () => {
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

    expect(result).toEqual({
      status: "minor_mismatch",
      apiVersion: "1.2.0",
      clientVersion: "1.3.0",
    });
  });

  it("returns compatible when versions match exactly", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "1.3.0";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            api_version: "1.3.0",
            min_client_version: "1.0.0",
            breaking_change_policy: "policy",
          }),
      }),
    );

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({ status: "compatible", apiVersion: "1.3.0" });
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

  it("returns patch_mismatch when only patch versions differ", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "1.3.0";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            api_version: "1.3.1",
            min_client_version: "1.0.0",
            breaking_change_policy: "policy",
          }),
      }),
    );

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({
      status: "patch_mismatch",
      apiVersion: "1.3.1",
      clientVersion: "1.3.0",
    });
  });

  it("returns minor_mismatch when minor versions differ", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "1.3.0";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            api_version: "1.4.0",
            min_client_version: "1.0.0",
            breaking_change_policy: "policy",
          }),
      }),
    );

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({
      status: "minor_mismatch",
      apiVersion: "1.4.0",
      clientVersion: "1.3.0",
    });
  });

  it("returns client_ahead when client major is newer than api major", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "2.0.0";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            api_version: "1.9.0",
            min_client_version: "1.0.0",
            breaking_change_policy: "policy",
          }),
      }),
    );

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({
      status: "client_ahead",
      apiVersion: "1.9.0",
      clientVersion: "2.0.0",
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

  it("returns unreachable when the version check times out", async () => {
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ = "1.3.0";
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("The operation was aborted.", "AbortError")));

    const result = await checkApiCompatibility("http://localhost:8000");

    expect(result).toEqual({
      status: "unreachable",
      error: "AbortError: The operation was aborted.",
    });
  });

  it("classifies actionable mismatches", () => {
    expect(isActionableVersionMismatch("major_mismatch")).toBe(true);
    expect(isActionableVersionMismatch("minor_mismatch")).toBe(true);
    expect(isActionableVersionMismatch("patch_mismatch")).toBe(false);
  });

  it("classifies advisory mismatches", () => {
    expect(isAdvisoryVersionMismatch("patch_mismatch")).toBe(true);
    expect(isAdvisoryVersionMismatch("client_ahead")).toBe(true);
    expect(isAdvisoryVersionMismatch("major_mismatch")).toBe(false);
  });
});
