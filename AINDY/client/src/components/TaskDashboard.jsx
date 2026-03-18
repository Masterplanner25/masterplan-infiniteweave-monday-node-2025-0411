import React, { useEffect, useState } from "react";
import { getTasks, createTask, completeTask, startTask } from "../api";

export default function TaskDashboard() {
  const [tasks, setTasks] = useState([]);
  const [newTask, setNewTask] = useState("");
  const [loading, setLoading] = useState(true);
  const [velocityMessage, setVelocityMessage] = useState("");

  const fetchTasks = async () => {
    try {
      const data = await getTasks();
      // Sort: Pending first, then by ID
      const sorted = data.sort((a, b) => (a.status === "completed" ? 1 : -1));
      setTasks(sorted);
    } catch (err) {
      console.error("Failed to load tasks", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newTask.trim()) return;
    
    try {
      await createTask({ name: newTask, priority: "medium" });
      setNewTask("");
      fetchTasks();
    } catch (err) {
      alert("Failed to create task");
    }
  };

  const handleComplete = async (taskName) => {
    try {
      const res = await completeTask(taskName);
      // Show the backend confirmation (contains TWR score)
      setVelocityMessage(res); 
      fetchTasks();
      
      // Clear message after 3s
      setTimeout(() => setVelocityMessage(""), 5000);
    } catch (err) {
      alert("Failed to complete task");
    }
  };

  const handleStart = async (taskName) => {
    await startTask(taskName);
    fetchTasks();
  };

  return (
    <div style={styles.container}>
      <h2 style={styles.title}>🚀 Execution Engine</h2>
      
      {/* --- VELOCITY FEEDBACK --- */}
      {velocityMessage && (
        <div style={styles.successBanner}>
          {velocityMessage}
        </div>
      )}

      {/* --- INPUT --- */}
      <form onSubmit={handleCreate} style={styles.form}>
        <input 
          style={styles.input} 
          placeholder="Initialize new directive..." 
          value={newTask}
          onChange={(e) => setNewTask(e.target.value)}
        />
        <button type="submit" style={styles.addButton}>ADD</button>
      </form>

      {/* --- TASK LIST --- */}
      <div style={styles.list}>
        {loading ? <p>Syncing...</p> : tasks.map((task) => (
          <div key={task.task_name} style={styles.taskCard(task.status)}>
            <div>
              <div style={styles.taskName}>{task.task_name}</div>
              <div style={styles.taskMeta}>
                Status: <span style={{color: getStatusColor(task.status)}}>{task.status.toUpperCase()}</span>
                {task.time_spent > 0 && ` • Time: ${(task.time_spent / 60).toFixed(1)}m`}
              </div>
            </div>
            
            <div style={styles.actions}>
              {task.status !== "completed" && (
                <>
                  {task.status !== "in_progress" && (
                    <button onClick={() => handleStart(task.task_name)} style={styles.actionBtn}>
                      ▶ Start
                    </button>
                  )}
                  <button onClick={() => handleComplete(task.task_name)} style={styles.completeBtn}>
                    ✅ Done
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
        
        {!loading && tasks.length === 0 && (
          <p style={{color: "#666", textAlign: "center"}}>No active directives.</p>
        )}
      </div>
    </div>
  );
}

// --- HELPERS & STYLES ---
const getStatusColor = (s) => {
  if (s === "completed") return "#00ffaa";
  if (s === "in_progress") return "#6cf";
  return "#888";
};

const styles = {
  container: { maxWidth: "700px", margin: "0 auto", padding: "2rem", color: "#eaeaea" },
  title: { borderLeft: "4px solid #f6f", paddingLeft: "12px", marginBottom: "24px" },
  successBanner: {
    background: "rgba(0, 255, 170, 0.1)", border: "1px solid #00ffaa", color: "#00ffaa",
    padding: "12px", borderRadius: "6px", marginBottom: "20px", fontWeight: "bold"
  },
  form: { display: "flex", gap: "12px", marginBottom: "32px" },
  input: { flex: 1, padding: "12px", background: "#111", border: "1px solid #333", color: "#fff", borderRadius: "6px" },
  addButton: { background: "#f6f", color: "#000", border: "none", padding: "0 24px", fontWeight: "bold", borderRadius: "6px", cursor: "pointer" },
  list: { display: "flex", flexDirection: "column", gap: "12px" },
  taskCard: (status) => ({
    display: "flex", justifyContent: "space-between", alignItems: "center",
    background: "#1a1a1a", border: "1px solid #333", padding: "16px", borderRadius: "8px",
    opacity: status === "completed" ? 0.5 : 1
  }),
  taskName: { fontSize: "16px", fontWeight: "500", marginBottom: "4px" },
  taskMeta: { fontSize: "12px", color: "#666" },
  actions: { display: "flex", gap: "8px" },
  actionBtn: { background: "#222", border: "1px solid #444", color: "#ccc", padding: "6px 12px", borderRadius: "4px", cursor: "pointer" },
  completeBtn: { background: "rgba(0, 255, 170, 0.2)", border: "1px solid #00ffaa", color: "#00ffaa", padding: "6px 12px", borderRadius: "4px", cursor: "pointer" }
};