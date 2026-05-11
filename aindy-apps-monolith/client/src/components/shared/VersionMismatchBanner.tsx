interface Props {
  status: "major_mismatch" | "minor_mismatch" | "patch_mismatch" | "client_ahead";
  apiVersion: string;
  clientVersion: string;
  onDismiss?: () => void;
}

const CONFIG = {
  major_mismatch: {
    bg: "#b91c1c",
    label: "Incompatible version",
    message: (api: string, client: string) =>
      `This page (v${client}) is incompatible with the current API (v${api}). Please reload.`,
    dismissable: false,
  },
  minor_mismatch: {
    bg: "#b45309",
    label: "API updated",
    message: (api: string, client: string) =>
      `API updated to v${api} (you have v${client}). Some features may not work correctly.`,
    dismissable: true,
  },
  patch_mismatch: {
    bg: "#1d4ed8",
    label: "Minor update available",
    message: (api: string, client: string) =>
      `API v${api} is available (you have v${client}). Reload when convenient.`,
    dismissable: true,
  },
  client_ahead: {
    bg: "#4b5563",
    label: "Client ahead of API",
    message: (api: string, client: string) =>
      `Client v${client} is ahead of API v${api}. This may indicate a partial rollback.`,
    dismissable: true,
  },
} as const;

export function VersionMismatchBanner({ status, apiVersion, clientVersion, onDismiss }: Props) {
  const config = CONFIG[status];
  if (!config) {
    return null;
  }

  return (
    <div
      role="alert"
      aria-live="polite"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        background: config.bg,
        color: "white",
        padding: "12px 16px",
        textAlign: "center",
        fontSize: "14px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "12px",
      }}
    >
      <strong>{config.label}:</strong>
      <span>{config.message(apiVersion, clientVersion)}</span>
      <button
        onClick={() => window.location.reload()}
        style={{
          textDecoration: "underline",
          cursor: "pointer",
          background: "none",
          border: "none",
          color: "white",
        }}
      >
        Reload
      </button>
      {config.dismissable && onDismiss ? (
        <button
          onClick={onDismiss}
          aria-label="Dismiss version warning"
          style={{
            marginLeft: 8,
            cursor: "pointer",
            background: "none",
            border: "none",
            color: "white",
            fontSize: "18px",
            lineHeight: 1,
          }}
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
