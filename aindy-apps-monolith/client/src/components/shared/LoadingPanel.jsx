export function LoadingPanel({ lines = 3, label }) {
  const widthClasses = ["w-full", "w-3/4", "w-1/2"];

  return (
    <div className="rounded-2xl border border-zinc-800/50 bg-zinc-950/50 p-6">
      <div className="space-y-3">
        {Array.from({ length: lines }, (_, index) => (
          <div
            key={index}
            data-testid="loading-panel-line"
            className={`h-3 rounded bg-zinc-800 animate-pulse ${widthClasses[index % widthClasses.length]}`}
          />
        ))}
      </div>
      {label ? <p className="mt-4 text-center text-xs text-zinc-500">{label}</p> : null}
    </div>
  );
}
