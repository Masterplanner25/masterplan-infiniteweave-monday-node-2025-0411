import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";

// --- COMPONENT IMPORTS ---
import Sidebar from "./components/Sidebar"; // Extracting this makes the file manageable
import Dashboard from "./components/Dashboard";
import HealthDashboard from "./components/HealthDashboard";
import ResearchEngine from "./components/ResearchEngine";
import AiSeoTool from "./components/AiSeoTool";
import InfiniteNetwork from "./components/InfiniteNetwork";
import LeadGen from "./components/LeadGen";
import FreelanceDashboard from "./components/FreelanceDashboard";
import TaskDashboard from "./components/TaskDashboard";
import MasterPlanDashboard from "./components/MasterPlanDashboard";
import ExecutionConsole from "./components/ExecutionConsole";
import AnalyticsPanel from "./components/AnalyticsPanel";
import Genesis from "./components/Genesis";

// ARM Components
import ARMAnalyze from "./components/ARMAnalyze";
import ARMGenerate from "./components/ARMGenerate";
import ARMLogs from "./components/ARMLogs";
import ARMConfig from "./components/ARMConfig";

// Social Layer
import ProfileView from "./components/ProfileView";
import Feed from "./components/Feed";

import "./App.css";

export default function App() {
  return (
    <TooltipProvider>
      {/* Future flags enabled for React Router v7 compatibility 
      */}
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <div className="flex min-h-screen bg-[#09090b] text-[#fafafa] font-sans selection:bg-[#00ffaa]/30">
          
          {/* Global Styles Injector */}
          <style dangerouslySetInnerHTML={{ __html: `
            body { margin: 0; padding: 0; background: #09090b; overflow: hidden; }
            * { box-sizing: border-box; }
            .custom-scrollbar::-webkit-scrollbar { width: 4px; }
            .custom-scrollbar::-webkit-scrollbar-thumb { background: #27272a; border-radius: 10px; }
            .main-content-gradient { background: linear-gradient(135deg, #09090b 0%, #0c0c0e 100%); }
          `}} />

          {/* Navigation Sidebar */}
          <Sidebar />
          
          {/* Main Viewport */}
          <main className="flex-1 h-screen overflow-y-auto p-10 main-content-gradient custom-scrollbar">
            <Routes>
              {/* Default Redirect */}
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              
              {/* Core Dashboards */}
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/genesis" element={<Genesis />} />
              <Route path="/health" element={<HealthDashboard />} />
              
              {/* Intelligence & Tools */}
              <Route path="/research" element={<ResearchEngine />} />
              <Route path="/seo" element={<AiSeoTool />} />
              <Route path="/leadgen" element={<LeadGen />} />
              <Route path="/analytics" element={<AnalyticsPanel />} />
              <Route path="/freelance/dashboard" element={<FreelanceDashboard />} />
              
              {/* System & Execution */}
              <Route path="/tasks" element={<TaskDashboard />} />
              <Route path="/masterplan" element={<MasterPlanDashboard />} />
              <Route path="/console" element={<ExecutionConsole />} />
              
              {/* Autonomous Reasoning Module (ARM) */}
              <Route path="/arm/analyze" element={<ARMAnalyze />} />
              <Route path="/arm/generate" element={<ARMGenerate />} />
              <Route path="/arm/logs" element={<ARMLogs />} />
              <Route path="/arm/config" element={<ARMConfig />} />
              
              {/* Social & Networking */}
              <Route path="/network" element={<InfiniteNetwork />} />
              <Route path="/network/feed" element={<Feed />} />
              <Route path="/social/profile/:username?" element={<ProfileView />} />
              
              {/* Catch-all Redirect */}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </TooltipProvider>
  );
}