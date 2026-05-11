const TYPE_STYLES = {
  error: "border-red-500/30 bg-red-950/80 text-red-200",
  success: "border-emerald-500/30 bg-emerald-950/80 text-emerald-200",
  info: "border-zinc-600/30 bg-zinc-900/90 text-zinc-200",
};

export function Toast({ toast, onDismiss }) {
  if (!toast) return null;

  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`fixed bottom-6 right-6 z-50 max-w-sm rounded-xl border px-4 py-3 text-sm shadow-xl backdrop-blur-sm ${
        TYPE_STYLES[toast.type] || TYPE_STYLES.error
      }`}
    >
      <span>{toast.message}</span>
      <button
        onClick={onDismiss}
        className="ml-3 text-xs underline opacity-60 hover:opacity-100"
        aria-label="Dismiss"
      >
        Dismiss
      </button>
    </div>
  );
}
