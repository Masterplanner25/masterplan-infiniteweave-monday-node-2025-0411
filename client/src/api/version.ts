import { ROUTES } from "./_routes.js";

export interface ApiVersionInfo {
  api_version: string;
  min_client_version: string;
  breaking_change_policy: string;
  changelog_url?: string | null;
}

export type VersionCompatibility =
  | { status: "compatible"; apiVersion: string }
  | { status: "patch_mismatch"; apiVersion: string; clientVersion: string }
  | { status: "minor_mismatch"; apiVersion: string; clientVersion: string }
  | { status: "major_mismatch"; apiVersion: string; clientVersion: string }
  | { status: "client_ahead"; apiVersion: string; clientVersion: string }
  | { status: "unreachable"; error: string };

function getClientVersion(): string {
  return globalThis.__AINDY_APP_VERSION_OVERRIDE__ || __APP_VERSION__;
}

function getVersionEndpoint(apiBaseUrl: string): string {
  const normalized = (apiBaseUrl || "").replace(/\/$/, "");
  const versionPath = ROUTES.PLATFORM.VERSION;
  if (!normalized) {
    return versionPath;
  }
  if (normalized.endsWith("/api")) {
    return `${normalized}${versionPath.replace(/^\/api/, "")}`;
  }
  return `${normalized}${versionPath}`;
}

export async function checkApiCompatibility(
  apiBaseUrl: string,
): Promise<VersionCompatibility> {
  try {
    const signal =
      typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
        ? AbortSignal.timeout(5000)
        : undefined;
    const response = await fetch(getVersionEndpoint(apiBaseUrl), {
      headers: {
        "X-Client-Version": getClientVersion(),
      },
      signal,
    });
    if (!response.ok) {
      return { status: "unreachable", error: `HTTP ${response.status}` };
    }
    const data: ApiVersionInfo = await response.json();
    const clientVersion = getClientVersion();
    const [apiMajor, apiMinor, apiPatch] = data.api_version.split(".").map(Number);
    const [clientMajor, clientMinor, clientPatch] = clientVersion.split(".").map(Number);

    if (clientMajor > apiMajor) {
      return {
        status: "client_ahead",
        apiVersion: data.api_version,
        clientVersion,
      };
    }
    if (apiMajor !== clientMajor) {
      return {
        status: "major_mismatch",
        apiVersion: data.api_version,
        clientVersion,
      };
    }
    if (apiMinor !== clientMinor) {
      return {
        status: "minor_mismatch",
        apiVersion: data.api_version,
        clientVersion,
      };
    }
    if (apiPatch !== clientPatch) {
      return {
        status: "patch_mismatch",
        apiVersion: data.api_version,
        clientVersion,
      };
    }

    return { status: "compatible", apiVersion: data.api_version };
  } catch (err) {
    return { status: "unreachable", error: String(err) };
  }
}

export function isActionableVersionMismatch(
  status: VersionCompatibility["status"],
): boolean {
  return status === "major_mismatch" || status === "minor_mismatch";
}

export function isAdvisoryVersionMismatch(
  status: VersionCompatibility["status"],
): boolean {
  return status === "patch_mismatch" || status === "client_ahead";
}
