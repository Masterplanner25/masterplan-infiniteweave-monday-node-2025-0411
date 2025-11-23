import React, { useEffect, useState } from "react";

export default function Dashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      const res = await fetch("http://127.0.0.1:8000/dashboard/overview");
      const json = await res.json();
      setData(json.overview);
    };
    fetchData();
  }, []);

  if (!data) return <p>Loading dashboard...</p>;

  return (
    <div>
      <h2 style={{ color: "#6cf" }}>System Overview</h2>
      <p>🧠 System Timestamp: {data.system_timestamp}</p>
      <p>👤 Total Authors: {data.author_count}</p>

      <h3 style={{ marginTop: "1rem", color: "#9f6" }}>Recent Authors</h3>
      <ul>
        {data.recent_authors.map((a) => (
          <li key={a.id}>
            {a.name} — {a.platform}
          </li>
        ))}
      </ul>

      <h3 style={{ marginTop: "1rem", color: "#f6f" }}>Recent Ripples</h3>
      <ul>
        {data.recent_ripples.map((r, i) => (
          <li key={i}>
            {r.summary} ({r.source_platform})
          </li>
        ))}
      </ul>
    </div>
  );
}

    <div style={{ marginTop: 18 }}>
  <h4>Autonomous Reasoning</h4>
  <div>
    <a href="/arm/analyze" style={{ marginRight: 12 }}>Open ARM — Analyze</a>
    <a href="/arm/generate">Open ARM — Generate</a>
  </div>
</div>