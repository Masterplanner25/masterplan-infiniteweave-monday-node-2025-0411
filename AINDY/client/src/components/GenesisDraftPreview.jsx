/**
 * GenesisDraftPreview — Phase 3 editable preview of a synthesized MasterPlan draft.
 * Block 4: Strategic Integrity Audit panel added.
 * Receives a draft object, sessionId, onLock callback from Genesis.jsx.
 */
import { useState } from "react";
import { auditGenesisDraft } from "../api";

const SEVERITY_COLORS = {
  critical: "#f87171",
  warning: "#fbbf24",
  advisory: "#60a5fa",
};

export default function GenesisDraftPreview({ draft, sessionId, onLock, locking }) {
  const [auditing, setAuditing] = useState(false);
  const [auditResult, setAuditResult] = useState(null);
  const [auditError, setAuditError] = useState(null);

  if (!draft) return null;

  const phases = draft.phases || [];
  const domains = draft.core_domains || [];
  const criteria = draft.success_criteria || [];
  const risks = draft.risk_factors || [];

  async function handleAudit() {
    setAuditing(true);
    setAuditResult(null);
    setAuditError(null);
    try {
      const result = await auditGenesisDraft(sessionId);
      setAuditResult(result);
    } catch (err) {
      setAuditError(err.message || "Audit failed.");
    } finally {
      setAuditing(false);
    }
  }

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
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={handleAudit}
            disabled={auditing || locking}
            style={{
              padding: "10px 18px",
              backgroundColor: "transparent",
              color: auditing ? "#71717a" : "#fbbf24",
              border: "1px solid #3f3f46",
              borderRadius: "8px",
              cursor: (auditing || locking) ? "not-allowed" : "pointer",
              fontWeight: "700",
              fontSize: "12px",
            }}
          >
            {auditing ? "AUDITING..." : "AUDIT DRAFT"}
          </button>
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

      {/* Audit error */}
      {auditError && (
        <div style={{
          marginTop: "16px",
          padding: "12px",
          background: "#1a0a0a",
          border: "1px solid #7f1d1d",
          borderRadius: "8px",
          color: "#f87171",
          fontSize: "12px",
        }}>
          Audit error: {auditError}
        </div>
      )}

      {/* Audit results panel */}
      {auditResult && (
        <div style={{
          marginTop: "20px",
          padding: "16px",
          background: "#0f0f13",
          border: `1px solid ${auditResult.audit_passed ? "#14532d" : "#7f1d1d"}`,
          borderRadius: "10px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <span style={{ fontWeight: "700", fontSize: "13px" }}>
              AUDIT{" "}
              <span style={{ color: auditResult.audit_passed ? "#4ade80" : "#f87171" }}>
                {auditResult.audit_passed ? "PASSED" : "FAILED"}
              </span>
            </span>
            <span style={{ color: "#71717a", fontSize: "12px" }}>
              Confidence: {auditResult.overall_confidence != null
                ? `${Math.round(auditResult.overall_confidence * 100)}%`
                : "—"}
            </span>
          </div>

          {auditResult.audit_summary && (
            <p style={{ margin: "0 0 12px 0", color: "#a1a1aa", fontSize: "12px", fontStyle: "italic" }}>
              {auditResult.audit_summary}
            </p>
          )}

          {auditResult.findings && auditResult.findings.length > 0 ? (
            <div>
              {auditResult.findings.map((f, i) => (
                <div key={i} style={{
                  marginBottom: "10px",
                  padding: "10px",
                  background: "#18181b",
                  borderRadius: "6px",
                  borderLeft: `3px solid ${SEVERITY_COLORS[f.severity] || "#71717a"}`,
                }}>
                  <div style={{ display: "flex", gap: "8px", marginBottom: "4px", alignItems: "center" }}>
                    <span style={{
                      padding: "2px 8px",
                      borderRadius: "4px",
                      fontSize: "10px",
                      fontWeight: "700",
                      textTransform: "uppercase",
                      background: SEVERITY_COLORS[f.severity] ? `${SEVERITY_COLORS[f.severity]}22` : "#27272a",
                      color: SEVERITY_COLORS[f.severity] || "#71717a",
                    }}>
                      {f.severity}
                    </span>
                    <span style={{ color: "#71717a", fontSize: "11px", textTransform: "uppercase" }}>
                      {f.type}
                    </span>
                  </div>
                  <p style={{ margin: "0 0 4px 0", color: "#f4f4f5", fontSize: "12px" }}>{f.description}</p>
                  {f.recommendation && (
                    <p style={{ margin: 0, color: "#71717a", fontSize: "11px" }}>
                      Rec: {f.recommendation}
                    </p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p style={{ margin: 0, color: "#4ade80", fontSize: "12px" }}>No findings — draft is structurally clean.</p>
          )}
        </div>
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
