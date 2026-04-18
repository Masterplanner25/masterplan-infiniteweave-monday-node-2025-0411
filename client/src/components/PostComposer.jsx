import React, { useState } from "react";
import { createPost } from "../api";

export default function PostComposer({ onPostCreated }) {
  const [content, setContent] = useState("");
  const [trustTier, setTrustTier] = useState("observer"); // Default: Public
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!content.trim()) return;

    setLoading(true);
    setError("");

    try {
      // 🧠 Construct the post payload matching your SocialPost model
      const newPost = {
        author_id: "me", // Backend handles actual ID resolution
        author_username: "me",
        content: content,
        trust_tier_required: trustTier,
        tags: [], // Could parse hashtags from content here
      };

      await createPost(newPost);
      
      // Reset form
      setContent("");
      setTrustTier("observer");
      
      // Notify parent to refresh feed
      if (onPostCreated) onPostCreated();
      
    } catch (err) {
      setError("Failed to post. System might be offline.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.container}>
      <form onSubmit={handleSubmit}>
        <textarea
          style={styles.textarea}
          placeholder="What are you building today?"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={loading}
        />
        
        <div style={styles.controls}>
          {/* Trust Tier Selector */}
          <select 
            style={styles.select}
            value={trustTier}
            onChange={(e) => setTrustTier(e.target.value)}
            disabled={loading}
          >
            <option value="observer">🌍 Public (Observer)</option>
            <option value="collab">🤝 Partners (Collab)</option>
            <option value="inner">🔒 Inner Circle</option>
          </select>

          <button 
            type="submit" 
            style={loading ? {...styles.button, opacity: 0.5} : styles.button}
            disabled={loading}
          >
            {loading ? "Posting..." : "Post Update"}
          </button>
        </div>
        
        {error && <p style={{color: "#ff4444", marginTop: "8px", fontSize: "12px"}}>{error}</p>}
      </form>
    </div>
  );
}

// --- STYLES ---
const styles = {
  container: {
    background: "#1a1a1a",
    border: "1px solid #333",
    borderRadius: "8px",
    padding: "16px",
    marginBottom: "24px",
  },
  textarea: {
    width: "100%",
    background: "#0b0b0b",
    border: "1px solid #333",
    borderRadius: "6px",
    padding: "12px",
    color: "#eaeaea",
    fontSize: "14px",
    minHeight: "80px",
    marginBottom: "12px",
    fontFamily: "inherit",
    resize: "vertical",
  },
  controls: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  select: {
    background: "#222",
    color: "#aaa",
    border: "1px solid #333",
    padding: "8px 12px",
    borderRadius: "4px",
    fontSize: "13px",
    cursor: "pointer",
  },
  button: {
    background: "#00ffaa",
    color: "#000",
    border: "none",
    padding: "8px 20px",
    borderRadius: "4px",
    fontWeight: "bold",
    cursor: "pointer",
    transition: "opacity 0.2s",
  }
};