export function EmptyState({ message, hint }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-zinc-800/30 bg-zinc-950/30 p-8 text-center">
      <p className="text-sm text-zinc-400">{message}</p>
      {hint ? <p className="mt-1 text-xs text-zinc-600">{hint}</p> : null}
    </div>
  );
}
