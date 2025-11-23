import React from "react";
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";

// --- COMPONENTS ---
import Dashboard from "./components/Dashboard";
import HealthDashboard from "./components/HealthDashboard";
import ResearchEngine from "./components/ResearchEngine";
import AiSeoTool from "./components/AiSeoTool";
import InfiniteNetwork from "./components/InfiniteNetwork";
import LeadGen from "./components/LeadGen";
import FreelanceDashboard from "./components/FreelanceDashboard";
import TaskDashboard from "./components/TaskDashboard";

// ARM Components
import ARMAnalyze from "./components/ARMAnalyze";
import ARMGenerate from "./components/ARMGenerate";
import ARMLogs from "./components/ARMLogs";
import ARMConfig from "./components/ARMConfig";

// ✅ NEW SOCIAL LAYER COMPONENTS
import ProfileView from "./components/ProfileView";
import Feed from "./components/Feed";

import "./App.css";

// --- SIDEBAR COMPONENT ---
function Sidebar() {
  const location = useLocation();
  // Helper to check if path is active
  const isActive = (path) => location.pathname.startsWith(path);

  return (
    <aside style={styles.sidebar}>
      <h3 style={{ marginBottom: "2rem", color: "#00ffaa", fontWeight: "bold", letterSpacing: "1px" }}>
        A.I.N.D.Y.
      </h3>

      <nav style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <NavItem to="/dashboard" active={location.pathname === "/dashboard"}>Dashboard</NavItem>
        
        {/* --- SOCIAL LAYER SECTION --- */}
        <div style={styles.sectionHeader}>
          Social Layer
        </div>
        <NavItem to="/network/feed" active={isActive("/network/feed")}>📡 Trust Feed</NavItem>
        <NavItem to="/social/profile/me" active={isActive("/social/profile")}>👤 My Identity</NavItem>

        {/* --- TOOLS SECTION --- */}
        <div style={styles.sectionHeader}>
          Tools
        </div>
        <NavItem to="/research" active={isActive("/research")}>Research Engine</NavItem>
        <NavItem to="/leadgen" active={isActive("/leadgen")}>LeadGen</NavItem>
        <NavItem to="/freelance/dashboard" active={isActive("/freelance/dashboard")}>Freelance Hub</NavItem>
        <NavItem to="/health" active={isActive("/health")}>Health Status</NavItem>
        <NavItem to="/seo" active={isActive("/seo")}>SEO Tool</NavItem>
        <NavItem to="/network" active={isActive("/network")}>Network Graph</NavItem>
        <NavItem to="/tasks" active={isActive("/tasks")}>🚀 Execution Engine</NavItem>

        {/* --- ARM SECTION --- */}
        <div style={styles.sectionHeader}>
          Autonomous Reasoning
        </div>
        <NavItem to="/arm/analyze" active={isActive("/arm/analyze")}>ARM Analyze</NavItem>
        <NavItem to="/arm/generate" active={isActive("/arm/generate")}>ARM Generate</NavItem>
        <NavItem to="/arm/logs" active={isActive("/arm/logs")}>ARM Logs</NavItem>
        <NavItem to="/arm/config" active={isActive("/arm/config")}>ARM Config</NavItem>
      </nav>
    </aside>
  );
}

// Helper component for Links
const NavItem = ({ to, children, active }) => (
  <Link 
    to={to} 
    style={{
      ...styles.link,
      background: active ? "rgba(0, 255, 170, 0.1)" : "transparent",
      color: active ? "#00ffaa" : "#b0b0b0",
      borderLeft: active ? "3px solid #00ffaa" : "3px solid transparent",
    }}
  >
    {children}
  </Link>
);

// --- MAIN APP COMPONENT ---
export default function App() {
  return (
    <TooltipProvider>
      <BrowserRouter>
        <div style={styles.app}>
          {/* Inline styles reset for preview environment */}
          <style>{`
            body { margin: 0; padding: 0; background: #0b0b0b; }
            * { box-sizing: border-box; }
          `}</style>

          <Sidebar />
          
          <main style={styles.main}>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/health" element={<HealthDashboard />} />
              <Route path="/research" element={<ResearchEngine />} />
              <Route path="/seo" element={<AiSeoTool />} />
              <Route path="/network" element={<InfiniteNetwork />} />
              <Route path="/leadgen" element={<LeadGen />} />
              <Route path="/freelance/dashboard" element={<FreelanceDashboard />} />
              <Route path="/tasks" element={<TaskDashboard />} />

              {/* ARM Routes */}
              <Route path="/arm/analyze" element={<ARMAnalyze />} />
              <Route path="/arm/generate" element={<ARMGenerate />} />
              <Route path="/arm/logs" element={<ARMLogs />} />
              <Route path="/arm/config" element={<ARMConfig />} />

              {/* ✅ Social Layer Routes */}
              <Route path="/network/feed" element={<Feed />} />
              <Route path="/social/profile/:username?" element={<ProfileView />} />

            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </TooltipProvider>
  );
}

// --- STYLES ---
const styles = {
  app: { 
    display: "flex", 
    minHeight: "100vh", 
    fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
    background: "#0b0b0b", 
    color: "#eaeaea"
  },
  sidebar: { 
    width: 260, 
    padding: "24px", 
    borderRight: "1px solid #222", 
    background: "#111",
    display: "flex",
    flexDirection: "column",
    flexShrink: 0,
    overflowY: "auto", 
    height: "100vh"
  },
  main: { 
    flex: 1, 
    padding: "32px 48px", 
    background: "#0b0b0b", 
    overflowY: "auto",
    height: "100vh"
  },
  link: { 
    textDecoration: "none", 
    padding: "10px 16px", 
    display: "block",
    borderRadius: "0 6px 6px 0",
    transition: "all 0.2s ease",
    fontSize: "14px",
    fontWeight: "500"
  },
  sectionHeader: { 
    fontSize: 11, 
    color: "#666", 
    marginTop: 16, 
    marginBottom: 8, 
    textTransform: "uppercase", 
    letterSpacing: "1.5px", 
    fontWeight: "600" 
  }
};