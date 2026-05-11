import React, { useEffect, useState } from "react";

import { getHealthDetails } from "../../api/platform.js";
import { useAuth } from "../../context/AuthContext";
import { AdminAccessRequired } from "../shared/AdminApiErrorBoundary";

export default function HealthDashboard() {
  const { isAdmin } = useAuth();
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const payload = await getHealthDetails();
        setHealth(payload);
      } catch {
        setError("Failed to load runtime health");
      } finally {
        setLoading(false);
      }
    };

    fetchHealth();
  }, []);

  if (!isAdmin) return <AdminAccessRequired />;
  if (loading) return <p>Loading health dashboard...</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;

  const platformChecks = Object.entries(health?.platform || {});
  const degradedDomains = health?.degraded_domains || [];

  return (
    <div style={{ padding: "1.5rem" }}>
      <h2 style={{ color: "#6cf" }}>A.I.N.D.Y. Runtime Health</h2>
      <p>Status: {health?.status || "unknown"}</p>
      <p>Build: {health?.version || "unknown"}</p>
      <p>Degraded Domains: {degradedDomains.length ? degradedDomains.join(", ") : "none"}</p>

      <div style={{ marginTop: "1rem", display: "grid", gap: "0.75rem" }}>
        {platformChecks.map(([name, status]) => (
          <div
            key={name}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "0.75rem 1rem",
              border: "1px solid #333",
              borderRadius: "0.75rem",
              background: "#111",
            }}
          >
            <span style={{ textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</span>
            <span
              style={{
                color:
                  status === "ok"
                    ? "#4caf50"
                    : status === "degraded"
                      ? "#ffb300"
                      : "#f44336",
              }}
            >
              {String(status)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
