import { useState } from "react";

export default function EngagementPanel() {
  const [likes, setLikes] = useState(0);
  const [shares, setShares] = useState(0);
  const [comments, setComments] = useState(0);
  const [clicks, setClicks] = useState(0);
  const [timeOnPage, setTimeOnPage] = useState(0);
  const [totalViews, setTotalViews] = useState(0);
  const [result, setResult] = useState(null);

  // --- Internal Styles ---
  const panelStyle = {
    backgroundColor: "#141414",
    padding: "15px",
    borderRadius: "8px",
    border: "1px solid #222",
    marginBottom: "15px"
  };

  const inputStyle = {
    backgroundColor: "#222",
    color: "#fff",
    border: "1px solid #444",
    padding: "10px",
    borderRadius: "4px",
    fontSize: "14px",
    width: "100%",
    boxSizing: "border-box"
  };

  const labelStyle = {
    fontSize: "11px",
    color: "#888",
    display: "block",
    marginBottom: "4px"
  };

  const buttonStyle = {
    backgroundColor: "#6f42c1", // Purple theme for Engagement
    color: "#fff",
    border: "none",
    padding: "12px",
    borderRadius: "6px",
    cursor: "pointer",
    fontWeight: "bold",
    width: "100%",
    marginTop: "10px",
    transition: "background 0.2s"
  };

  const handleSubmit = async () => {
    try {
      const response = await fetch("http://localhost:8000/calculate_engagement", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          likes: parseInt(likes),
          shares: parseInt(shares),
          comments: parseInt(comments),
          clicks: parseInt(clicks),
          time_on_page: parseFloat(timeOnPage),
          total_views: parseInt(totalViews)
        })
      });

      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error("Engagement Calculation Error:", err);
    }
  };

  return (
    <div style={panelStyle}>
      <h3 style={{ marginTop: 0, fontSize: "16px", color: "#6f42c1" }}>Engagement Metrics</h3>

      {/* Grid Layout to prevent overlapping */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "10px" }}>
        <div>
          <label style={labelStyle}>Likes</label>
          <input type="number" style={inputStyle} value={likes} onChange={(e)=>setLikes(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Shares</label>
          <input type="number" style={inputStyle} value={shares} onChange={(e)=>setShares(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Comments</label>
          <input type="number" style={inputStyle} value={comments} onChange={(e)=>setComments(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Clicks</label>
          <input type="number" style={inputStyle} value={clicks} onChange={(e)=>setClicks(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Time on Page</label>
          <input type="number" style={inputStyle} value={timeOnPage} onChange={(e)=>setTimeOnPage(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Total Views</label>
          <input type="number" style={inputStyle} value={totalViews} onChange={(e)=>setTotalViews(e.target.value)} />
        </div>
      </div>

      <button style={buttonStyle} onClick={handleSubmit}>
        Calculate Engagement Score
      </button>

      {result && (
        <pre style={{ 
          marginTop: "15px", 
          padding: "12px", 
          background: "#0a0a0a", 
          color: "#a278ff", 
          fontSize: "12px", 
          borderRadius: "4px",
          border: "1px solid #331a4d",
          overflowX: "auto"
        }}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}
