import React, { useState, useEffect } from "react";
import axios from "axios";

function App() {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ name: "", tagline: "" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    axios
      .get("http://localhost:5000/api/users")
      .then((res) => setUsers(res.data))
      .catch((err) => {
        console.error("⚠️ Error fetching users:", err);
        setError("Could not load users.");
      });
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.tagline) return;
    setLoading(true);
    setError("");
    try {
      const res = await axios.post("http://localhost:5000/api/users", form);
      setUsers([...users, res.data]);
      setForm({ name: "", tagline: "" });
    } catch (err) {
      console.error("⚠️ Error creating user:", err);
      setError("Failed to create user.");
    } finally {
      setLoading(false);
    }
  };

  return (
    /* Main Container: Changed to a deep dark zinc */
    <div className="p-10 font-sans bg-zinc-950 text-white min-h-screen">
      <h1 className="text-3xl font-bold mb-6 text-white border-b border-zinc-800 pb-4">
        Infinite Network (Alpha)
      </h1>

      {/* CREATE PROFILE FORM */}
      <form
        onSubmit={handleSubmit}
        className="mb-8 p-6 bg-zinc-900 rounded-xl border border-zinc-800 shadow-2xl space-y-4 w-full max-w-md"
      >
        <h3 className="text-sm font-semibold uppercase tracking-widest text-zinc-500">Create New Profile</h3>
        
        <div>
          <input
            /* Fixed: Added bg-zinc-800 and text-white to ensure visibility */
            className="bg-zinc-800 border border-zinc-700 p-3 w-full rounded-lg text-white placeholder-zinc-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition"
            placeholder="Name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>

        <div>
          <input
            /* Fixed: Added bg-zinc-800 and text-white to ensure visibility */
            className="bg-zinc-800 border border-zinc-700 p-3 w-full rounded-lg text-white placeholder-zinc-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition"
            placeholder="Tagline (e.g. AI Builder)"
            value={form.tagline}
            onChange={(e) => setForm({ ...form, tagline: e.target.value })}
          />
        </div>

        <button
          className="bg-white text-black font-bold px-4 py-3 rounded-lg w-full hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          type="submit"
          disabled={loading}
        >
          {loading ? "Creating..." : "Create Profile"}
        </button>
        
        {error && <p className="text-red-400 text-sm mt-2 font-medium">✕ {error}</p>}
      </form>

      {/* PROFILES LIST */}
      <div className="space-y-4 w-full max-w-md">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-2">Network Members</h3>
        
        {users.length === 0 && !loading && (
          <p className="text-zinc-600 italic">No profiles yet — be the first to join.</p>
        )}
        
        {users.map((user, i) => (
          <div
            key={i}
            className="border border-zinc-800 p-4 bg-zinc-900 rounded-lg shadow hover:border-zinc-600 transition group"
          >
            <h2 className="text-xl font-semibold text-white group-hover:text-blue-400 transition-colors">
              {user.name}
            </h2>
            <p className="text-zinc-400">{user.tagline}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;