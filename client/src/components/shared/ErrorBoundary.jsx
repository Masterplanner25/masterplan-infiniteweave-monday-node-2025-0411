import { Component } from "react";

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
