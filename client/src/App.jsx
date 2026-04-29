import { lazy, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/shared/ui/tooltip";

import {
  checkApiCompatibility,
  isAdvisoryVersionMismatch,
} from "./api/version";
import ErrorBoundary, { RouteErrorBoundary } from "./components/shared/ErrorBoundary";
import AppShell from "./components/shared/AppShell";
import KPIDashboard from "./components/shared/KPIDashboard";
import ProtectedRoute from "./components/shared/ProtectedRoute";
import { VersionMismatchBanner } from "./components/shared/VersionMismatchBanner";
import { useAuth } from "./context/AuthContext";
import LoginPage from "./pages/Login";
import RegisterPage from "./pages/Register";
import { useSystem } from "./context/SystemContext";

import "./App.css";

const Dashboard = lazy(() => import("./components/app/Dashboard"));
const TaskDashboard = lazy(() => import("./components/app/TaskDashboard"));
const MasterPlanDashboard = lazy(() => import("./components/app/MasterPlanDashboard"));
const AnalyticsPanel = lazy(() => import("./components/app/AnalyticsPanel"));
const ResearchEngine = lazy(() => import("./components/app/ResearchEngine"));
const LeadGen = lazy(() => import("./components/app/LeadGen"));
const Feed = lazy(() => import("./components/app/Feed"));
const FreelanceDashboard = lazy(() => import("./components/app/FreelanceDashboard"));
const ARMAnalyze = lazy(() => import("./components/app/ARMAnalyze"));
const ARMConfig = lazy(() => import("./components/app/ARMConfig"));
const ARMConfigSuggest = lazy(() => import("./components/app/ARMConfigSuggest"));
const ARMGenerate = lazy(() => import("./components/app/ARMGenerate"));
const ARMLogs = lazy(() => import("./components/app/ARMLogs"));
const ARMMetrics = lazy(() => import("./components/app/ARMMetrics"));
const MemoryBrowser = lazy(() => import("./components/app/MemoryBrowser"));
const IdentityDashboard = lazy(() => import("./components/app/IdentityDashboard"));

function BootGate() {
  const { booting, booted, bootError, bootSystem } = useSystem();
  const { logout } = useAuth();

  if (booting && !booted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#09090b] px-6 text-[#fafafa]">
        <div className="rounded-3xl border border-zinc-800 bg-zinc-950/90 px-8 py-6 text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-[#00ffaa]">
            Identity Boot
          </p>
          <p className="mt-3 text-sm text-zinc-400">
            Restoring memory, runs, metrics, and active flows.
          </p>
        </div>
      </div>
    );
  }

  if (bootError && !booted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#09090b] px-6 text-[#fafafa]">
        <div className="max-w-md rounded-3xl border border-red-500/30 bg-zinc-950/90 p-8">
          <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-red-300">
            Identity Boot Failed
          </p>
          <p className="mt-3 text-sm text-zinc-300">{bootError}</p>
          <div className="mt-6 flex gap-3">
            <button
              onClick={() => bootSystem().catch(() => {})}
              className="rounded-2xl bg-[#00ffaa] px-4 py-3 text-sm font-black uppercase tracking-[0.18em] text-black"
            >
              Retry
            </button>
            <button
              onClick={logout}
              className="rounded-2xl border border-zinc-700 px-4 py-3 text-sm font-medium text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
            >
              Sign Out
            </button>
          </div>
          <p className="mt-4 text-[10px] text-zinc-600">
            If the problem persists, sign out and log back in.
          </p>
        </div>
      </div>
    );
  }

  return <Outlet />;
}

function PlatformRedirect() {
  const { isAdmin } = useAuth();
  const platformBase = import.meta.env.VITE_PLATFORM_BASE_URL ?? "/platform";

  if (isAdmin) {
    // PlatformApp owns the /platform/* surface, including /agent and the
    // other admin-only console routes that used to live in this router
    // (AgentConsole, FlowEngineConsole, ObservabilityDashboard, etc.).
    const suffix = window.location.pathname.replace(/^\/platform/, "");
    const search = window.location.search || "";
    const hash = window.location.hash || "";
    window.location.href = `${platformBase}${suffix}${search}${hash}`;
    return null;
  }

  return <Navigate to="/dashboard" replace />;
}

