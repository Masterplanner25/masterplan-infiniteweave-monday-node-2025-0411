import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getProfile, upsertProfile } from "../api";

export default function ProfileView() {
  const { username } = useParams();
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false); // New state for edit mode

  // Form State
  const [formData, setFormData] = useState({
    username: username || "me",
    tagline: "Building the Anti-LinkedIn",
    bio: "AI Architect & Solo Dev.",
    tags: ["Builder", "AI", "MVP"]
  });

  const fetchProfile = async () => {
    setLoading(true);
    try {
      const targetUser = username || "me";
      const data = await getProfile(targetUser);
      setProfile(data);
      setFormData(data); // Pre-fill form
      setIsEditing(false);
    } catch (err) {
      console.log("Profile not found. Showing create mode.");
      setProfile(null); // Triggers create mode
      setIsEditing(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, [username]);

  const handleSave = async () => {
    try {
      await upsertProfile(formData);
      await fetchProfile(); // Refresh after save
    } catch (err) {
      alert("Failed to save profile.");
    }
  };

  if (loading) return <div style={styles.container}>Loading Identity Node...</div>;

  // --- CREATE / EDIT MODE ---
  if (isEditing || !profile) {
    return (
      <div style={styles.container}>
        <h2 style={styles.sectionTitle}>👤 Initialize Identity</h2>
        <div style={styles.card}>
          <div style={{marginBottom: 16}}>
            <label style={styles.label}>Username</label>
            <input 
              style={styles.input} 
              value={formData.username} 
              onChange={e => setFormData({...formData, username: e.target.value})}
            />
          </div>
          <div style={{marginBottom: 16}}>
            <label style={styles.label}>Tagline</label>
            <input 
              style={styles.input} 
              value={formData.tagline} 
              onChange={e => setFormData({...formData, tagline: e.target.value})}
            />
          </div>
          <div style={{marginBottom: 16}}>
            <label style={styles.label}>Bio</label>
            <textarea 
              style={styles.textarea} 
              value={formData.bio} 
              onChange={e => setFormData({...formData, bio: e.target.value})}
            />
          </div>
          <button style={styles.button} onClick={handleSave}>
            {profile ? "Save Changes" : "Create Identity Node"}
          </button>
        </div>
      </div>
    );
  }

  // --- VIEW MODE (Existing Code) ---
  const { metrics_snapshot } = profile;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <div style={styles.avatarPlaceholder}>
          {profile.username.charAt(0).toUpperCase()}
        </div>
        <div>
          <h1 style={styles.username}>{profile.username}</h1>
          <p style={styles.tagline}>{profile.tagline}</p>
          <div style={styles.tagsRow}>
            {profile.tags?.map((tag, i) => (
              <span key={i} style={styles.tag}>#{tag}</span>
            ))}
          </div>
        </div>
        <button onClick={() => setIsEditing(true)} style={styles.editButton}>Edit</button>
      </div>

      <h3 style={styles.sectionTitle}>⚡ Velocity Metrics</h3>
      <div style={styles.grid}>
        <MetricCard label="TWR Score" value={metrics_snapshot?.twr_score?.toFixed(1) || "0.0"} color="#00ffaa" />
        <MetricCard label="Trust Score" value={metrics_snapshot?.trust_score?.toFixed(0) || "50"} color="#6cf" />
        <MetricCard label="Execution Velocity" value={metrics_snapshot?.execution_velocity?.toFixed(1) || "0.0"} color="#f6f" />
      </div>

      <div style={styles.trustBadgeContainer}>
        <span style={styles.trustLabel}>Network Status:</span>
        <span style={styles.trustValue}>INNER CIRCLE (Verified)</span>
      </div>

      <div style={styles.bioBox}>
        <h4 style={{color: "#888", marginBottom: "8px"}}>About</h4>
        <p style={{lineHeight: "1.6"}}>{profile.bio}</p>
      </div>
    </div>
  );
}

const MetricCard = ({ label, value, color }) => (
  <div style={{...styles.card, borderTop: `3px solid ${color}`}}>
    <div style={{fontSize: "24px", fontWeight: "bold", color: color}}>{value}</div>
    <div style={{fontSize: "12px", color: "#888", textTransform: "uppercase"}}>{label}</div>
  </div>
);

const styles = {
  container: { padding: "2rem", color: "#eaeaea", maxWidth: "800px", margin: "0 auto" },
  header: { display: "flex", alignItems: "center", gap: "24px", marginBottom: "32px", borderBottom: "1px solid #333", paddingBottom: "24px" },
  avatarPlaceholder: { width: "80px", height: "80px", borderRadius: "50%", background: "#222", color: "#6cf", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "32px", fontWeight: "bold", border: "2px solid #333" },
  username: { fontSize: "32px", margin: "0 0 8px 0", color: "#fff" },
  tagline: { fontSize: "16px", color: "#aaa", margin: "0 0 12px 0" },
  tagsRow: { display: "flex", gap: "8px" },
  tag: { background: "rgba(0, 255, 170, 0.1)", color: "#00ffaa", padding: "4px 8px", borderRadius: "4px", fontSize: "12px" },
  sectionTitle: { color: "#fff", borderLeft: "4px solid #6cf", paddingLeft: "12px", marginBottom: "16px" },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "16px", marginBottom: "32px" },
  card: { background: "#111", padding: "16px", borderRadius: "8px", textAlign: "center" },
  trustBadgeContainer: { background: "rgba(255, 0, 255, 0.05)", border: "1px solid rgba(255, 0, 255, 0.2)", padding: "12px 20px", borderRadius: "8px", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "32px" },
  trustLabel: { color: "#aaa", fontSize: "14px" },
  trustValue: { color: "#f6f", fontWeight: "bold", letterSpacing: "1px" },
  bioBox: { background: "#111", padding: "24px", borderRadius: "8px" },
  input: { width: "100%", padding: "8px", background: "#222", border: "1px solid #333", color: "#fff", borderRadius: "4px" },
  textarea: { width: "100%", padding: "8px", background: "#222", border: "1px solid #333", color: "#fff", borderRadius: "4px", minHeight: "100px" },
  label: { display: "block", marginBottom: "8px", color: "#aaa", fontSize: "14px" },
  button: { background: "#00ffaa", color: "#000", border: "none", padding: "10px 20px", borderRadius: "4px", fontWeight: "bold", cursor: "pointer" },
  editButton: { marginLeft: "auto", background: "transparent", border: "1px solid #444", color: "#aaa", padding: "6px 12px", borderRadius: "4px", cursor: "pointer" }
};