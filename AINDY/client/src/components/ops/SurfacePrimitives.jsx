import React from "react";

export const surfacePalette = {
  background: "#09090b",
  panel: "#101115",
  panelRaised: "#151821",
  border: "rgba(255,255,255,0.08)",
  borderStrong: "rgba(0,255,170,0.18)",
  text: "#f4f4f5",
  muted: "#9ca3af",
  accent: "#00ffaa",
  accentSoft: "rgba(0,255,170,0.12)",
  warning: "#f59e0b",
  danger: "#f87171",
  success: "#34d399",
  info: "#38bdf8",
};

export function formatDateTime(value) {
  if (!value) return "Pending";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Pending";
  return date.toLocaleString();
}

export function formatRelativeTime(value) {
  if (!value) return "just now";
  const ts = new Date(value).getTime();
  if (Number.isNaN(ts)) return "just now";
  const diffSeconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
  if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
  return `${Math.floor(diffSeconds / 86400)}d ago`;
}

export function formatCompactNumber(value) {
  const numeric = Number(value || 0);
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: numeric < 100 ? 1 : 0,
  }).format(numeric);
}

export function statusTone(status) {
  switch ((status || "").toLowerCase()) {
    case "low":
      return "success";
    case "medium":
      return "warning";
    case "high":
      return "danger";
    case "approved":
    case "success":
    case "completed":
      return "success";
    case "pending":
    case "pending_approval":
    case "waiting":
      return "warning";
    case "failed":
    case "rejected":
      return "danger";
    case "running":
    case "executing":
      return "info";
    default:
      return "neutral";
  }
}

const toneMap = {
  success: {
    color: surfacePalette.success,
    background: "rgba(52, 211, 153, 0.12)",
    border: "rgba(52, 211, 153, 0.28)",
  },
  warning: {
    color: surfacePalette.warning,
    background: "rgba(245, 158, 11, 0.12)",
    border: "rgba(245, 158, 11, 0.28)",
  },
  danger: {
    color: surfacePalette.danger,
    background: "rgba(248, 113, 113, 0.12)",
    border: "rgba(248, 113, 113, 0.28)",
  },
  info: {
    color: surfacePalette.info,
    background: "rgba(56, 189, 248, 0.12)",
    border: "rgba(56, 189, 248, 0.28)",
  },
  neutral: {
    color: surfacePalette.muted,
    background: "rgba(255, 255, 255, 0.04)",
    border: surfacePalette.border,
  },
};

export function PageShell({ title, eyebrow, description, actions, children }) {
  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <section
        className="overflow-hidden rounded-[28px] border p-8"
        style={{
          background:
            "radial-gradient(circle at top left, rgba(0,255,170,0.16), transparent 36%), linear-gradient(135deg, rgba(16,17,21,0.98), rgba(9,9,11,0.96))",
          borderColor: surfacePalette.borderStrong,
        }}
      >
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            {eyebrow ? (
              <div
                className="mb-3 text-xs font-semibold uppercase tracking-[0.28em]"
                style={{ color: surfacePalette.accent }}
              >
                {eyebrow}
              </div>
            ) : null}
            <h1 className="text-4xl font-black tracking-[-0.04em]" style={{ color: surfacePalette.text }}>
              {title}
            </h1>
            {description ? (
              <p className="mt-3 max-w-2xl text-sm leading-7" style={{ color: surfacePalette.muted }}>
                {description}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
        </div>
      </section>
      {children}
    </div>
  );
}

export function SurfaceGrid({ children }) {
  return <div className="grid gap-5 lg:grid-cols-12">{children}</div>;
}

export function SurfacePanel({ title, subtitle, actions, className = "", children }) {
  return (
    <section
      className={`rounded-[24px] border p-6 shadow-[0_22px_60px_rgba(0,0,0,0.28)] ${className}`.trim()}
      style={{
        background: "linear-gradient(180deg, rgba(21,24,33,0.92), rgba(12,12,14,0.94))",
        borderColor: surfacePalette.border,
      }}
    >
      {(title || subtitle || actions) && (
        <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            {title ? (
              <h2 className="text-lg font-semibold tracking-[-0.02em]" style={{ color: surfacePalette.text }}>
                {title}
              </h2>
            ) : null}
            {subtitle ? (
              <p className="mt-1 text-sm leading-6" style={{ color: surfacePalette.muted }}>
                {subtitle}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      )}
      {children}
    </section>
  );
}

export function MetricCard({ label, value, hint, tone = "neutral" }) {
  const colors = toneMap[tone] || toneMap.neutral;
  return (
    <div
      className="rounded-[20px] border p-5"
      style={{ background: colors.background, borderColor: colors.border }}
    >
      <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: surfacePalette.muted }}>
        {label}
      </div>
      <div className="mt-3 text-3xl font-black tracking-[-0.04em]" style={{ color: colors.color }}>
        {value}
      </div>
      {hint ? (
        <div className="mt-2 text-sm leading-6" style={{ color: surfacePalette.muted }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

export function InlineBadge({ children, tone = "neutral" }) {
  const colors = toneMap[tone] || toneMap.neutral;
  return (
    <span
      className="inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]"
      style={{
        color: colors.color,
        background: colors.background,
        borderColor: colors.border,
      }}
    >
      {children}
    </span>
  );
}

export function EmptyState({ title, description, action }) {
  return (
    <div
      className="flex min-h-[220px] flex-col items-center justify-center rounded-[22px] border border-dashed px-6 py-10 text-center"
      style={{ borderColor: surfacePalette.border, background: "rgba(255,255,255,0.02)" }}
    >
      <div className="text-xl font-semibold" style={{ color: surfacePalette.text }}>
        {title}
      </div>
      {description ? (
        <p className="mt-3 max-w-md text-sm leading-7" style={{ color: surfacePalette.muted }}>
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function LoadingState({ label = "Loading" }) {
  return (
    <div className="flex min-h-[160px] items-center justify-center rounded-[22px] border" style={{ borderColor: surfacePalette.border }}>
      <div className="flex items-center gap-3 text-sm" style={{ color: surfacePalette.muted }}>
        <span
          className="h-2.5 w-2.5 animate-pulse rounded-full"
          style={{ background: surfacePalette.accent }}
        />
        {label}
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div
      className="rounded-[20px] border px-5 py-4"
      style={{
        color: surfacePalette.danger,
        background: "rgba(248,113,113,0.1)",
        borderColor: "rgba(248,113,113,0.32)",
      }}
    >
      <div className="text-sm font-medium">{message}</div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em]"
          style={{ borderColor: "rgba(248,113,113,0.32)" }}
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function ActionButton({
  children,
  onClick,
  tone = "primary",
  disabled = false,
  type = "button",
}) {
  const styles =
    tone === "ghost"
      ? {
          background: "rgba(255,255,255,0.03)",
          color: surfacePalette.text,
          borderColor: surfacePalette.border,
        }
      : tone === "danger"
      ? {
          background: "rgba(248,113,113,0.12)",
          color: surfacePalette.danger,
          borderColor: "rgba(248,113,113,0.3)",
        }
      : {
          background: surfacePalette.accent,
          color: "#04110d",
          borderColor: "rgba(0,255,170,0.5)",
        };

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="rounded-full border px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] transition-all disabled:cursor-not-allowed disabled:opacity-50"
      style={styles}
    >
      {children}
    </button>
  );
}