export default function App() {
  const [versionStatus, setVersionStatus] = useState(null);
  const [versionDismissed, setVersionDismissed] = useState(false);
  const routeElement = (name, element) => (
    <RouteErrorBoundary name={name} layer="domain" domain={name}>
      {element}
    </RouteErrorBoundary>
  );

  const getClientVersionStr = () =>
    globalThis.__AINDY_APP_VERSION_OVERRIDE__ || __APP_VERSION__;

  const handleVersionStatus = (newStatus) => {
    setVersionStatus((currentStatus) => {
      const currentKey = currentStatus
        ? `${currentStatus.status}:${currentStatus.apiVersion || ""}:${currentStatus.clientVersion || ""}`
        : "";
      const nextKey = newStatus
        ? `${newStatus.status}:${newStatus.apiVersion || ""}:${newStatus.clientVersion || ""}`
        : "";

      if (
        newStatus?.status === "major_mismatch" ||
        newStatus?.status === "minor_mismatch" ||
        (nextKey && nextKey !== currentKey)
      ) {
        setVersionDismissed(false);
      }
      return newStatus;
    });
  };

  useEffect(() => {
    const versionCheckBaseUrl =
      import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

    const check = () => {
      checkApiCompatibility(versionCheckBaseUrl).then(handleVersionStatus);
    };

    check();

    const handleFocus = () => check();
    window.addEventListener("focus", handleFocus);

    const interval = setInterval(check, 10 * 60 * 1000);

    return () => {
      window.removeEventListener("focus", handleFocus);
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const handleApiWarning = () => {
      if (!versionStatus || versionStatus.status === "compatible") {
        handleVersionStatus({
          status: "minor_mismatch",
          apiVersion: "?",
          clientVersion: getClientVersionStr(),
        });
      }
    };

    window.addEventListener("aindy:version-warning", handleApiWarning);
    return () => window.removeEventListener("aindy:version-warning", handleApiWarning);
  }, [versionStatus]);

  const showBanner =
    !import.meta.env.DEV &&
    versionStatus &&
    versionStatus.status !== "compatible" &&
    versionStatus.status !== "unreachable" &&
    !versionDismissed;

  return (
    <>
      {showBanner ? (
        <VersionMismatchBanner
          status={versionStatus.status}
          apiVersion={versionStatus.apiVersion}
          clientVersion={versionStatus.clientVersion}
          onDismiss={
            isAdvisoryVersionMismatch(versionStatus.status)
              ? () => setVersionDismissed(true)
              : undefined
          }
        />
      ) : null}
      <TooltipProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <ErrorBoundary layer="platform">
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route element={<ProtectedRoute />}>
                <Route element={<BootGate />}>
                  <Route element={routeElement("Application Shell", <AppShell />)}>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={routeElement("Dashboard", <Dashboard />)} />
                    <Route path="/tasks" element={routeElement("Tasks", <TaskDashboard />)} />
                    <Route path="/masterplan" element={routeElement("MasterPlan", <MasterPlanDashboard />)} />
                    <Route path="/analytics" element={routeElement("Analytics", <AnalyticsPanel />)} />
                    <Route path="/kpi" element={routeElement("KPI Snapshot", <KPIDashboard />)} />
                    <Route path="/search/research" element={routeElement("Research", <ResearchEngine />)} />
                    <Route path="/search/leadgen" element={routeElement("Lead Generation", <LeadGen />)} />
                    <Route path="/social" element={routeElement("Social Feed", <Feed />)} />
                    <Route path="/freelance" element={routeElement("Freelance Dashboard", <FreelanceDashboard />)} />
                    <Route path="/arm/analyze" element={routeElement("ARM Analyze", <ARMAnalyze />)} />
                    <Route path="/arm/config" element={routeElement("ARM Config", <ARMConfig />)} />
                    <Route path="/arm/config/suggest" element={routeElement("ARM Suggest", <ARMConfigSuggest />)} />
                    <Route path="/arm/config/generate" element={routeElement("ARM Generate", <ARMGenerate />)} />
                    <Route path="/arm/config/logs" element={routeElement("ARM Logs", <ARMLogs />)} />
                    <Route path="/arm/config/metrics" element={routeElement("ARM Metrics", <ARMMetrics />)} />
                    <Route path="/memory" element={routeElement("Memory", <MemoryBrowser />)} />
                    <Route path="/identity" element={routeElement("Identity", <IdentityDashboard />)} />
                    <Route path="/platform/*" element={<PlatformRedirect />} />
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                  </Route>
                </Route>
              </Route>
            </Routes>
          </ErrorBoundary>
        </BrowserRouter>
      </TooltipProvider>
    </>
  );
}
