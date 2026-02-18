import { useState } from "react";
// Import all panels from the same directory
import EngagementPanel from "./EngagementPanel";
import AIEfficiencyPanel from "./AIEfficiencyPanel";
import ImpactPanel from "./ImpactPanel";
import RevenueScalingPanel from "./RevenueScalingPanel";
import ExecutionSpeedPanel from "./ExecutionSpeedPanel";
import AttentionValuePanel from "./AttentionValuePanel";
import IncomeEfficiencyPanel from "./IncomeEfficiencyPanel"; 
import MonetizationEfficiencyPanel from "./MonetizationEfficiencyPanel";
import BusinessGrowthPanel from "./BusinessGrowthPanel";
import EngagementRatePanel from "./EngagementRatePanel";
import AIProductivityBoostPanel from "./AIProductivityBoostPanel";
import DecisionEfficiencyPanel from "./DecisionEfficiencyPanel";
import LostPotentialPanel from "./LostPotentialPanel";

export default function ExecutionConsole() {
  // 1. Tab State
  const [activeTab, setActiveTab] = useState("core");

  // 2. Form States (for Core TWR)
  const [taskName, setTaskName] = useState("");
  const [timeSpent, setTimeSpent] = useState(1);
  const [complexity, setComplexity] = useState(3);
  const [skill, setSkill] = useState(3);
  const [aiUse, setAiUse] = useState(3);
  const [difficulty, setDifficulty] = useState(3);
  const [result, setResult] = useState(null);

  // --- Styles ---
  const containerStyle = {
    maxWidth: "800px",
    margin: "0 auto",
    padding: "20px",
    backgroundColor: "#000",
    color: "#eee",
    minHeight: "100vh",
    fontFamily: "sans-serif"
  };

  const navStyle = {
    display: "flex",
    gap: "10px",
    marginBottom: "30px",
    borderBottom: "1px solid #222",
    paddingBottom: "10px",
    overflowX: "auto" 
  };

  const tabButtonStyle = (id) => ({
    padding: "10px 20px",
    backgroundColor: activeTab === id ? "#007bff" : "transparent",
    color: activeTab === id ? "#fff" : "#777",
    border: "none",
    borderRadius: "6px",
    cursor: "pointer",
    fontWeight: "bold",
    whiteSpace: "nowrap",
    transition: "all 0.2s"
  });

  const sectionStyle = {
    backgroundColor: "#111",
    padding: "20px",
    borderRadius: "10px",
    border: "1px solid #222",
    marginBottom: "20px"
  };

  const inputStyle = {
    backgroundColor: "#222",
    color: "#fff",
    border: "1px solid #444",
    padding: "10px",
    borderRadius: "6px",
    width: "100%",
    marginTop: "5px",
    boxSizing: "border-box"
  };

  // --- Logic Handlers ---
  const handleReset = () => {
    setTaskName("");
    setTimeSpent(1);
    setComplexity(3);
    setSkill(3);
    setAiUse(3);
    setDifficulty(3);
    setResult(null);
  };

  const handleCalculate = async () => {
    try {
      const response = await fetch("http://localhost:8000/calculate_twr", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_name: taskName,
          time_spent: parseFloat(timeSpent),
          task_complexity: parseInt(complexity),
          skill_level: parseInt(skill),
          ai_utilization: parseInt(aiUse),
          task_difficulty: parseInt(difficulty)
        })
      });
      setResult(await response.json());
    } catch (err) { alert("TWR failed."); }
  };

  return (
    <div style={containerStyle}>
      <h2 style={{ marginBottom: "20px", color: "#00ffaa" }}>Execution Console</h2>

      {/* NAVIGATION TABS */}
      <div style={navStyle}>
        <button onClick={() => setActiveTab("core")} style={tabButtonStyle("core")}>Core Metrics</button>
        <button onClick={() => setActiveTab("efficiency")} style={tabButtonStyle("efficiency")}>AI & Speed</button>
        <button onClick={() => setActiveTab("growth")} style={tabButtonStyle("growth")}>Growth & Rev</button>
        <button onClick={() => setActiveTab("impact")} style={tabButtonStyle("impact")}>Social & Impact</button>
      </div>

      {/* TAB CONTENT */}
      <div>
        {activeTab === "core" && (
          <div style={sectionStyle}>
            <h4 style={{ color: "#999", textTransform: "uppercase", fontSize: "11px", marginBottom: "15px" }}>TWR Analysis</h4>
            <div style={{ marginBottom: "15px" }}>
              <label>Task Name</label>
              <input style={inputStyle} value={taskName} onChange={(e) => setTaskName(e.target.value)} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "15px", marginBottom: "20px" }}>
              <div><label>Time (Hrs)</label><input style={inputStyle} type="number" value={timeSpent} onChange={(e) => setTimeSpent(e.target.value)} /></div>
              <div><label>Skill (1-5)</label><input style={inputStyle} type="number" value={skill} onChange={(e) => setSkill(e.target.value)} /></div>
            </div>
            <div style={{ display: "flex", gap: "10px" }}>
              <button 
                onClick={handleCalculate} 
                style={{ flex: 2, padding: "12px", backgroundColor: "#007bff", color: "#fff", border: "none", borderRadius: "6px", fontWeight: "bold", cursor: "pointer" }}
              >
                Run Calculation
              </button>
              <button 
                onClick={handleReset} 
                style={{ flex: 1, padding: "12px", backgroundColor: "transparent", color: "#ff4d4d", border: "1px solid #422", borderRadius: "6px", cursor: "pointer" }}
              >
                Reset
              </button>
            </div>
            
            {result && (
              <div style={{ marginTop: "20px", padding: "15px", backgroundColor: "#0a0a0a", borderRadius: "8px", border: "1px solid #333" }}>
                <pre style={{ color: "#64b5f6", fontSize: "13px", whiteSpace: "pre-wrap" }}>
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}

        {activeTab === "efficiency" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <AIEfficiencyPanel />
            <AIProductivityBoostPanel /> 
            <DecisionEfficiencyPanel /> 
            <ExecutionSpeedPanel />
          </div>
        )}

        {activeTab === "growth" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <IncomeEfficiencyPanel /> 
            <RevenueScalingPanel />
            <BusinessGrowthPanel /> 
            <MonetizationEfficiencyPanel /> 
            <LostPotentialPanel /> 
            <AttentionValuePanel />
          </div>
        )}

        {activeTab === "impact" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
            <EngagementPanel />
            <ImpactPanel />
          </div>
        )}
      </div>
    </div>
  );
}