// src/components/IdentityDashboard.jsx
import React, { useState, useEffect, useCallback } from "react";
import {
  getIdentityProfile,
  updateIdentityProfile,
  getIdentityEvolution,
  getIdentityContext,
} from "../../api/identity.js";

// ── Constants ───────────────────────────────────────────────────────────────
import { safeMap } from "../../utils/safe";
const DIMENSION_META = {
  communication: {
    icon: "💬",
    label: "Communication",
    color: "#60a5fa",
    fields: [
    { key: "tone", label: "Tone", type: "text" },
    { key: "notes", label: "Notes", type: "textarea" }]

  },
  tools: {
    icon: "🛠️",
    label: "Tools & Tech",
    color: "#34d399",
    fields: [
    { key: "preferred_languages", label: "Preferred Languages", type: "tags" },
    { key: "preferred_tools", label: "Preferred Tools", type: "tags" },
    { key: "avoided_tools", label: "Avoided Tools", type: "tags" }]

  },
  decision_making: {
    icon: "🎯",
    label: "Decision Making",
    color: "#ffd93d",
    fields: [
    { key: "risk_tolerance", label: "Risk Tolerance", type: "text" },
    { key: "speed_vs_quality", label: "Speed vs Quality", type: "text" },
    { key: "notes", label: "Notes", type: "textarea" }]

  },
  learning: {
    icon: "📚",
    label: "Learning Style",
    color: "#a78bfa",
    fields: [
    { key: "style", label: "Style", type: "text" },
    { key: "detail_preference", label: "Detail Preference", type: "text" },
    { key: "notes", label: "Notes", type: "textarea" }]

  }
};

const ARC_COLORS = {
  "Stable and consistent": "#00ffaa",
  "Actively evolving": "#ffd93d",
  "No observations yet": "#94a3b8"
};

function arcColor(arc) {
  if (!arc) return "#94a3b8";
  if (arc.toLowerCase().includes("stable")) return "#00ffaa";
  if (arc.toLowerCase().includes("evolv")) return "#ffd93d";
  return "#94a3b8";
}

// ── Sub-components ──────────────────────────────────────────────────────────

function TagList({ items }) {
  if (!items || items.length === 0) {
    return <span style={{ color: "#52525b", fontSize: 12 }}>None set</span>;
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {safeMap(items, (t, i) =>
      <span
        key={i}
        style={{
          background: "#27272a",
          border: "1px solid #3f3f46",
          borderRadius: 4,
          padding: "1px 8px",
          fontSize: 12,
          color: "#a1a1aa"
        }}>

          {t}
        </span>)
      }
    </div>);

}

function FieldValue({ field, value }) {
  if (field.type === "tags") return <TagList items={value} />;
  if (!value) return <span style={{ color: "#52525b", fontSize: 12 }}>Not set</span>;
  return <span style={{ color: "#e4e4e7", fontSize: 13 }}>{value}</span>;
}

function DimensionCard({ dimensionKey, data, onEdit }) {
  const meta = DIMENSION_META[dimensionKey];
  if (!meta) return null;
  return (
    <div
      style={{
        background: "#18181b",
        border: `1px solid ${meta.color}22`,
        borderRadius: 10,
        padding: 20,
        display: "flex",
        flexDirection: "column",
        gap: 14
      }}>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 20 }}>{meta.icon}</span>
          <span style={{ color: meta.color, fontWeight: 700, fontSize: 15 }}>{meta.label}</span>
        </div>
        <button
          onClick={() => onEdit(dimensionKey)}
          style={{
            background: "transparent",
            border: `1px solid #3f3f46`,
            borderRadius: 6,
            color: "#a1a1aa",
            fontSize: 11,
            padding: "3px 10px",
            cursor: "pointer"
          }}>

          Edit
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {safeMap(meta.fields, (field) =>
        <div key={field.key}>
            <div style={{ color: "#71717a", fontSize: 11, marginBottom: 3 }}>{field.label}</div>
            <FieldValue field={field} value={data?.[field.key]} />
          </div>)
        }
      </div>
    </div>);

}

