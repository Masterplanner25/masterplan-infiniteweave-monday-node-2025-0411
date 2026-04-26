interface Props {
  apiVersion: string;
  clientVersion: string;
}

export function VersionMismatchBanner({ apiVersion, clientVersion }: Props) {
  return (
    <div
      role="alert"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        background: "#b91c1c",
        color: "white",
        padding: "12px 16px",
        textAlign: "center",
        fontSize: "14px",
      }}
    >
      <strong>Version mismatch:</strong> This page (v{clientVersion}) is incompatible with
      the current API (v{apiVersion}).
      <button
        onClick={() => window.location.reload()}
        style={{
          marginLeft: 12,
          textDecoration: "underline",
          cursor: "pointer",
          background: "none",
          border: "none",
          color: "white",
        }}
      >
        Reload to update
      </button>
    </div>
  );
}
