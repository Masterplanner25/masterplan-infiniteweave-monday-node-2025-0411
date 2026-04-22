import React, { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";
import { useSystem } from "../../context/SystemContext";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, login } = useAuth();
  const { bootSystem, booting } = useSystem();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!email.trim() || !password) {
      setError("Email and password are required.");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      const token = await login(email.trim(), password);
      await bootSystem(token);
      const nextPath = location.state?.from?.pathname || "/dashboard";
      navigate(nextPath, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#09090b] px-6 text-[#fafafa]">
      <div className="w-full max-w-md rounded-3xl border border-zinc-800 bg-zinc-950/90 p-8 shadow-2xl">
        <div className="mb-8">
          <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-[#00ffaa]">
            Identity Boot
          </p>
          <h1 className="mt-3 text-3xl font-black tracking-tight text-white">
            Activate A.I.N.D.Y.
          </h1>
          <p className="mt-2 text-sm text-zinc-500">
            Sign in to restore memory, active runs, metrics, and execution state.
          </p>
        </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Email
            </span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 outline-none transition-colors focus:border-[#00ffaa]/50"
              placeholder="you@aindy.ai"
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.18em] text-zinc-500">
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 outline-none transition-colors focus:border-[#00ffaa]/50"
              placeholder="••••••••"
            />
          </label>

          {error ? (
            <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={submitting || booting}
            className="w-full rounded-2xl bg-[#00ffaa] px-4 py-3 text-sm font-black uppercase tracking-[0.18em] text-black transition-colors hover:bg-[#00ffaa]/80 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
          >
            {submitting || booting ? "Booting..." : "Login and Boot"}
          </button>
        </form>

        <p className="mt-6 text-sm text-zinc-500">
          Don&apos;t have an account?{" "}
          <Link className="text-[#00ffaa] hover:text-[#7dffd2]" to="/register">
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