function ContextPreview({ context, open, onToggle }) {
  return (
    <div
      style={{
        background: "#18181b",
        border: "1px solid #27272a",
        borderRadius: 10,
        overflow: "hidden"
      }}>

      <button
        onClick={onToggle}
        style={{
          width: "100%",
          background: "transparent",
          border: "none",
          padding: "12px 18px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
          color: "#a1a1aa",
          fontSize: 13
        }}>

        <span>🔍 How AINDY sees you right now</span>
        <span style={{ fontSize: 11 }}>{open ? "▲" : "▼"}</span>
      </button>
      {open &&
      <div style={{ padding: "0 18px 16px" }}>
          {context ?
        <pre
          style={{
            margin: 0,
            whiteSpace: "pre-wrap",
            fontFamily: "inherit",
            fontSize: 12,
            color: "#71717a",
            lineHeight: 1.6
          }}>

              {JSON.stringify(context, null, 2)}
            </pre> :

        <span style={{ color: "#52525b", fontSize: 12 }}>No context loaded.</span>
        }
        </div>
      }
    </div>);

}

function EvolutionTimeline({ evolution }) {
  if (!evolution) return null;

  const { observation_count, total_changes, most_changed_dimension, recent_changes, evolution_arc, message } =
  evolution;
  const arc = evolution_arc || message || "";

  return (
    <div
      style={{
        background: "#18181b",
        border: "1px solid #27272a",
        borderRadius: 10,
        padding: 20
      }}>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: 18 }}>📈</span>
        <span style={{ color: "#e4e4e7", fontWeight: 700, fontSize: 15 }}>Evolution</span>
      </div>

      {/* Stats row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 12,
          marginBottom: 16
        }}>

        {safeMap([
        { label: "Observations", value: observation_count ?? 0, color: "#60a5fa" },
        { label: "Total Changes", value: total_changes ?? 0, color: "#ffd93d" },
        {
          label: "Most Changed",
          value: most_changed_dimension ?
          DIMENSION_META[most_changed_dimension]?.label ?? most_changed_dimension :
          "—",
          color: most_changed_dimension ? DIMENSION_META[most_changed_dimension]?.color ?? "#94a3b8" : "#52525b"
        }],
        (stat) =>
        <div
          key={stat.label}
          style={{
            background: "#09090b",
            borderRadius: 8,
            padding: "10px 14px",
            textAlign: "center"
          }}>

            <div style={{ color: stat.color, fontWeight: 700, fontSize: 20 }}>{stat.value}</div>
            <div style={{ color: "#52525b", fontSize: 11, marginTop: 2 }}>{stat.label}</div>
          </div>)
        }
      </div>

      {/* Arc badge */}
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          background: "#09090b",
          borderRadius: 6,
          padding: "4px 12px",
          marginBottom: 16,
          border: `1px solid ${arcColor(arc)}44`
        }}>

        <span style={{ width: 6, height: 6, borderRadius: "50%", background: arcColor(arc), display: "inline-block" }} />
        <span style={{ color: arcColor(arc), fontSize: 12 }}>{arc || "No arc data"}</span>
      </div>

      {/* Recent changes */}
      {recent_changes && recent_changes.length > 0 ?
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ color: "#71717a", fontSize: 11, marginBottom: 2 }}>Recent Changes</div>
          {safeMap(recent_changes, (change, i) => {
          const dimMeta = change.dimension ? DIMENSION_META[change.dimension] : null;
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                background: "#09090b",
                borderRadius: 8,
                padding: "8px 12px"
              }}>

                <span style={{ fontSize: 14, marginTop: 1 }}>{dimMeta?.icon ?? "•"}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 2 }}>
                    {dimMeta &&
                  <span
                    style={{
                      fontSize: 10,
                      color: dimMeta.color,
                      background: `${dimMeta.color}22`,
                      borderRadius: 4,
                      padding: "1px 6px"
                    }}>

                        {dimMeta.label}
                      </span>
                  }
                    {change.field &&
                  <span style={{ color: "#52525b", fontSize: 11 }}>{change.field}</span>
                  }
                  </div>
                  {change.new_value &&
                <span style={{ color: "#a1a1aa", fontSize: 12 }}>
                      → {typeof change.new_value === "object" ? JSON.stringify(change.new_value) : String(change.new_value)}
                    </span>
                }
                  {change.inference_source &&
                <div style={{ color: "#3f3f46", fontSize: 11, marginTop: 2 }}>
                      via {change.inference_source}
                    </div>
                }
                </div>
              </div>);

        })}
        </div> :

      <div style={{ color: "#52525b", fontSize: 12, textAlign: "center", padding: "12px 0" }}>
          No changes recorded yet. Use AINDY and your profile will evolve automatically.
        </div>
      }
    </div>);

}

