import React, { useEffect, useState } from "react";
import { getFeed, getSocialAnalytics, recordSocialInteraction } from "../../api/social.js";
import PostComposer from "./PostComposer";
import { safeMap } from "../../utils/safe";

export default function Feed() {
  const [posts, setPosts] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState(null);

  const fetchPosts = async (showSilently = false) => {
    if (!showSilently) setLoading(true);
    try {
      const [feedData, analyticsData] = await Promise.all([
        getFeed(20, filter),
        getSocialAnalytics(),
      ]);
      setPosts(feedData);
      setAnalytics(analyticsData);
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
    const interval = setInterval(() => fetchPosts(true), 60000);
    return () => clearInterval(interval);
  }, [filter]);

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <h2 style={styles.title}>Trust Feed</h2>
        <button onClick={() => fetchPosts()} style={styles.refreshBtn}>
          {loading ? "..." : "Refresh"}
        </button>
      </header>

      <PostComposer onPostCreated={() => fetchPosts(true)} />
      {analytics ? <SocialAnalyticsPanel analytics={analytics} /> : null}

      <div style={styles.filterBar}>
        <button style={!filter ? styles.activeFilter : styles.filter} onClick={() => setFilter(null)}>
          All Signal
        </button>
        <button style={filter === "inner" ? styles.activeFilter : styles.filter} onClick={() => setFilter("inner")}>
          Inner Circle
        </button>
      </div>

      {error ? <div style={styles.errorBox}>{error}</div> : null}

      <div style={styles.stream}>
        {loading ? <p style={styles.syncingText}>Synchronizing Trust Graph...</p> : null}
        {safeMap(posts, (item) => (
          <PostCard key={item.post.id} item={item} onInteraction={() => fetchPosts(true)} />
        ))}
        {!loading && posts.length === 0 ? (
          <div style={styles.emptyState}>
            <p style={{ margin: 0, fontSize: "1.2rem" }}>No signal detected.</p>
            <small style={{ color: "#666" }}>Expand your network or be the first to broadcast.</small>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SocialAnalyticsPanel({ analytics }) {
  return (
    <div style={styles.analyticsPanel}>
      <div style={styles.analyticsGrid}>
        <AnalyticsCard label="Posts" value={analytics.overview?.post_count || 0} />
        <AnalyticsCard label="Impressions" value={analytics.overview?.total_impressions || 0} />
        <AnalyticsCard label="Clicks" value={analytics.overview?.total_clicks || 0} />
        <AnalyticsCard label="Avg Engagement" value={Number(analytics.overview?.avg_engagement_score || 0).toFixed(1)} />
      </div>
      <div style={styles.trendRow}>
        <div style={styles.trendBox}>
          <h3 style={styles.subTitle}>Top Content</h3>
          {safeMap(analytics.top_posts || [], (post) => (
            <div key={post.id} style={styles.topPostRow}>
              <span style={styles.topPostContent}>{post.content}</span>
              <span style={styles.metric}>Eng {Number(post.engagement_score || 0).toFixed(1)}</span>
            </div>
          ))}
        </div>
        <div style={styles.trendBox}>
          <h3 style={styles.subTitle}>Performance Trend</h3>
          {safeMap(analytics.trend || [], (point) => (
            <div key={point.date} style={styles.trendPoint}>
              <span>{point.date}</span>
              <span>
                Impr {point.impressions} | Clicks {point.clicks} | Eng{" "}
                {Number(point.avg_engagement_score || 0).toFixed(1)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function AnalyticsCard({ label, value }) {
  return (
    <div style={styles.analyticsCard}>
      <div style={styles.analyticsValue}>{value}</div>
      <div style={styles.analyticsLabel}>{label}</div>
    </div>
  );
}

function PostCard({ item, onInteraction }) {
  const { post, reason } = item;

  const getTierMeta = (tier) => {
    switch (tier) {
      case "inner":
        return { color: "#ff7a18", label: "INNER CIRCLE" };
      case "collab":
        return { color: "#3fd0b8", label: "COLLABORATOR" };
      default:
        return { color: "#9ae66e", label: "PUBLIC SIGNAL" };
    }
  };

  const tier = getTierMeta(post.trust_tier_required);

  const handleInteraction = async (action) => {
    try {
      await recordSocialInteraction(post.id, action);
      if (onInteraction) onInteraction();
    } catch (err) {
      console.error("Social interaction failed", err);
    }
  };

  return (
    <div
      style={styles.card}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "#36524d";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "#222";
      }}
    >
      <div style={styles.cardHeader}>
        <div style={styles.authorGroup}>
          <div style={{ ...styles.avatar, backgroundColor: tier.color }}>
            {post.author_username[0].toUpperCase()}
          </div>
          <span style={styles.author}>@{post.author_username}</span>
        </div>
        <span style={{ ...styles.badge, borderColor: tier.color, color: tier.color }}>{tier.label}</span>
      </div>

      <p style={styles.content}>{post.content}</p>

      <div style={styles.cardFooter}>
        <div style={styles.metaGroup}>
          <span style={styles.meta}>
            {new Date(post.created_at).toLocaleDateString()} at{" "}
            {new Date(post.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
          <span style={{ ...styles.meta, color: "#aaa" }}>via {reason}</span>
          <span style={styles.metric}>Impr {post.impressions || 0}</span>
          <span style={styles.metric}>Clicks {post.clicks || 0}</span>
          <span style={styles.metric}>Eng {Number(post.engagement_score || 0).toFixed(1)}</span>
        </div>
        <div style={styles.actions}>
          <button style={styles.actionBtn} onClick={() => handleInteraction("click")}>
            Click
          </button>
          <button style={styles.actionBtn} onClick={() => handleInteraction("like")}>
            Like
          </button>
          <button style={styles.actionBtn} onClick={() => handleInteraction("boost")}>
            Boost
          </button>
        </div>
      </div>
    </div>
  );
}

const styles = {
  container: { maxWidth: "760px", margin: "0 auto", padding: "2rem 1rem", color: "#eaeaea" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" },
  title: { borderLeft: "4px solid #3fd0b8", paddingLeft: "12px", margin: 0, fontSize: "1.5rem" },
  refreshBtn: {
    background: "transparent",
    border: "1px solid #333",
    color: "#666",
    borderRadius: "4px",
    padding: "4px 10px",
    cursor: "pointer",
    fontSize: "12px",
  },
  filterBar: { display: "flex", gap: "8px", marginBottom: "24px", borderBottom: "1px solid #222", paddingBottom: "12px" },
  filter: { background: "transparent", border: "none", color: "#666", cursor: "pointer", fontSize: "13px", padding: "6px 12px" },
  activeFilter: {
    background: "#17201f",
    border: "none",
    color: "#9ae66e",
    cursor: "pointer",
    fontSize: "13px",
    padding: "6px 12px",
    borderRadius: "4px",
    fontWeight: "bold",
  },
  stream: { display: "flex", flexDirection: "column", gap: "12px" },
  card: { background: "#111", border: "1px solid #222", borderRadius: "12px", padding: "20px", transition: "0.2s border-color" },
  cardHeader: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "15px" },
  authorGroup: { display: "flex", alignItems: "center", gap: "10px" },
  avatar: {
    width: "32px",
    height: "32px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#08120f",
    fontWeight: "bold",
    fontSize: "14px",
  },
  author: { fontWeight: "bold", color: "#fff", fontSize: "14px" },
  badge: { fontSize: "9px", border: "1px solid", padding: "2px 8px", borderRadius: "20px", fontWeight: "bold", letterSpacing: "0.5px" },
  content: { fontSize: "15px", lineHeight: "1.6", color: "#ddd", marginBottom: "20px", whiteSpace: "pre-wrap" },
  cardFooter: { display: "flex", justifyContent: "space-between", borderTop: "1px solid #222", paddingTop: "12px", gap: "12px", flexWrap: "wrap" },
  metaGroup: { display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" },
  actions: { display: "flex", gap: "8px", alignItems: "center" },
  actionBtn: {
    background: "#161616",
    border: "1px solid #303030",
    color: "#ddd",
    borderRadius: "999px",
    padding: "6px 12px",
    cursor: "pointer",
    fontSize: "12px",
  },
  metric: { fontSize: "11px", color: "#8de7cf" },
  meta: { fontSize: "11px", color: "#444" },
  errorBox: { padding: "12px", background: "rgba(255, 68, 68, 0.1)", border: "1px solid #ff4444", color: "#ff4444", borderRadius: "8px", marginBottom: "20px", fontSize: "14px" },
  syncingText: { textAlign: "center", color: "#3fd0b8", fontSize: "12px", margin: "10px 0" },
  emptyState: { textAlign: "center", padding: "60px 20px", background: "#0a0a0a", border: "1px dashed #222", borderRadius: "12px" },
  analyticsPanel: { background: "#101417", border: "1px solid #1f2a2e", borderRadius: "12px", padding: "18px", marginBottom: "20px" },
  analyticsGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: "12px", marginBottom: "16px" },
  analyticsCard: { background: "#0b1012", border: "1px solid #223038", borderRadius: "10px", padding: "14px" },
  analyticsValue: { color: "#f5f7f6", fontSize: "24px", fontWeight: "bold" },
  analyticsLabel: { color: "#7ca09b", fontSize: "11px", textTransform: "uppercase" },
  trendRow: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "14px" },
  trendBox: { background: "#0b1012", border: "1px solid #223038", borderRadius: "10px", padding: "14px" },
  subTitle: { margin: "0 0 12px 0", color: "#d9f6ef", fontSize: "14px" },
  topPostRow: { display: "flex", justifyContent: "space-between", gap: "12px", padding: "8px 0", borderBottom: "1px solid #152026" },
  topPostContent: { color: "#d3d9d7", fontSize: "12px", flex: 1 },
  trendPoint: { display: "flex", justifyContent: "space-between", gap: "12px", padding: "6px 0", color: "#b1c3bf", fontSize: "12px" },
};
