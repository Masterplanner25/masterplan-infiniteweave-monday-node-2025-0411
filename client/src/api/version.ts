export interface ApiVersionInfo {
  api_version: string;
  min_client_version: string;
  breaking_change_policy: string;
  changelog_url?: string | null;
}

export type VersionCompatibility =
  | { status: "compatible"; apiVersion: string }
  | { status: "major_mismatch"; apiVersion: string; clientVersion: string }
  | { status: "unreachable"; error: string };

function getClientVersion(): string {
  return globalThis.__AINDY_APP_VERSION_OVERRIDE__ || __APP_VERSION__;
}

function getVersionEndpoint(apiBaseUrl: string): string {
  const normalized = (apiBaseUrl || "").replace(/\/$/, "");
  if (!normalized) {
    return "/api/version";
  }
  if (normalized.endsWith("/api")) {
    return `${normalized}/version`;
  }
  return `${normalized}/api/version`;
}

export async function checkApiCompatibility(
  apiBaseUrl: string,
): Promise<VersionCompatibility> {
  try {
    const response = await fetch(getVersionEndpoint(apiBaseUrl), {
      headers: {
        "X-Client-Version": getClientVersion(),
      },
    });
    if (!response.ok) {
      return { status: "unreachable", error: `HTTP ${response.status}` };
    }
    const data: ApiVersionInfo = await response.json();
    const apiMajor = parseInt(data.api_version.split(".")[0], 10);
    const clientVersion = getClientVersion();
    const clientMajor = parseInt(clientVersion.split(".")[0], 10);

    if (apiMajor !== clientMajor) {
      return {
        status: "major_mismatch",
        apiVersion: data.api_version,
        clientVersion,
      };
    }

    return { status: "compatible", apiVersion: data.api_version };
  } catch (err) {
    return { status: "unreachable", error: String(err) };
  }
}
