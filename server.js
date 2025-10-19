import express from "express";
import cors from "cors";
import axios from "axios";

const app = express();
app.use(cors());
app.use(express.json());

const users = [];

app.post("/api/users", async (req, res) => {
  const user = req.body;
  users.push(user);

  try {
    // Send the event to A.I.N.D.Y.
    await axios.post("http://localhost:8000/bridge/user_event", {
      name: user.name,
      tagline: user.tagline,
      platform: "InfiniteNetwork",
      action: "create_profile"
    });
    console.log(`✅ Synced ${user.name} to A.I.N.D.Y.`);
  } catch (err) {
    console.error("⚠️ Failed to sync with A.I.N.D.Y.:", err.message);
  }

  res.status(201).json(user);
});

// 👇 This keeps the server running
app.listen(5000, () => console.log("🌐 Node server running on port 5000"));
