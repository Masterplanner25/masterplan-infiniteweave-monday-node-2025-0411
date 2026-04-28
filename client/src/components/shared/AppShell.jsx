import React, { useMemo, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";

const PLATFORM_BASE = import.meta.env.VITE_PLATFORM_BASE_URL ?? "/platform";
const platformUrl = (path) => `${PLATFORM_BASE}${path}`;

const NAV_GROUPS = [
  {
    title: "PLATFORM",
    adminOnly: true,
    links: [
      { to: "/agent", label: "Agent Console", external: true },
      { to: "/flows", label: "Flow Engine", external: true },
      { to: "/observability", label: "Observability", external: true },
      { to: "/health", label: "Health", external: true },
      { to: "/executions", label: "Executions", external: true },
      { to: "/approvals", label: "Approvals", external: true },
      { to: "/registry", label: "Registry", external: true },
      { to: "/trace", label: "Ripple Trace", external: true },
    ],
  },
  {
    title: "WORKSPACE",
    links: [
      { to: "/dashboard", label: "Dashboard" },
      { to: "/tasks", label: "Tasks" },
      { to: "/masterplan", label: "MasterPlan" },
    ],
  },
  {
    title: "ANALYTICS",
    links: [
      { to: "/analytics", label: "Analytics" },
      { to: "/kpi", label: "KPI Snapshot" },
    ],
  },
  {
    title: "GROWTH",
    links: [
      { to: "/search/research", label: "Research" },
      { to: "/search/leadgen", label: "Lead Gen" },
      { to: "/social", label: "Social Feed" },
      { to: "/freelance", label: "Freelance" },
    ],
  },
  {
    title: "AI TOOLS",
    links: [
      { to: "/arm/analyze", label: "ARM Analyze" },
      { to: "/arm/config", label: "ARM Config" },
      { to: "/arm/config/suggest", label: "ARM Suggest" },
      { to: "/arm/config/generate", label: "ARM Generate" },
      { to: "/arm/config/logs", label: "ARM Logs" },
      { to: "/arm/config/metrics", label: "ARM Metrics" },
    ],
  },
  {
    title: "IDENTITY",
    links: [
      { to: "/identity", label: "Identity" },
      { to: "/memory", label: "Memory" },
    ],
  },
];

function ShellLink({ to, label, onNavigate, external = false }) {
  const baseClasses = [
    "block rounded-2xl border px-3 py-2 text-sm transition-colors",
    "border-zinc-800/60 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900/70 hover:text-zinc-100",
  ];

  if (external) {
    const isActive = typeof window !== "undefined" && window.location.pathname.startsWith("/platform");
    return (
      <a
        href={platformUrl(to)}
        onClick={onNavigate}
        target="_self"
        className={[
          "block rounded-2xl border px-3 py-2 text-sm transition-colors",
          isActive
            ? "border-[#00ffaa]/30 bg-[#00ffaa]/10 text-[#00ffaa]"
            : "border-zinc-800/60 bg-zinc-950/40 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900/70 hover:text-zinc-100",
        ].join(" ")}
      >
        {label}
      </a>
    );
  }

  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        [
          ...baseClasses,
          isActive
            ? "border-[#00ffaa]/30 bg-[#00ffaa]/10 text-[#00ffaa]"
            : "",
        ].join(" ")
      }
    >
      {label}
    </NavLink>
  );
}

export default function AppShell() {
  const { isAdmin, logout, user } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const visibleGroups = useMemo(
    () => NAV_GROUPS.filter((group) => !group.adminOnly || isAdmin),
    [isAdmin],
  );

  return (
    <div className="min-h-screen bg-[#09090b] text-[#fafafa] selection:bg-[#00ffaa]/30 lg:flex">
      <aside
        className={[
          "fixed inset-y-0 left-0 z-40 w-80 border-r border-zinc-800/60 bg-zinc-950/95 backdrop-blur transition-transform lg:static lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        <div className="flex h-full flex-col">
          <div className="border-b border-zinc-800/60 px-5 py-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-[#00ffaa]">
                  Control Surface
                </p>
                <h1 className="mt-3 text-2xl font-black tracking-tight text-white">
                  A.I.N.D.Y.
                </h1>
                <p className="mt-2 text-sm text-zinc-500">
                  Route the workspace, analytics, growth, and platform surfaces.
                </p>
              </div>
              <button
                type="button"
                className="rounded-xl border border-zinc-800 px-3 py-2 text-xs uppercase tracking-[0.18em] text-zinc-400 lg:hidden"
                onClick={() => setSidebarOpen(false)}
              >
                Close
              </button>
            </div>
          </div>

          <nav className="flex-1 space-y-6 overflow-y-auto px-4 py-5 custom-scrollbar">
            {visibleGroups.map((group) => (
              <div key={group.title}>
                <p className="mb-3 px-2 text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-600">
                  {group.title}
                </p>
                <div className="space-y-2">
                  {group.links.map((link) => (
                    <ShellLink
                      key={link.to}
                      to={link.to}
                      label={link.label}
                      external={link.external}
                      onNavigate={() => setSidebarOpen(false)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </nav>
        </div>
      </aside>

      {sidebarOpen ? (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      ) : null}

      <div className="flex min-h-screen flex-1 flex-col lg:ml-0">
        <header className="sticky top-0 z-20 border-b border-zinc-800/60 bg-[#09090b]/95 backdrop-blur">
          <div className="flex items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="rounded-2xl border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.18em] text-zinc-300 lg:hidden"
                onClick={() => setSidebarOpen(true)}
              >
                Menu
              </button>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-600">
                  Navigation Shell
                </p>
                <p className="text-sm text-zinc-300">Unified workspace routing</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden rounded-2xl border border-zinc-800 bg-zinc-950/70 px-4 py-2 text-right sm:block">
                <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-600">
                  Active Identity
                </p>
                <p className="text-sm text-zinc-200">{user?.email || "Unknown user"}</p>
              </div>
              <button
                type="button"
                onClick={logout}
                className="rounded-2xl bg-[#00ffaa] px-4 py-2 text-[10px] font-black uppercase tracking-[0.18em] text-black transition-colors hover:bg-[#00ffaa]/80"
              >
                Logout
              </button>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
          <div className="min-h-full rounded-[28px] border border-zinc-800/60 bg-zinc-950/40 p-4 shadow-2xl shadow-black/20 sm:p-6 lg:p-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
