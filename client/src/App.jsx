import React from "react";
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/shared/ui/tooltip";

// --- COMPONENT IMPORTS ---
import Sidebar from "./components/shared/Sidebar"; // Extracting this makes the file manageable
import Dashboard from "./components/app/Dashboard";
import HealthDashboard from "./components/platform/HealthDashboard";
import ResearchEngine from "./components/app/ResearchEngine";
import AiSeoTool from "./components/app/AiSeoTool";
import InfiniteNetwork from "./components/app/InfiniteNetwork";
import LeadGen from "./components/app/LeadGen";
import FreelanceDashboard from "./components/app/FreelanceDashboard";
import TaskDashboard from "./components/app/TaskDashboard";
import MasterPlanDashboard from "./components/app/MasterPlanDashboard";
import ExecutionConsole from "./components/platform/ExecutionConsole";
import FlowEngineConsole from "./components/platform/FlowEngineConsole";
import AnalyticsPanel from "./components/app/AnalyticsPanel";
import Genesis from "./components/app/Genesis";
import AgentApprovalInbox from "./components/platform/AgentApprovalInbox";
import ObservabilityDashboard from "./components/platform/ObservabilityDashboard";
import RippleTraceViewer from "./components/platform/RippleTraceViewer";
import LoginPage from "./components/shared/LoginPage";
import RegisterPage from "./pages/Register";
import { useAuth } from "./context/AuthContext";
import { useSystem } from "./context/SystemContext";

// ARM Components
import ARMAnalyze from "./components/app/ARMAnalyze";
import ARMGenerate from "./components/app/ARMGenerate";
import ARMLogs from "./components/app/ARMLogs";
import ARMConfig from "./components/app/ARMConfig";

// Social Layer
import ProfileView from "./components/app/ProfileView";
import Feed from "./components/app/Feed";

// Agent
import AgentConsole from "./components/platform/AgentConsole";

// Memory Layer
import MemoryBrowser from "./components/app/MemoryBrowser";
import IdentityDashboard from "./components/app/IdentityDashboard";
import AgentRegistry from "./components/platform/AgentRegistry";

import "./App.css";

function ProtectedRoute() {
  const location = useLocation();
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}

function PlatformRoute() {
  const location = useLocation();
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (!user?.is_admin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
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
      <style dangerouslySetInnerHTML={{ __html: `
            body { margin: 0; padding: 0; background: #09090b; overflow: hidden; }
            * { box-sizing: border-box; }
            .custom-scrollbar::-webkit-scrollbar { width: 4px; }
            .custom-scrollbar::-webkit-scrollbar-thumb { background: #27272a; border-radius: 10px; }
            .main-content-gradient { background: linear-gradient(135deg, #09090b 0%, #0c0c0e 100%); }
          `}} />
      <Sidebar />
      <main className="flex-1 h-screen overflow-y-auto p-10 main-content-gradient custom-scrollbar">
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <TooltipProvider>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<BootGate />}>
              <Route element={<AppShell />}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/dashboard/graph" element={<Dashboard />} />
                <Route path="/genesis" element={<Genesis />} />
                <Route path="/health" element={<HealthDashboard />} />
                <Route path="/research" element={<ResearchEngine />} />
                <Route path="/seo" element={<AiSeoTool />} />
                <Route path="/leadgen" element={<LeadGen />} />
                <Route path="/analytics" element={<AnalyticsPanel />} />
                <Route path="/freelance/dashboard" element={<FreelanceDashboard />} />
                <Route path="/tasks" element={<TaskDashboard />} />
                <Route path="/masterplan" element={<MasterPlanDashboard />} />
                <Route path="/arm/analyze" element={<ARMAnalyze />} />
                <Route path="/arm/generate" element={<ARMGenerate />} />
                <Route path="/arm/logs" element={<ARMLogs />} />
                <Route path="/arm/config" element={<ARMConfig />} />
                <Route path="/network" element={<InfiniteNetwork />} />
                <Route path="/network/feed" element={<Feed />} />
                <Route path="/social/profile/:username?" element={<ProfileView />} />
                <Route path="/memory" element={<MemoryBrowser />} />
                <Route path="/identity" element={<IdentityDashboard />} />
                <Route path="/agent" element={<AgentConsole />} />
                <Route element={<PlatformRoute />}>
                  <Route path="/console" element={<ExecutionConsole />} />
                  <Route path="/flow-console" element={<FlowEngineConsole />} />
                  <Route path="/agents" element={<AgentRegistry />} />
                  <Route path="/agent/approvals" element={<AgentApprovalInbox />} />
                  <Route path="/observability" element={<ObservabilityDashboard />} />
                  <Route path="/rippletrace" element={<RippleTraceViewer />} />
                </Route>
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Route>
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  );
}
