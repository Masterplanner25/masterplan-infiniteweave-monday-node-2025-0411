import React, { useEffect, useState } from "react";
import { getFeed } from "../api";
import PostComposer from "./PostComposer";

export default function Feed() {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState(null); // null = show all

  // Function to fetch posts (can be called to refresh)
  const fetchPosts = async () => {
    setLoading(true);
    try {
      const data = await getFeed(20, filter);
      setPosts(data);
      setError("");
    } catch (err) {
      console.error("Feed Error:", err);
      setError("Could not load the network feed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchPosts();
  }, [filter]);

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>📡 Network Activity</h2>
      
      {/* --- 1. THE INPUT MECHANISM --- */}
      <PostComposer onPostCreated={fetchPosts} />

      {/* --- 2. FILTER CONTROLS --- */}
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

      {/* --- 3. THE FEED STREAM --- */}
      {loading && <p style={{color: "#666"}}>Syncing with Trust Graph...</p>}
      {error && <p style={{color: "#ff4444"}}>{error}</p>}

      <div style={styles.stream}>
        {posts.map((item) => (
          <PostCard key={item.post.id} item={item} />
        ))}
        
        {!loading && posts.length === 0 && (
          <div style={styles.emptyState}>
            <p>No signal detected yet.</p>
            <small>Be the first to broadcast.</small>
          </div>
        )}
      </div>
    </div>
  );
}

// --- HELPER: INDIVIDUAL POST CARD ---
const PostCard = ({ item }) => {
  const { post, reason } = item;
  
  // Trust Tier Badge Color Logic
  const tierColor = 
    post.trust_tier_required === "inner" ? "#f6f" : 
    post.trust_tier_required === "collab" ? "#6cf" : "#888";

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <span style={styles.author}>@{post.author_username}</span>
        <span style={{...styles.badge, borderColor: tierColor, color: tierColor}}>
          {post.trust_tier_required.toUpperCase()}
        </span>
      </div>
      
      <p style={styles.content}>{post.content}</p>
      
      <div style={styles.cardFooter}>
        <span style={styles.meta}>{new Date(post.created_at).toLocaleString()}</span>
        <span style={styles.meta}>Running via {reason}</span>
      </div>
    </div>
  );
};

// --- STYLES ---
const styles = {
  container: {
    maxWidth: "700px",
    margin: "0 auto",
    padding: "2rem",
    color: "#eaeaea",
  },
  title: {
    borderLeft: "4px solid #00ffaa",
    paddingLeft: "12px",
    marginBottom: "24px",
  },
  filterBar: {
    display: "flex",
    gap: "12px",
    marginBottom: "24px",
    borderBottom: "1px solid #333",
    paddingBottom: "12px",
  },
  filter: {
    background: "transparent",
    border: "none",
    color: "#666",
    cursor: "pointer",
    fontSize: "14px",
    padding: "4px 8px",
  },
  activeFilter: {
    background: "#222",
    border: "none",
    color: "#00ffaa",
    cursor: "pointer",
    fontSize: "14px",
    padding: "4px 8px",
    borderRadius: "4px",
    fontWeight: "bold",
  },
  stream: {
    display: "flex",
    flexDirection: "column",
    gap: "16px",
  },
  card: {
    background: "#111",
    border: "1px solid #222",
    borderRadius: "8px",
    padding: "20px",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: "12px",
  },
  author: {
    fontWeight: "bold",
    color: "#fff",
  },
  badge: {
    fontSize: "10px",
    border: "1px solid",
    padding: "2px 6px",
    borderRadius: "10px",
    letterSpacing: "1px",
  },
  content: {
    fontSize: "15px",
    lineHeight: "1.5",
    color: "#ccc",
    marginBottom: "16px",
    whiteSpace: "pre-wrap",
  },
  cardFooter: {
    display: "flex",
    justifyContent: "space-between",
    borderTop: "1px solid #222",
    paddingTop: "12px",
  },
  meta: {
    fontSize: "12px",
    color: "#555",
  },
  emptyState: {
    textAlign: "center",
    padding: "40px",
    color: "#444",
    border: "2px dashed #222",
    borderRadius: "8px",
  }
};