import React, { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { getAgentRuns } from "../api";
import { APPROVAL_EVENT } from "./AgentApprovalInbox";

const SubNavItem = ({ to, children, active, badge }) => (
  <Link
    to={to}
    className={`mb-1 flex items-center justify-between gap-3 rounded-lg px-10 py-2 text-xs font-medium transition-all duration-200 ${
      active
        ? "bg-[#00ffaa]/5 text-[#00ffaa]"
        : "text-zinc-500 hover:bg-zinc-800/30 hover:text-zinc-200"
    }`}
  >
    <span>{children}</span>
    {badge ? (
      <span className="rounded-full bg-[#00ffaa] px-2 py-0.5 text-[10px] font-bold text-black">
        {badge}
      </span>
    ) : null}
  </Link>
);

const NavSection = ({ title, icon, isOpen, toggle, children, isAnyChildActive }) => (
  <div className="mb-2">
    <button
      onClick={toggle}
      className={`w-full rounded-xl px-4 py-3 transition-all duration-200 ${
        isAnyChildActive
          ? "bg-zinc-900/50 text-white"
          : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-sm font-semibold">
          <span>{icon}</span>
          <span>{title}</span>
        </div>
        <span className={`text-[10px] transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}>
          ▼
        </span>
      </div>
    </button>
    {isOpen ? <div className="mt-1 flex animate-in flex-col slide-in-from-top-2 duration-200">{children}</div> : null}
  </div>
);

export default function Sidebar() {
  const location = useLocation();
  const [openSection, setOpenSection] = useState("System");
  const [pendingApprovals, setPendingApprovals] = useState(0);

  const isActive = (path) => location.pathname === path || location.pathname.startsWith(`${path}/`);

  const toggleSection = (name) => {
    setOpenSection((current) => (current === name ? null : name));
  };

  const loadPendingApprovals = useCallback(async () => {
    try {
      const runs = await getAgentRuns("pending_approval", 100);
      setPendingApprovals(Array.isArray(runs) ? runs.length : 0);
    } catch {
      setPendingApprovals(0);
    }
  }, []);

  useEffect(() => {
    loadPendingApprovals();
    const interval = window.setInterval(loadPendingApprovals, 30000);
    const onApprovalCountChange = () => loadPendingApprovals();
    window.addEventListener(APPROVAL_EVENT, onApprovalCountChange);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener(APPROVAL_EVENT, onApprovalCountChange);
    };
  }, [loadPendingApprovals]);

  return (
    <aside className="flex h-screen w-72 flex-shrink-0 flex-col border-r border-zinc-800/50 bg-[#0c0c0e] p-4">
      <div className="mb-10 mt-4 px-3">
        <h3 className="text-2xl font-black italic tracking-tighter text-[#00ffaa]">
          AINDY<span className="not-italic text-zinc-500">.OS</span>
        </h3>
      </div>

      <nav className="custom-scrollbar flex-1 overflow-y-auto pr-2">
        <Link
          to="/dashboard"
          className={`mb-2 flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-bold transition-all ${
            location.pathname === "/dashboard"
              ? "bg-[#00ffaa] text-black shadow-[0_0_20px_rgba(0,255,170,0.2)]"
              : "text-zinc-400 hover:bg-zinc-800/50"
          }`}
        >
          🏠 Dashboard
        </Link>

        <Link
          to="/genesis"
          className={`mb-6 flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-bold transition-all ${
            isActive("/genesis")
              ? "bg-white text-black"
              : "text-zinc-400 hover:bg-zinc-800/50"
          }`}
        >
          ✨ Genesis
        </Link>

        <NavSection
          title="Social Layer"
          icon="📡"
          isOpen={openSection === "Social"}
          toggle={() => toggleSection("Social")}
          isAnyChildActive={isActive("/network") || isActive("/social")}
        >
          <SubNavItem to="/network/feed" active={isActive("/network/feed")}>Trust Feed</SubNavItem>
          <SubNavItem to="/social/profile/me" active={isActive("/social/profile")}>My Identity</SubNavItem>
          <SubNavItem to="/network" active={location.pathname === "/network"}>Infinite Network</SubNavItem>
        </NavSection>

        <NavSection
          title="Intelligence"
          icon="🔍"
          isOpen={openSection === "Tools"}
          toggle={() => toggleSection("Tools")}
          isAnyChildActive={isActive("/research") || isActive("/seo") || isActive("/leadgen")}
        >
          <SubNavItem to="/research" active={isActive("/research")}>Research Engine</SubNavItem>
          <SubNavItem to="/seo" active={isActive("/seo")}>SEO Tool</SubNavItem>
          <SubNavItem to="/leadgen" active={isActive("/leadgen")}>LeadGen</SubNavItem>
          <SubNavItem to="/analytics" active={isActive("/analytics")}>Analytics</SubNavItem>
        </NavSection>

        <NavSection
          title="System"
          icon="⚙️"
          isOpen={openSection === "System"}
          toggle={() => toggleSection("System")}
          isAnyChildActive={
            isActive("/masterplan") ||
            isActive("/tasks") ||
            isActive("/console") ||
            isActive("/agent") ||
            isActive("/freelance/dashboard") ||
            isActive("/observability") ||
            isActive("/rippletrace")
          }
        >
          <SubNavItem to="/masterplan" active={isActive("/masterplan")}>Master Plan</SubNavItem>
          <SubNavItem to="/tasks" active={isActive("/tasks")}>Execution Engine</SubNavItem>
          <SubNavItem to="/console" active={isActive("/console")}>Console</SubNavItem>
          <SubNavItem to="/agent" active={location.pathname === "/agent"}>Agent Console</SubNavItem>
          <SubNavItem to="/agent/approvals" active={isActive("/agent/approvals")} badge={pendingApprovals || null}>
            Approval Inbox
          </SubNavItem>
          <SubNavItem to="/observability" active={isActive("/observability")}>Observability</SubNavItem>
          <SubNavItem to="/rippletrace" active={isActive("/rippletrace")}>Ripple Trace</SubNavItem>
          <SubNavItem to="/freelance/dashboard" active={isActive("/freelance/dashboard")}>Freelance Hub</SubNavItem>
        </NavSection>

        <NavSection
          title="ARM Module"
          icon="🧠"
          isOpen={openSection === "ARM"}
          toggle={() => toggleSection("ARM")}
          isAnyChildActive={isActive("/arm")}
        >
          <SubNavItem to="/arm/analyze" active={isActive("/arm/analyze")}>Analyze</SubNavItem>
          <SubNavItem to="/arm/generate" active={isActive("/arm/generate")}>Generate</SubNavItem>
          <SubNavItem to="/arm/logs" active={isActive("/arm/logs")}>System Logs</SubNavItem>
          <SubNavItem to="/arm/config" active={isActive("/arm/config")}>Config</SubNavItem>
        </NavSection>

        <NavSection
          title="Memory"
          icon="💾"
          isOpen={openSection === "Memory"}
          toggle={() => toggleSection("Memory")}
          isAnyChildActive={isActive("/memory") || isActive("/identity") || isActive("/agents")}
        >
          <SubNavItem to="/memory" active={isActive("/memory")}>Memory Browser</SubNavItem>
          <SubNavItem to="/identity" active={isActive("/identity")}>Identity Profile</SubNavItem>
          <SubNavItem to="/agents" active={isActive("/agents")}>Agent Federation</SubNavItem>
        </NavSection>
      </nav>

      <div className="mt-auto border-t border-zinc-800/50 pt-4">
        <Link to="/health" className="flex items-center gap-3 px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-[#00ffaa]">
          🟢 System Online
        </Link>
      </div>
    </aside>
  );
}
