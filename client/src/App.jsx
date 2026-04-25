import { lazy } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/shared/ui/tooltip";

import ErrorBoundary, { RouteErrorBoundary } from "./components/shared/ErrorBoundary";
import AppShell from "./components/shared/AppShell";
import KPIDashboard from "./components/shared/KPIDashboard";
import ProtectedRoute from "./components/shared/ProtectedRoute";
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
const AgentConsole = lazy(() => import("./components/platform/AgentConsole"));
const FlowEngineConsole = lazy(() => import("./components/platform/FlowEngineConsole"));
const ObservabilityDashboard = lazy(() => import("./components/platform/ObservabilityDashboard"));
const HealthDashboard = lazy(() => import("./components/platform/HealthDashboard"));
const ExecutionConsole = lazy(() => import("./components/platform/ExecutionConsole"));
const AgentApprovalInbox = lazy(() => import("./components/platform/AgentApprovalInbox"));
const AgentRegistry = lazy(() => import("./components/platform/AgentRegistry"));
const RippleTraceViewer = lazy(() => import("./components/platform/RippleTraceViewer"));

function BootGate() {
  const { booting, booted, bootError, bootSystem } = useSystem();

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
          <button
            onClick={() => bootSystem().catch(() => {})}
            className="mt-6 rounded-2xl bg-[#00ffaa] px-4 py-3 text-sm font-black uppercase tracking-[0.18em] text-black"
          >
            Retry Boot
          </button>
        </div>
      </div>
    );
  }

  return <Outlet />;
}

export default function App() {
  const routeElement = (name, element) => (
    <RouteErrorBoundary name={name}>
      {element}
    </RouteErrorBoundary>
  );

  return (
    <TooltipProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ErrorBoundary>
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
                  <Route element={<ProtectedRoute requireAdmin />}>
                    <Route path="/platform/agent" element={routeElement("Agent Console", <AgentConsole />)} />
                    <Route path="/platform/flows" element={routeElement("Flow Engine Console", <FlowEngineConsole />)} />
                    <Route path="/platform/observability" element={routeElement("Observability", <ObservabilityDashboard />)} />
                    <Route path="/platform/health" element={routeElement("Health Dashboard", <HealthDashboard />)} />
                    <Route path="/platform/executions" element={routeElement("Execution Console", <ExecutionConsole />)} />
                    <Route path="/platform/approvals" element={routeElement("Agent Approvals", <AgentApprovalInbox />)} />
                    <Route path="/platform/registry" element={routeElement("Agent Registry", <AgentRegistry />)} />
                    <Route path="/platform/trace" element={routeElement("Ripple Trace", <RippleTraceViewer />)} />
                  </Route>
                  <Route path="*" element={<Navigate to="/dashboard" replace />} />
                </Route>
              </Route>
            </Route>
          </Routes>
        </ErrorBoundary>
      </BrowserRouter>
    </TooltipProvider>
  );
}