function EditModal({ dimensionKey, data, onSave, onClose }) {
  const meta = DIMENSION_META[dimensionKey];
  const [form, setForm] = useState(() => {
    const initial = {};
    if (data && meta) {
      meta.fields.forEach((f) => {
        initial[f.key] = data[f.key] ?? (f.type === "tags" ? [] : "");
      });
    }
    return initial;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [tagInput, setTagInput] = useState({});

  if (!meta) return null;

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function addTag(key) {
    const raw = (tagInput[key] || "").trim();
    if (!raw) return;
    const current = form[key] || [];
    if (!current.includes(raw)) {
      setField(key, [...current, raw]);
    }
    setTagInput((prev) => ({ ...prev, [key]: "" }));
  }

  function removeTag(key, tag) {
    setField(
      key,
      (form[key] || []).filter((t) => t !== tag)
    );
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave(dimensionKey, form);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}>

      <div
        style={{
          background: "#18181b",
          border: `1px solid ${meta.color}44`,
          borderRadius: 12,
          padding: 28,
          width: 460,
          maxWidth: "90vw",
          maxHeight: "80vh",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 20
        }}>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 20 }}>{meta.icon}</span>
            <span style={{ color: meta.color, fontWeight: 700, fontSize: 16 }}>
              Edit {meta.label}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "#52525b", fontSize: 18, cursor: "pointer" }}>

            ✕
          </button>
        </div>

        {safeMap(meta.fields, (field) =>
        <div key={field.key}>
            <label style={{ color: "#71717a", fontSize: 12, display: "block", marginBottom: 6 }}>
              {field.label}
            </label>
            {field.type === "tags" ?
          <div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 6 }}>
                  {safeMap(form[field.key], (tag) =>
              <span
                key={tag}
                style={{
                  background: "#27272a",
                  border: "1px solid #3f3f46",
                  borderRadius: 4,
                  padding: "2px 8px",
                  fontSize: 12,
                  color: "#a1a1aa",
                  display: "flex",
                  alignItems: "center",
                  gap: 4
                }}>

                      {tag}
                      <button
                  onClick={() => removeTag(field.key, tag)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "#52525b",
                    cursor: "pointer",
                    padding: 0,
                    lineHeight: 1,
                    fontSize: 11
                  }}>

                        ✕
                      </button>
                    </span>
              )}
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <input
                value={tagInput[field.key] || ""}
                onChange={(e) =>
                setTagInput((prev) => ({ ...prev, [field.key]: e.target.value }))
                }
                onKeyDown={(e) => e.key === "Enter" && addTag(field.key)}
                placeholder="Add item, press Enter"
                style={{
                  flex: 1,
                  background: "#09090b",
                  border: "1px solid #27272a",
                  borderRadius: 6,
                  color: "#e4e4e7",
                  fontSize: 13,
                  padding: "7px 10px",
                  outline: "none"
                }} />

                  <button
                onClick={() => addTag(field.key)}
                style={{
                  background: meta.color,
                  border: "none",
                  borderRadius: 6,
                  color: "#09090b",
                  fontWeight: 700,
                  fontSize: 13,
                  padding: "7px 14px",
                  cursor: "pointer"
                }}>

                    Add
                  </button>
                </div>
              </div> :
          field.type === "textarea" ?
          <textarea
            value={form[field.key] || ""}
            onChange={(e) => setField(field.key, e.target.value)}
            rows={3}
            style={{
              width: "100%",
              boxSizing: "border-box",
              background: "#09090b",
              border: "1px solid #27272a",
              borderRadius: 6,
              color: "#e4e4e7",
              fontSize: 13,
              padding: "8px 10px",
              outline: "none",
              resize: "vertical",
              fontFamily: "inherit"
            }} /> :


          <input
            value={form[field.key] || ""}
            onChange={(e) => setField(field.key, e.target.value)}
            style={{
              width: "100%",
              boxSizing: "border-box",
              background: "#09090b",
              border: "1px solid #27272a",
              borderRadius: 6,
              color: "#e4e4e7",
              fontSize: 13,
              padding: "8px 10px",
              outline: "none"
            }} />

          }
          </div>)
        }

        {error &&
        <div style={{ background: "#7f1d1d", borderRadius: 6, padding: "8px 12px", color: "#fca5a5", fontSize: 12 }}>
            {error}
          </div>
        }

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "1px solid #3f3f46",
              borderRadius: 6,
              color: "#a1a1aa",
              fontSize: 13,
              padding: "8px 18px",
              cursor: "pointer"
            }}>

            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              background: meta.color,
              border: "none",
              borderRadius: 6,
              color: "#09090b",
              fontWeight: 700,
              fontSize: 13,
              padding: "8px 22px",
              cursor: saving ? "not-allowed" : "pointer",
              opacity: saving ? 0.6 : 1
            }}>

            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>);

}

