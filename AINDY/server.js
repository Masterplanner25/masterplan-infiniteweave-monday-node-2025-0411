import express from "express";
import cors from "cors";
import axios from "axios";
import dotenv from "dotenv";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

const users = [];

// API key for service-to-service calls to FastAPI
const AINDY_API_KEY = process.env.AINDY_API_KEY;

app.post("/api/users", async (req, res) => {
  const user = req.body;
  users.push(user);

  try {
    // Send the event to A.I.N.D.Y. with service API key
    await axios.post("http://localhost:8000/network_bridge/connect", {
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
  } catch (err) {
    console.error("⚠️ Failed to sync with A.I.N.D.Y.:", err.message);
  }

  res.status(201).json(user);
});


app.get("/api/users", (req, res) => {
  res.json(users);
});

// 👇 This keeps the server running
app.listen(5000, () => console.log("🌐 Node server running on port 5000"));
