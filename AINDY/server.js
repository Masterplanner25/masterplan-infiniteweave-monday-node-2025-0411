import express from "express";
import cors from "cors";
import axios from "axios";
import dotenv from "dotenv";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

// API key for service-to-service calls to FastAPI
const AINDY_API_KEY = process.env.AINDY_API_KEY;
const AINDY_BASE_URL = process.env.AINDY_BASE_URL || "http://localhost:8000";

app.post("/api/users", async (req, res) => {
  const user = req.body;

  try {
    // Send the event to A.I.N.D.Y. with service API key
    const response = await axios.post(`${AINDY_BASE_URL}/network_bridge/connect`, {
      author_name: user.name,           // ✅ expected by FastAPI
      platform: "InfiniteNetwork",      // ✅ expected by FastAPI
      connection_type: "BridgeHandshake",
      notes: user.tagline || null       // ✅ optional
    }, {
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": AINDY_API_KEY,
      }
    });

    console.log(`✅ Synced ${user.name} to A.I.N.D.Y.`);
    return res.status(201).json({
      ...user,
      author_id: response.data?.author_id,
      status: response.data?.status || "connected",
      synced_at: response.data?.timestamp,
    });
  } catch (err) {
    console.error("⚠️ Failed to sync with A.I.N.D.Y.:", err.message);
    return res.status(502).json({ error: "sync_failed", message: err.message });
  }
});


app.get("/api/users", (req, res) => {
  const platform = req.query.platform || "InfiniteNetwork";
  axios.get(`${AINDY_BASE_URL}/network_bridge/authors`, {
    params: { platform },
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": AINDY_API_KEY,
    }
  }).then((response) => {
    res.json(response.data);
  }).catch((err) => {
    console.error("⚠️ Failed to load users from A.I.N.D.Y.:", err.message);
    res.status(502).json({ error: "fetch_failed", message: err.message });
  });
});

// 👇 This keeps the server running
app.listen(5000, () => console.log("🌐 Node server running on port 5000"));
