import { Component, Suspense } from "react";
import { getStoredToken } from "../../api/_core.js";
import { reportClientError } from "../../api/operator.js";

function RouteSpinner() {
  return (
    <div className="flex h-full min-h-[200px] items-center justify-center">
      <div className="h-5 w-5 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-300" />
    </div>
  );
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info.componentStack);
    try {
      const token = getStoredToken();
      let userId = null;
      if (token) {
        try {
          const payload = JSON.parse(atob(token.split(".")[1]));
          userId = payload.sub || null;
        } catch {}
      }
      reportClientError({
        error_message: error?.message || String(error),
        component_stack: info?.componentStack || "",
        route: typeof window !== "undefined" ? window.location.pathname : "",
        user_agent: typeof navigator !== "undefined" ? navigator.userAgent : "",
        error_type: "boundary",
        user_id: userId,
        trace_id: null,
      });
    } catch {}
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="flex min-h-screen items-center justify-center bg-[#09090b] text-[#fafafa]">
            <div className="max-w-md rounded-2xl border border-zinc-800 bg-zinc-950/90 px-6 py-4 text-center">
              <p className="text-sm text-zinc-400">
                Something went wrong loading this page.
              </p>
              <button
                className="mt-3 text-xs text-zinc-500 underline"
                onClick={() => this.setState({ hasError: false, error: null })}
              >
                Try again
              </button>
            </div>
          </div>
        )
      );
    }

    return this.props.children;
  }
}

export function RouteErrorBoundary({ children, name }) {
  return (
    <ErrorBoundary
      fallback={
        <div className="flex h-full min-h-[200px] items-center justify-center text-sm text-zinc-400">
          <span>{name || "This page"} encountered an error.</span>
          <button
            className="ml-2 text-xs text-zinc-500 underline"
            onClick={() => window.location.reload()}
          >
            Reload
          </button>
        </div>
      }
    >
      <Suspense fallback={<RouteSpinner />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}
