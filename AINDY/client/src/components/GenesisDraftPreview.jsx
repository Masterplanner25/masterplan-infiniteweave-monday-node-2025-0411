/**
 * GenesisDraftPreview — Phase 3 editable preview of a synthesized MasterPlan draft.
 * Receives a draft object and onLock callback from Genesis.jsx.
 */
export default function GenesisDraftPreview({ draft, onLock, locking }) {
  if (!draft) return null;

  const phases = draft.phases || [];
  const domains = draft.core_domains || [];
  const criteria = draft.success_criteria || [];
  const risks = draft.risk_factors || [];

  return (
    <div style={{
      padding: "24px",
      border: "1px solid #27272a",
      borderRadius: "12px",
      background: "#0c0c0e",
      color: "#f4f4f5",
      fontSize: "13px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <h3 style={{ margin: 0, fontSize: "16px", fontWeight: "700" }}>
          DRAFT <span style={{ color: "#00ffaa" }}>MASTERPLAN</span>
        </h3>
        <button
          onClick={onLock}
          disabled={locking}
          style={{
            padding: "10px 20px",
            backgroundColor: locking ? "#27272a" : "#fff",
            color: "#000",
            border: "none",
            borderRadius: "8px",
            cursor: locking ? "not-allowed" : "pointer",
            fontWeight: "800",
            fontSize: "12px",
          }}
        >
          {locking ? "LOCKING..." : "LOCK PLAN"}
        </button>
      </div>

      {/* Core fields */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "20px" }}>
        <Field label="Vision" value={draft.vision_statement} />
        <Field label="Horizon" value={draft.time_horizon_years ? `${draft.time_horizon_years} years` : "—"} />
        <Field label="Mechanism" value={draft.primary_mechanism} />
        <Field label="Ambition" value={draft.ambition_score != null ? `${Math.round(draft.ambition_score * 100)}%` : "—"} />
        <Field label="Confidence" value={draft.confidence_at_synthesis != null ? `${Math.round(draft.confidence_at_synthesis * 100)}%` : "—"} />
      </div>

      {/* Phases */}
      {phases.length > 0 && (
        <Section label="Phases">
          {phases.map((p, i) => (
            <div key={i} style={{ marginBottom: "8px" }}>
              <span style={{ color: "#00ffaa", fontWeight: "600" }}>{p.name}</span>
              {p.duration_months && <span style={{ color: "#71717a", marginLeft: "8px" }}>{p.duration_months}mo</span>}
              {p.description && <p style={{ color: "#a1a1aa", margin: "2px 0 0 0" }}>{p.description}</p>}
            </div>
          ))}
        </Section>
      )}

      {/* Domains */}
      {domains.length > 0 && (
        <Section label="Core Domains">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            {domains.map((d, i) => (
              <span key={i} style={{
                padding: "4px 10px",
                border: "1px solid #3f3f46",
                borderRadius: "20px",
                color: "#a1a1aa",
                fontSize: "12px",
              }}>
                {d.name}
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* Success criteria */}
      {criteria.length > 0 && (
        <Section label="Success Criteria">
          <ul style={{ margin: 0, paddingLeft: "16px", color: "#a1a1aa" }}>
            {criteria.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </Section>
      )}

      {/* Risk factors */}
      {risks.length > 0 && (
        <Section label="Risk Factors">
          <ul style={{ margin: 0, paddingLeft: "16px", color: "#f87171" }}>
            {risks.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <p style={{ margin: "0 0 2px 0", color: "#71717a", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </p>
      <p style={{ margin: 0, color: "#f4f4f5" }}>{value || "—"}</p>
    </div>
  );
}

function Section({ label, children }) {
  return (
    <div style={{ marginBottom: "16px" }}>
      <p style={{ margin: "0 0 8px 0", color: "#71717a", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {label}
      </p>
      {children}
    </div>
  );
}
