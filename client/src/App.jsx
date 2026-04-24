import { lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/shared/ui/tooltip";

import ErrorBoundary, { RouteErrorBoundary } from "./components/shared/ErrorBoundary";
import LoginPage from "./components/shared/LoginPage";
import RegisterPage from "./pages/Register";
import { useAuth } from "./context/AuthContext";
import { useSystem } from "./context/SystemContext";

import "./App.css";

const Sidebar = lazy(() => import("./components/shared/Sidebar"));
const Dashboard = lazy(() => import("./components/app/Dashboard"));
const HealthDashboard = lazy(() => import("./components/platform/HealthDashboard"));
const ResearchEngine = lazy(() => import("./components/app/ResearchEngine"));
const AiSeoTool = lazy(() => import("./components/app/AiSeoTool"));
const InfiniteNetwork = lazy(() => import("./components/app/InfiniteNetwork"));
const LeadGen = lazy(() => import("./components/app/LeadGen"));
const FreelanceDashboard = lazy(() => import("./components/app/FreelanceDashboard"));
const TaskDashboard = lazy(() => import("./components/app/TaskDashboard"));
const MasterPlanDashboard = lazy(() => import("./components/app/MasterPlanDashboard"));
const ExecutionConsole = lazy(() => import("./components/platform/ExecutionConsole"));
const FlowEngineConsole = lazy(() => import("./components/platform/FlowEngineConsole"));
const AnalyticsPanel = lazy(() => import("./components/app/AnalyticsPanel"));
const Genesis = lazy(() => import("./components/app/Genesis"));
const AgentApprovalInbox = lazy(() => import("./components/platform/AgentApprovalInbox"));
const ObservabilityDashboard = lazy(() => import("./components/platform/ObservabilityDashboard"));
const RippleTraceViewer = lazy(() => import("./components/platform/RippleTraceViewer"));
const ARMAnalyze = lazy(() => import("./components/app/ARMAnalyze"));
const ARMGenerate = lazy(() => import("./components/app/ARMGenerate"));
const ARMLogs = lazy(() => import("./components/app/ARMLogs"));
const ARMConfig = lazy(() => import("./components/app/ARMConfig"));
const ProfileView = lazy(() => import("./components/app/ProfileView"));
const Feed = lazy(() => import("./components/app/Feed"));
const AgentConsole = lazy(() => import("./components/platform/AgentConsole"));
const MemoryBrowser = lazy(() => import("./components/app/MemoryBrowser"));
const IdentityDashboard = lazy(() => import("./components/app/IdentityDashboard"));
const AgentRegistry = lazy(() => import("./components/platform/AgentRegistry"));

function ProtectedRoute() {
  const location = useLocation();
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

function PlatformRoute() {
  const { isAdmin } = useSystem();

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <ErrorBoundary
      fallback={(
        <div className="p-8 text-sm text-zinc-400">
          Platform tool encountered an error.{" "}
          <button className="text-zinc-500 underline" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      )}
    >
      <Outlet />
    </ErrorBoundary>
  );
}

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

function AppShell() {
  return (
    <div className="flex min-h-screen bg-[#09090b] text-[#fafafa] font-sans selection:bg-[#00ffaa]/30">
      <Sidebar />
      <main className="flex-1 h-screen overflow-y-auto p-10 main-content-gradient custom-scrollbar">
        <Outlet />
      </main>
    </div>
  );
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
                  <Route path="/dashboard/graph" element={routeElement("Dashboard", <Dashboard />)} />
                  <Route path="/genesis" element={routeElement("Genesis", <Genesis />)} />
                  <Route path="/health" element={routeElement("Health Dashboard", <HealthDashboard />)} />
                  <Route path="/research" element={routeElement("Research", <ResearchEngine />)} />
                  <Route path="/seo" element={routeElement("SEO", <AiSeoTool />)} />
                  <Route path="/leadgen" element={routeElement("Lead Generation", <LeadGen />)} />
                  <Route path="/analytics" element={routeElement("Analytics", <AnalyticsPanel />)} />
                  <Route path="/freelance/dashboard" element={routeElement("Freelance Dashboard", <FreelanceDashboard />)} />
                  <Route path="/tasks" element={routeElement("Tasks", <TaskDashboard />)} />
                  <Route path="/masterplan" element={routeElement("MasterPlan", <MasterPlanDashboard />)} />
                  <Route path="/arm/analyze" element={routeElement("ARM Analyze", <ARMAnalyze />)} />
                  <Route path="/arm/generate" element={routeElement("ARM Generate", <ARMGenerate />)} />
                  <Route path="/arm/logs" element={routeElement("ARM Logs", <ARMLogs />)} />
                  <Route path="/arm/config" element={routeElement("ARM Config", <ARMConfig />)} />
                  <Route path="/network" element={routeElement("Network", <InfiniteNetwork />)} />
                  <Route path="/network/feed" element={routeElement("Feed", <Feed />)} />
                  <Route path="/social/profile/:username?" element={routeElement("Profile", <ProfileView />)} />
                  <Route path="/memory" element={routeElement("Memory", <MemoryBrowser />)} />
                  <Route path="/identity" element={routeElement("Identity", <IdentityDashboard />)} />
                  <Route path="/agent" element={routeElement("Agent Console", <AgentConsole />)} />
                  <Route element={<PlatformRoute />}>
                    <Route path="/console" element={routeElement("Execution Console", <ExecutionConsole />)} />
                    <Route path="/flow-console" element={routeElement("Flow Engine Console", <FlowEngineConsole />)} />
                    <Route path="/agents" element={routeElement("Agent Registry", <AgentRegistry />)} />
                    <Route path="/agent/approvals" element={routeElement("Agent Approvals", <AgentApprovalInbox />)} />
                    <Route path="/observability" element={routeElement("Observability", <ObservabilityDashboard />)} />
                    <Route path="/rippletrace" element={routeElement("RippleTrace", <RippleTraceViewer />)} />
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
