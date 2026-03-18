import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";

// --- SUB-ITEM COMPONENT ---
const SubNavItem = ({ to, children, active }) => (
  <Link 
    to={to} 
    className={`flex items-center gap-3 px-10 py-2 rounded-lg transition-all duration-200 text-xs font-medium mb-1
      ${active 
        ? "text-[#00ffaa] bg-[#00ffaa]/5" 
        : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/30"}`}
  >
    {children}
  </Link>
);

// --- COLLAPSIBLE SECTION COMPONENT ---
const NavSection = ({ title, icon, isOpen, toggle, children, isAnyChildActive }) => (
  <div className="mb-2">
    <button 
      onClick={toggle}
      className={`w-full flex items-center justify-between px-4 py-3 rounded-xl transition-all duration-200
        ${isAnyChildActive ? "bg-zinc-900/50 text-white" : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"}`}
    >
      <div className="flex items-center gap-3 font-semibold text-sm">
        <span>{icon}</span>
        <span>{title}</span>
      </div>
      <span className={`text-[10px] transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}>
        ▼
      </span>
    </button>
    
    {isOpen && (
      <div className="mt-1 flex flex-col animate-in slide-in-from-top-2 duration-200">
        {children}
      </div>
    )}
  </div>
);

export default function Sidebar() {
  const location = useLocation();
  const [openSection, setOpenSection] = useState("System"); // Default open section

  const isActive = (path) => location.pathname === path || location.pathname.startsWith(path + "/");
  
  const toggleSection = (name) => {
    setOpenSection(openSection === name ? null : name);
  };

  return (
    <aside className="w-72 h-screen flex flex-col bg-[#0c0c0e] border-r border-zinc-800/50 p-4 flex-shrink-0">
      <div className="px-3 mb-10 mt-4">
        <h3 className="text-[#00ffaa] font-black tracking-tighter text-2xl italic">
          AINDY<span className="text-zinc-500 not-italic">.OS</span>
        </h3>
      </div>

      <nav className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
        {/* TOP LEVEL: DASHBOARD & GENESIS */}
        <Link 
          to="/dashboard" 
          className={`flex items-center gap-3 px-4 py-3 rounded-xl mb-2 text-sm font-bold transition-all
            ${location.pathname === "/dashboard" ? "bg-[#00ffaa] text-black shadow-[0_0_20px_rgba(0,255,170,0.2)]" : "text-zinc-400 hover:bg-zinc-800/50"}`}
        >
          🏠 Dashboard
        </Link>

        <Link 
          to="/genesis" 
          className={`flex items-center gap-3 px-4 py-3 rounded-xl mb-6 text-sm font-bold transition-all
            ${isActive("/genesis") ? "bg-white text-black" : "text-zinc-400 hover:bg-zinc-800/50"}`}
        >
          ✨ Genesis
        </Link>

        {/* SECTION: SOCIAL LAYER */}
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

        {/* SECTION: INTELLIGENCE */}
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

        {/* SECTION: SYSTEM */}
        <NavSection 
          title="System" 
          icon="⚙️" 
          isOpen={openSection === "System"} 
          toggle={() => toggleSection("System")}
          isAnyChildActive={isActive("/masterplan") || isActive("/tasks") || isActive("/console")}
        >
          <SubNavItem to="/masterplan" active={isActive("/masterplan")}>Master Plan</SubNavItem>
          <SubNavItem to="/tasks" active={isActive("/tasks")}>Execution Engine</SubNavItem>
          <SubNavItem to="/console" active={isActive("/console")}>Console</SubNavItem>
          <SubNavItem to="/freelance/dashboard" active={isActive("/freelance/dashboard")}>Freelance Hub</SubNavItem>
        </NavSection>

        {/* SECTION: ARM */}
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
      </nav>
      
      <div className="mt-auto pt-4 border-t border-zinc-800/50">
        <Link to="/health" className="flex items-center gap-3 px-4 py-2 text-[10px] font-bold text-[#00ffaa] uppercase tracking-widest">
          🟢 System Online
        </Link>
      </div>
    </aside>
  );
}