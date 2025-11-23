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
    <div className="p-10 font-sans bg-gray-50 min-h-screen">
      <h1 className="text-3xl font-bold mb-6">Infinite Network (Alpha)</h1>

      <form
        onSubmit={handleSubmit}
        className="mb-8 p-4 bg-white rounded-lg shadow-md space-y-3 w-full max-w-md"
      >
        <input
          className="border p-2 w-full rounded"
          placeholder="Name"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <input
          className="border p-2 w-full rounded"
          placeholder="Tagline (e.g. AI Builder)"
          value={form.tagline}
          onChange={(e) => setForm({ ...form, tagline: e.target.value })}
        />
        <button
          className="bg-black text-white px-4 py-2 rounded w-full"
          type="submit"
          disabled={loading}
        >
          {loading ? "Creating..." : "Create Profile"}
        </button>
        {error && <p className="text-red-600 text-sm">{error}</p>}
      </form>

      <div className="space-y-4 w-full max-w-md">
        {users.length === 0 && (
          <p className="text-gray-500">No profiles yet — create one above!</p>
        )}
        {users.map((user, i) => (
          <div
            key={i}
            className="border p-4 bg-white rounded-lg shadow hover:shadow-lg transition"
          >
            <h2 className="text-xl font-semibold">{user.name}</h2>
            <p className="text-gray-600">{user.tagline}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
