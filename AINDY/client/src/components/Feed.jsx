import React, { useEffect, useState } from "react";
import { getFeed } from "../api";
import PostComposer from "./PostComposer";

export default function Feed() {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState(null);

  const fetchPosts = async (showSilently = false) => {
    if (!showSilently) setLoading(true);
    try {
      const data = await getFeed(20, filter);
      setPosts(data);
      setError("");
    } catch (err) {
      console.error("Feed Error:", err);
      setError("Could not load the network feed. Check backend connectivity.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPosts();
    // OPTIONAL: Auto-refresh every 60 seconds
    const interval = setInterval(() => fetchPosts(true), 60000);
    return () => clearInterval(interval);
  }, [filter]);

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h2 style={styles.title}>📡 Trust Feed</h2>
        <button onClick={() => fetchPosts()} style={styles.refreshBtn}>
          {loading ? "..." : "Refresh"}
        </button>
      </header>
      
      <PostComposer onPostCreated={() => fetchPosts(true)} />

      <div style={styles.filterBar}>
        <button 
          style={!filter ? styles.activeFilter : styles.filter} 
          onClick={() => setFilter(null)}
        >
          All Signal
        </button>
        <button 
          style={filter === "inner" ? styles.activeFilter : styles.filter} 
          onClick={() => setFilter("inner")}
        >
          🔒 Inner Circle
        </button>
      </div>

      {error && <div style={styles.errorBox}>{error}</div>}

      <div style={styles.stream}>
        {loading && <p style={styles.syncingText}>Synchronizing Trust Graph...</p>}
        
        {posts.map((item) => (
          <PostCard key={item.post.id} item={item} />
        ))}
        
        {!loading && posts.length === 0 && (
          <div style={styles.emptyState}>
            <p style={{ margin: 0, fontSize: "1.2rem" }}>No signal detected.</p>
            <small style={{ color: "#666" }}>Expand your network or be the first to broadcast.</small>
          </div>
        )}
      </div>
    </div>
  );
}

const PostCard = ({ item }) => {
  const { post, reason } = item;
  
  const getTierMeta = (tier) => {
    switch(tier) {
      case "inner": return { color: "#ff00ff", label: "INNER CIRCLE" };
      case "collab": return { color: "#00ccff", label: "COLLABORATOR" };
      default: return { color: "#00ffaa", label: "PUBLIC SIGNAL" };
    }
  };

  const tier = getTierMeta(post.trust_tier_required);

  return (
    <div 
      style={styles.card}
      onMouseEnter={(e) => e.currentTarget.style.borderColor = "#444"}
      onMouseLeave={(e) => e.currentTarget.style.borderColor = "#222"}
    >
      <div style={styles.cardHeader}>
        <div style={styles.authorGroup}>
          <div style={{...styles.avatar, backgroundColor: tier.color}}>{post.author_username[0].toUpperCase()}</div>
          <span style={styles.author}>@{post.author_username}</span>
        </div>
        <span style={{...styles.badge, borderColor: tier.color, color: tier.color}}>
          {tier.label}
        </span>
      </div>
      
      <p style={styles.content}>{post.content}</p>
      
      <div style={styles.cardFooter}>
        <span style={styles.meta}>{new Date(post.created_at).toLocaleDateString()} at {new Date(post.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
        <span style={{...styles.meta, color: "#aaa"}}>via {reason}</span>
      </div>
    </div>
  );
};

const styles = {
  container: { maxWidth: "650px", margin: "0 auto", padding: "2rem 1rem", color: "#eaeaea" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" },
  title: { borderLeft: "4px solid #00ffaa", paddingLeft: "12px", margin: 0, fontSize: "1.5rem" },
  refreshBtn: { background: "transparent", border: "1px solid #333", color: "#666", borderRadius: "4px", padding: "4px 10px", cursor: "pointer", fontSize: "12px" },
  filterBar: { display: "flex", gap: "8px", marginBottom: "24px", borderBottom: "1px solid #222", paddingBottom: "12px" },
  filter: { background: "transparent", border: "none", color: "#666", cursor: "pointer", fontSize: "13px", padding: "6px 12px", transition: "0.2s" },
  activeFilter: { background: "#1a1a1a", border: "none", color: "#00ffaa", cursor: "pointer", fontSize: "13px", padding: "6px 12px", borderRadius: "4px", fontWeight: "bold" },
  stream: { display: "flex", flexDirection: "column", gap: "12px" },
  card: { background: "#111", border: "1px solid #222", borderRadius: "12px", padding: "20px", transition: "0.2s border-color" },
  cardHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "15px" },
  authorGroup: { display: "flex", alignItems: "center", gap: "10px" },
  avatar: { width: "32px", height: "32px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", color: "#000", fontWeight: "bold", fontSize: "14px" },
  author: { fontWeight: "bold", color: "#fff", fontSize: "14px" },
  badge: { fontSize: "9px", border: "1px solid", padding: "2px 8px", borderRadius: "20px", fontWeight: "bold", letterSpacing: "0.5px" },
  content: { fontSize: "15px", lineHeight: "1.6", color: "#ddd", marginBottom: "20px", whiteSpace: "pre-wrap" },
  cardFooter: { display: "flex", justifyContent: "space-between", borderTop: "1px solid #222", paddingTop: "12px" },
  meta: { fontSize: "11px", color: "#444" },
  errorBox: { padding: "12px", background: "rgba(255, 68, 68, 0.1)", border: "1px solid #ff4444", color: "#ff4444", borderRadius: "8px", marginBottom: "20px", fontSize: "14px" },
  syncingText: { textAlign: "center", color: "#00ffaa", fontSize: "12px", margin: "10px 0", animatePulse: "true" },
  emptyState: { textAlign: "center", padding: "60px 20px", background: "#0a0a0a", border: "1px dashed #222", borderRadius: "12px" }
};