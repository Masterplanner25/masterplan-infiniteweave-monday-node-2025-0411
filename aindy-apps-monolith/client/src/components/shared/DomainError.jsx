export function DomainError({ error, domain, onRetry }) {
  if (!error) {
    return null;
  }

  const status = error?.status ?? "unknown";
  const label = domain || error?.domain || "server";

  let message = `${label} returned an unexpected error (${status}).`;
  if (status === 408) {
    message = `${label} timed out. Check your connection and try again.`;
  } else if (status === 429) {
    message = `${label} is rate-limited. Wait a moment and try again.`;
  } else if (status === 500) {
    message = `${label} encountered an error. Our team has been notified.`;
  } else if (status === 503) {
    message = `${label} is temporarily unavailable. Try again in a moment.`;
  }

  return (
    <div className="rounded-2xl border border-zinc-800/30 bg-zinc-950/30 p-6 text-center">
      <p className="text-sm text-zinc-400">{message}</p>
      {onRetry ? (
        <button
          type="button"
          className="mt-3 text-xs text-zinc-500 underline"
          onClick={onRetry}
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}

export default DomainError;