// ── Main component ──────────────────────────────────────────────────────────

export default function IdentityDashboard() {
  const [profile, setProfile] = useState(null);
  const [evolution, setEvolution] = useState(null);
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [editDimension, setEditDimension] = useState(null);
  const [saveError, setSaveError] = useState(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [prof, evo] = await Promise.all([getIdentityProfile(), getIdentityEvolution()]);
      setProfile(prof);
      setEvolution(evo);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function loadContext() {
    if (context) {
      setContextOpen((o) => !o);
      return;
    }
    try {
      const ctx = await getIdentityContext();
      setContext(ctx);
      setContextOpen(true);
    } catch {
      setContextOpen((o) => !o);
    }
  }

  async function handleSaveDimension(dimensionKey, formData) {
    setSaveError(null);
    await updateIdentityProfile({ [dimensionKey]: formData });
    // Optimistic update
    setProfile((prev) => ({ ...prev, [dimensionKey]: { ...(prev?.[dimensionKey] ?? {}), ...formData } }));
    // Refresh evolution
    try {
      const evo = await getIdentityEvolution();
      setEvolution(evo);
    } catch {

      // non-fatal
    }}

  // ── Render ─────────────────────────────────────────────────────────────────

  const containerStyle = {
    minHeight: "100vh",
    background: "#09090b",
    color: "#e4e4e7",
    fontFamily: "'Inter', 'Segoe UI', sans-serif",
    padding: "28px 32px",
    maxWidth: 860,
    margin: "0 auto"
  };

  if (loading) {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: "center", padding: 80, color: "#52525b" }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>👤</div>
          <div>Loading identity profile…</div>
        </div>
      </div>);

  }

  if (error) {
    return (
      <div style={containerStyle}>
        <div
          style={{
            background: "#7f1d1d",
            borderRadius: 10,
            padding: "20px 24px",
            color: "#fca5a5",
            display: "flex",
            alignItems: "center",
            gap: 12
          }}>

          <span style={{ fontSize: 20 }}>⚠️</span>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 4 }}>Failed to load identity profile</div>
            <div style={{ fontSize: 13 }}>{error}</div>
          </div>
          <button
            onClick={loadAll}
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "1px solid #fca5a5",
              borderRadius: 6,
              color: "#fca5a5",
              fontSize: 12,
              padding: "6px 14px",
              cursor: "pointer"
            }}>

            Retry
          </button>
        </div>
      </div>);

  }

  const evol = profile?.evolution ?? {};

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ fontSize: 28 }}>👤</span>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: "#e4e4e7" }}>Identity Profile</h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <span style={{ color: "#52525b", fontSize: 13 }}>
            What A.I.N.D.Y. has learned about how you work
          </span>
          {evol.observation_count > 0 &&
          <span
            style={{
              background: "#00ffaa22",
              border: "1px solid #00ffaa44",
              borderRadius: 6,
              color: "#00ffaa",
              fontSize: 12,
              padding: "2px 10px"
            }}>

              {evol.observation_count} observation{evol.observation_count !== 1 ? "s" : ""}
            </span>
          }
        </div>
      </div>

      {/* Context Preview */}
      <div style={{ marginBottom: 20 }}>
        <ContextPreview context={context} open={contextOpen} onToggle={loadContext} />
      </div>

      {/* Profile Grid — 2×2 */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          marginBottom: 24
        }}>

        {safeMap(Object.keys(DIMENSION_META), (key) =>
        <DimensionCard
          key={key}
          dimensionKey={key}
          data={profile?.[key]}
          onEdit={setEditDimension} />)

        }
      </div>

      {/* Evolution Timeline */}
      <EvolutionTimeline evolution={evolution} />

      {/* Edit Modal */}
      {editDimension &&
      <EditModal
        dimensionKey={editDimension}
        data={profile?.[editDimension]}
        onSave={handleSaveDimension}
        onClose={() => {
          setEditDimension(null);
          setSaveError(null);
        }} />

      }

      {saveError &&
      <div
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          background: "#7f1d1d",
          borderRadius: 8,
          padding: "10px 16px",
          color: "#fca5a5",
          fontSize: 13,
          zIndex: 1001
        }}>

          Save failed: {saveError}
        </div>
      }
    </div>);

}
