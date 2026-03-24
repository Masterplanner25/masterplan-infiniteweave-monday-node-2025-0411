import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listMasterPlans, activateMasterPlan, setMasterplanAnchor, getMasterplanProjection } from "../api.js";

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

function AnchorModal({ planId, onClose, onSaved }) {
  const [anchorDate, setAnchorDate] = useState("");
  const [goalValue, setGoalValue] = useState("");
  const [goalUnit, setGoalUnit] = useState("");
  const [goalDescription, setGoalDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await setMasterplanAnchor(planId, {
        anchor_date: anchorDate || null,
        goal_value: goalValue ? parseFloat(goalValue) : null,
        goal_unit: goalUnit || null,
        goal_description: goalDescription || null,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message || "Failed to save anchor");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.8)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div style={{
        background: "#0c0c0e", border: "1px solid #27272a", borderRadius: "12px",
        padding: "32px", width: "420px", color: "#fff",
      }}>
        <h3 style={{ margin: "0 0 24px", fontSize: "16px", fontWeight: "800" }}>
          SET <span style={{ color: "#00ffaa" }}>ANCHOR</span>
        </h3>

        <label style={{ display: "block", marginBottom: "16px" }}>
          <span style={{ fontSize: "12px", color: "#71717a", display: "block", marginBottom: "6px" }}>
            TARGET DATE
          </span>
          <input
            type="date"
            value={anchorDate}
            onChange={e => setAnchorDate(e.target.value)}
            style={{ width: "100%", padding: "8px", background: "#18181b", border: "1px solid #27272a", borderRadius: "6px", color: "#fff", boxSizing: "border-box" }}
          />
        </label>

        <label style={{ display: "block", marginBottom: "16px" }}>
          <span style={{ fontSize: "12px", color: "#71717a", display: "block", marginBottom: "6px" }}>
            GOAL VALUE
          </span>
          <input
            type="number"
            value={goalValue}
            onChange={e => setGoalValue(e.target.value)}
            placeholder="e.g. 100000"
            style={{ width: "100%", padding: "8px", background: "#18181b", border: "1px solid #27272a", borderRadius: "6px", color: "#fff", boxSizing: "border-box" }}
          />
        </label>

        <label style={{ display: "block", marginBottom: "16px" }}>
          <span style={{ fontSize: "12px", color: "#71717a", display: "block", marginBottom: "6px" }}>
            UNIT (e.g. USD, tasks, books)
          </span>
          <input
            type="text"
            value={goalUnit}
            onChange={e => setGoalUnit(e.target.value)}
            placeholder="USD"
            style={{ width: "100%", padding: "8px", background: "#18181b", border: "1px solid #27272a", borderRadius: "6px", color: "#fff", boxSizing: "border-box" }}
          />
        </label>

        <label style={{ display: "block", marginBottom: "24px" }}>
          <span style={{ fontSize: "12px", color: "#71717a", display: "block", marginBottom: "6px" }}>
            GOAL DESCRIPTION
          </span>
          <textarea
            value={goalDescription}
            onChange={e => setGoalDescription(e.target.value)}
            placeholder="What does reaching this goal mean?"
            rows={3}
            style={{ width: "100%", padding: "8px", background: "#18181b", border: "1px solid #27272a", borderRadius: "6px", color: "#fff", resize: "vertical", boxSizing: "border-box" }}
          />
        </label>

        {error && <p style={{ color: "#f87171", fontSize: "13px", marginBottom: "16px" }}>{error}</p>}

        <div style={{ display: "flex", gap: "12px" }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{ flex: 1, padding: "10px", backgroundColor: "#00ffaa", color: "#000", border: "none", borderRadius: "6px", fontWeight: "800", cursor: "pointer", fontSize: "13px" }}
          >
            {saving ? "SAVING..." : "SAVE ANCHOR"}
          </button>
          <button
            onClick={onClose}
            style={{ padding: "10px 16px", backgroundColor: "#18181b", color: "#71717a", border: "1px solid #27272a", borderRadius: "6px", cursor: "pointer", fontSize: "13px" }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

function ETAProjectionPanel({ planId }) {
  const [projection, setProjection] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMasterplanProjection(planId);
      setProjection(data);
    } catch (err) {
      setError("ETA unavailable");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [planId]);

  if (loading) return <p style={{ fontSize: "12px", color: "#52525b", margin: "8px 0 0" }}>Computing ETA...</p>;
  if (error) return <p style={{ fontSize: "12px", color: "#52525b", margin: "8px 0 0" }}>{error}</p>;
  if (!projection) return null;

  const confidenceColor = {
    high: "#00ffaa",
    medium: "#facc15",
    low: "#f87171",
    insufficient_data: "#52525b",
  }[projection.eta_confidence] || "#52525b";

  const dab = projection.days_ahead_behind;
  const dabLabel = dab === null ? null
    : dab >= 0 ? `${dab}d ahead` : `${Math.abs(dab)}d behind`;
  const dabColor = dab === null ? "#71717a" : dab >= 0 ? "#00ffaa" : "#f87171";

  return (
    <div style={{ marginTop: "12px", padding: "10px", background: "#111113", borderRadius: "6px", border: "1px solid #27272a" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
        <span style={{ fontSize: "11px", color: "#71717a", fontWeight: "700", letterSpacing: "0.05em" }}>ETA PROJECTION</span>
        <span style={{ fontSize: "11px", color: confidenceColor }}>{projection.eta_confidence}</span>
      </div>
      <div style={{ fontSize: "12px", color: "#a1a1aa" }}>
        <p style={{ margin: "3px 0" }}>
          <strong>Velocity:</strong> {projection.velocity?.toFixed(2)} tasks/day
        </p>
        {projection.projected_completion_date && (
          <p style={{ margin: "3px 0" }}>
            <strong>ETA:</strong> {projection.projected_completion_date}
          </p>
        )}
        {dabLabel && (
          <p style={{ margin: "3px 0", color: dabColor, fontWeight: "700" }}>
            {dabLabel}
          </p>
        )}
        <p style={{ margin: "3px 0" }}>
          {projection.completed_tasks} / {projection.total_tasks} tasks complete
        </p>
      </div>
    </div>
  );
}

export default function MasterPlanDashboard() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activating, setActivating] = useState(null);
  const [anchorModalPlanId, setAnchorModalPlanId] = useState(null);

  const fetchPlans = async () => {
    setLoading(true);
    try {
      const data = await listMasterPlans();
      setPlans(data.plans || []);
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

                {/* ETA Projection — shown for active plans */}
                {plan.is_active && <ETAProjectionPanel planId={plan.id} />}

                {/* Anchor button — available on active or locked plans */}
                {(plan.is_active || plan.status === "locked") && (
                  <button
                    onClick={() => setAnchorModalPlanId(plan.id)}
                    style={{
                      marginTop: "8px",
                      width: "100%",
                      padding: "7px",
                      backgroundColor: "transparent",
                      color: "#71717a",
                      border: "1px solid #27272a",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontWeight: "600",
                      fontSize: "11px",
                    }}
                  >
                    SET ANCHOR
                  </button>
                )}

                {plan.status === "locked" && !plan.is_active && (
                  <button
                    onClick={() => handleActivate(plan.id)}
                    disabled={activating === plan.id}
                    style={{
                      marginTop: "8px",
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

      {anchorModalPlanId && (
        <AnchorModal
          planId={anchorModalPlanId}
          onClose={() => setAnchorModalPlanId(null)}
          onSaved={fetchPlans}
        />
      )}
    </div>
  );
}
