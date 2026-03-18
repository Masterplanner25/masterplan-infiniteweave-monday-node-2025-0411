import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listMasterPlans, activateMasterPlan } from "../api.js";

const STATUS_BADGE = {
  active:   { label: "ACTIVE",   color: "#00ffaa" },
  locked:   { label: "LOCKED",   color: "#facc15" },
  draft:    { label: "DRAFT",    color: "#71717a" },
  archived: { label: "ARCHIVED", color: "#52525b" },
};

function StatusBadge({ status, isActive }) {
  const key = isActive ? "active" : (status || "draft");
  const badge = STATUS_BADGE[key] || STATUS_BADGE.draft;
  return (
    <span style={{
      fontSize: "10px",
      color: badge.color,
      border: `1px solid ${badge.color}`,
      padding: "2px 6px",
      borderRadius: "4px",
    }}>
      {badge.label}
    </span>
  );
}

export default function MasterPlanDashboard() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activating, setActivating] = useState(null);

  const fetchPlans = async () => {
    setLoading(true);
    try {
      const data = await listMasterPlans();
      setPlans(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Error fetching plans:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlans();
  }, []);

  const handleActivate = async (planId) => {
    setActivating(planId);
    try {
      await activateMasterPlan(planId);
      await fetchPlans();
    } catch (err) {
      alert("Activation failed: " + err.message);
    } finally {
      setActivating(null);
    }
  };

  return (
    <div style={{ color: "#fff", backgroundColor: "transparent" }}>

      {/* HEADER */}
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
          <p style={{ color: "#71717a", margin: "8px 0 0 0" }}>
            Architect and monitor your long-term strategic evolution.
          </p>
        </div>
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
          }}
        >
          Initialize via Genesis
        </button>
      </div>

      {/* PLAN GRID */}
      <section>
        <h3 style={{ marginTop: 0, marginBottom: "20px", fontSize: "16px", color: "#f4f4f5" }}>
          Deployment Log
        </h3>
        {loading ? (
          <p style={{ color: "#52525b" }}>Loading plans...</p>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "16px" }}>
            {plans.length === 0 && (
              <div style={{
                gridColumn: "1/-1",
                padding: "40px",
                border: "2px dashed #27272a",
                borderRadius: "12px",
                textAlign: "center",
                color: "#52525b"
              }}>
                No master plans found. Start by initializing Genesis.
              </div>
            )}

            {plans.map(plan => (
              <div key={plan.id} style={{
                padding: "20px",
                border: "1px solid #27272a",
                borderRadius: "12px",
                background: plan.is_active ? "rgba(0, 255, 170, 0.03)" : "#0c0c0e",
                position: "relative",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "12px" }}>
                  <span style={{ fontWeight: "900", color: "#00ffaa" }}>
                    {plan.version_label || plan.version || `#${plan.id}`}
                  </span>
                  <StatusBadge status={plan.status} isActive={plan.is_active} />
                </div>

                <div style={{ fontSize: "13px" }}>
                  {plan.posture && (
                    <p style={{ margin: "4px 0", color: "#a1a1aa" }}>
                      <strong>Posture:</strong> {plan.posture}
                    </p>
                  )}
                  {plan.created_at && (
                    <p style={{ margin: "4px 0", color: "#a1a1aa" }}>
                      <strong>Created:</strong> {new Date(plan.created_at).toLocaleDateString()}
                    </p>
                  )}
                  {plan.locked_at && (
                    <p style={{ margin: "4px 0", color: "#a1a1aa" }}>
                      <strong>Locked:</strong> {new Date(plan.locked_at).toLocaleDateString()}
                    </p>
                  )}
                </div>

                {plan.status === "locked" && !plan.is_active && (
                  <button
                    onClick={() => handleActivate(plan.id)}
                    disabled={activating === plan.id}
                    style={{
                      marginTop: "12px",
                      width: "100%",
                      padding: "8px",
                      backgroundColor: "#18181b",
                      color: "#00ffaa",
                      border: "1px solid #00ffaa40",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontWeight: "600",
                      fontSize: "12px",
                    }}
                  >
                    {activating === plan.id ? "ACTIVATING..." : "ACTIVATE"}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
