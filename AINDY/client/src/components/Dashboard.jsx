import React, { useEffect, useState } from "react";
import { getDashboardOverview } from "../api";

export default function Dashboard() {
  const [data, setData] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      const json = await getDashboardOverview();
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
