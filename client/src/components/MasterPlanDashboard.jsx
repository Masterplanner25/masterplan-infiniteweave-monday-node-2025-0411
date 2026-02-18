import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom"; // Added for linking to Genesis

export default function MasterPlanDashboard() {
  const navigate = useNavigate(); // Navigation hook
  const [plans, setPlans] = useState([]);
  const [version, setVersion] = useState("");
  const [startDate, setStartDate] = useState("");
  const [durationYears, setDurationYears] = useState(5);
  const [isOrigin, setIsOrigin] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [wcuTarget, setWcuTarget] = useState(3000);
  const [revenueTarget, setRevenueTarget] = useState(100000);
  const [booksRequired, setBooksRequired] = useState(3);
  const [playbooksRequired, setPlaybooksRequired] = useState(2);
  const [studioRequired, setStudioRequired] = useState(true);
  const [platformRequired, setPlatformRequired] = useState(true);

  // --- REUSABLE STYLES (Matching your new OS theme) ---
  const inputStyle = {
    backgroundColor: "#18181b",
    color: "#fff",
    border: "1px solid #27272a",
    padding: "10px",
    borderRadius: "6px",
    width: "100%",
    marginTop: "5px",
    fontSize: "14px",
    boxSizing: "border-box"
  };

  const labelStyle = {
    display: "block",
    marginBottom: "12px",
    color: "#a1a1aa",
    fontSize: "12px",
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: "0.05em"
  };

  const fetchPlans = () => {
    fetch("http://localhost:8000/masterplans")
      .then(res => res.json())
      .then(data => setPlans(data))
      .catch(err => console.error("Error fetching plans:", err));
  };

  useEffect(() => {
    fetchPlans();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const response = await fetch("http://localhost:8000/create_masterplan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        version,
        start_date: startDate,
        duration_years: parseFloat(durationYears),
        is_origin: isOrigin,
        is_active: isActive,
        wcu_target: parseFloat(wcuTarget),
        revenue_target: parseFloat(revenueTarget),
        books_required: parseInt(booksRequired),
        playbooks_required: parseInt(playbooksRequired),
        studio_required: studioRequired,
        platform_required: platformRequired
      })
    });

    if (response.ok) {
      fetchPlans();
      setVersion("");
      setStartDate("");
      setDurationYears(5);
      setIsOrigin(false);
      setIsActive(false);
    } else {
      const error = await response.json();
      alert(error.detail || "Error creating master plan");
    }
  };

  return (
    <div style={{ color: "#fff", backgroundColor: "transparent" }}>
      
      {/* --- HEADER SECTION --- */}
      <div style={{ 
        display: "flex", 
        justifyContent: "space-between", 
        alignItems: "flex-end", 
        marginBottom: "40px",
        borderBottom: "1px solid #27272a",
        paddingBottom: "24px"
      }}>
        <div>
          <h2 style={{ fontSize: "2.5rem", fontWeight: "900", margin: 0, letterSpacing: "-0.02em" }}>
            MASTER <span style={{ color: "#00ffaa" }}>PLANS</span>
          </h2>
          <p style={{ color: "#71717a", margin: "8px 0 0 0" }}>Architect and monitor your long-term strategic evolution.</p>
        </div>

        {/* BRIDGE TO GENESIS */}
        <button 
          onClick={() => navigate("/genesis")}
          style={{
            padding: "12px 24px",
            backgroundColor: "#00ffaa",
            color: "#000",
            border: "none",
            borderRadius: "8px",
            cursor: "pointer",
            fontWeight: "800",
            fontSize: "13px",
            textTransform: "uppercase",
            boxShadow: "0 0 20px rgba(0, 255, 170, 0.2)",
            transition: "all 0.2s ease"
          }}
        >
          ✨ Initialize via Genesis
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "350px 1fr", gap: "48px", alignItems: "start" }}>
        
        {/* --- LEFT COLUMN: CREATE FORM --- */}
        <section>
          <form onSubmit={handleSubmit} style={{
            padding: "24px",
            border: "1px solid #27272a",
            borderRadius: "12px",
            background: "linear-gradient(180deg, #0c0c0e 0%, #09090b 100%)",
          }}>
            <h3 style={{ marginTop: 0, marginBottom: "20px", fontSize: "16px", color: "#f4f4f5" }}>New Configuration</h3>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <label style={labelStyle}>Version <input style={inputStyle} placeholder="V1" value={version} onChange={(e) => setVersion(e.target.value)} required /></label>
              <label style={labelStyle}>Start Date <input style={inputStyle} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required /></label>
            </div>

            <label style={labelStyle}>Duration (Years) <input style={inputStyle} type="number" step="0.1" value={durationYears} onChange={(e) => setDurationYears(e.target.value)} required /></label>
            
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <label style={labelStyle}>WCU Target <input style={inputStyle} type="number" value={wcuTarget} onChange={(e) => setWcuTarget(e.target.value)} /></label>
              <label style={labelStyle}>Revenue Target <input style={inputStyle} type="number" value={revenueTarget} onChange={(e) => setRevenueTarget(e.target.value)} /></label>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", margin: "20px 0", padding: "12px", backgroundColor: "#18181b", borderRadius: "8px" }}>
              <label style={{ fontSize: "12px", display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input type="checkbox" checked={studioRequired} onChange={(e) => setStudioRequired(e.target.checked)} /> Studio
              </label>
              <label style={{ fontSize: "12px", display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input type="checkbox" checked={platformRequired} onChange={(e) => setPlatformRequired(e.target.checked)} /> Platform
              </label>
              <label style={{ fontSize: "12px", display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input type="checkbox" checked={isOrigin} onChange={(e) => setIsOrigin(e.target.checked)} /> Origin
              </label>
              <label style={{ fontSize: "12px", display: "flex", alignItems: "center", gap: "6px", cursor: "pointer" }}>
                <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> Active
              </label>
            </div>

            <button type="submit" style={{
              width: "100%",
              padding: "12px",
              backgroundColor: "#27272a",
              color: "white",
              border: "1px solid #3f3f46",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: "600",
              fontSize: "14px",
              transition: "background 0.2s"
            }}>
              Create Manual Entry
            </button>
          </form>
        </section>

        {/* --- RIGHT COLUMN: ACTIVE PLANS --- */}
        <section>
          <h3 style={{ marginTop: 0, marginBottom: "20px", fontSize: "16px", color: "#f4f4f5" }}>Deployment Log</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "16px" }}>
            {plans.length === 0 && (
              <div style={{ gridColumn: "1/-1", padding: "40px", border: "2px dashed #27272a", borderRadius: "12px", textAlign: "center", color: "#52525b" }}>
                No active master plans found. Start by initializing Genesis.
              </div>
            )}

            {plans.map(plan => (
              <div key={plan.id} style={{
                padding: "20px",
                border: "1px solid #27272a",
                borderRadius: "12px",
                background: plan.is_active ? "rgba(0, 255, 170, 0.03)" : "#0c0c0e",
                position: "relative",
                transition: "transform 0.2s ease"
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                  <span style={{ fontWeight: "900", color: "#00ffaa" }}>{plan.version}</span>
                  <span style={{ fontSize: "10px", color: plan.is_active ? "#00ffaa" : "#52525b", border: "1px solid currentColor", padding: "2px 6px", borderRadius: "4px" }}>
                    {plan.is_active ? "ACTIVE" : "ARCHIVED"}
                  </span>
                </div>
                
                <div style={{ spaceY: "8px", fontSize: "13px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                    <span style={{ color: "#71717a" }}>WCU Progress</span>
                    <span>{plan.total_wcu} / {plan.wcu_target}</span>
                  </div>
                  <div style={{ width: "100%", height: "4px", backgroundColor: "#18181b", borderRadius: "2px", marginBottom: "12px" }}>
                    <div style={{ width: `${Math.min((plan.total_wcu / plan.wcu_target) * 100, 100)}%`, height: "100%", backgroundColor: "#00ffaa", borderRadius: "2px" }} />
                  </div>

                  <p style={{ margin: "4px 0", color: "#a1a1aa" }}><strong>Start:</strong> {new Date(plan.start_date).toLocaleDateString()}</p>
                  <p style={{ margin: "4px 0", color: "#a1a1aa" }}><strong>Revenue:</strong> ${plan.gross_revenue?.toLocaleString()}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

      </div>
    </div>
  );
}
