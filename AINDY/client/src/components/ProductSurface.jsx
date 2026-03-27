import React from "react";

const TOKENS = {
  panel: "border border-zinc-800/80 bg-zinc-950/80 backdrop-blur-sm",
  muted: "text-zinc-400",
  text: "text-zinc-100",
};

export function Surface({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={`rounded-2xl ${TOKENS.panel} ${className}`}>
      {(title || subtitle || action) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-800/70 px-5 py-4">
          <div>
            {title ? <h2 className={`text-base font-semibold ${TOKENS.text}`}>{title}</h2> : null}
            {subtitle ? <p className={`mt-1 text-sm ${TOKENS.muted}`}>{subtitle}</p> : null}
          </div>
          {action ? <div className="shrink-0">{action}</div> : null}
        </div>
      )}
      <div className="px-5 py-5">{children}</div>
    </section>
  );
}

export function MetricCard({ label, value, detail, tone = "cyan" }) {
  const tones = {
    cyan: "from-cyan-400/20 to-cyan-600/10 text-cyan-200",
    amber: "from-amber-400/20 to-amber-600/10 text-amber-200",
    emerald: "from-emerald-400/20 to-emerald-600/10 text-emerald-200",
    rose: "from-rose-400/20 to-rose-600/10 text-rose-200",
  };
  return (
    <div className={`rounded-2xl border border-zinc-800/80 bg-gradient-to-br ${tones[tone] || tones.cyan} p-4`}>
      <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">{label}</div>
      <div className="mt-3 text-2xl font-semibold text-zinc-50">{value}</div>
      {detail ? <div className="mt-2 text-sm text-zinc-400">{detail}</div> : null}
    </div>
  );
}

export function EmptyState({ title, body }) {
  return (
    <div className="rounded-2xl border border-dashed border-zinc-800 bg-zinc-950/60 px-6 py-12 text-center">
      <h3 className="text-lg font-semibold text-zinc-100">{title}</h3>
      <p className="mx-auto mt-2 max-w-xl text-sm text-zinc-400">{body}</p>
    </div>
  );
}

export function StatusPill({ label, tone = "zinc" }) {
  const tones = {
    zinc: "border-zinc-700 bg-zinc-900 text-zinc-300",
    cyan: "border-cyan-700/60 bg-cyan-950/50 text-cyan-200",
    amber: "border-amber-700/60 bg-amber-950/50 text-amber-200",
    emerald: "border-emerald-700/60 bg-emerald-950/50 text-emerald-200",
    rose: "border-rose-700/60 bg-rose-950/50 text-rose-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${tones[tone] || tones.zinc}`}>
      {label}
    </span>
  );
}

export function ActionButton({
  children,
  onClick,
  disabled = false,
  variant = "primary",
  className = "",
  type = "button",
}) {
  const variants = {
    primary: "bg-cyan-300 text-zinc-950 hover:bg-cyan-200",
    secondary: "border border-zinc-700 bg-zinc-900 text-zinc-100 hover:bg-zinc-800",
    danger: "bg-rose-400 text-zinc-950 hover:bg-rose-300",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-xl px-3 py-2 text-sm font-medium transition ${variants[variant] || variants.primary} disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      {children}
    </button>
  );
}
