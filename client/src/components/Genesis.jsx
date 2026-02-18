import { useState, useRef, useEffect } from "react";

export default function Genesis() {
  const [started, setStarted] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);

  const bottomRef = useRef(null);

  // --- Fixed: Merged the two startGenesis functions ---
  const startGenesis = async () => {
    setLoading(true);
    try {
      const response = await fetch("http://localhost:8000/genesis/session", {
        method: "POST"
      });

      const data = await response.json();
      setSessionId(data.session_id);

      setStarted(true);
      setMessages([
        {
          role: "ai",
          content: "Initialization sequence active. I have established a secure session. What do you want your life to look like in 5–10 years?"
        }
      ]);
    } catch (err) {
      console.error("Failed to start session:", err);
      alert("A.I.N.D.Y. Connection Error: Ensure backend is running on port 8000.");
    } finally {
      setLoading(false);
    }
  };

  const scrollToBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch("http://localhost:8000/genesis/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // --- Pass the sessionId so the backend tracks this specific plan ---
        body: JSON.stringify({ 
          message: userMessage.content,
          session_id: sessionId 
        })
      });

      const data = await response.json();

      setTimeout(() => {
        setMessages((prev) => [
          ...prev,
          { role: "ai", content: data.reply }
        ]);
        setLoading(false);
      }, 600);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        { role: "ai", content: "Protocol error. Sync failed. Please try again." }
      ]);
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex justify-center bg-[#09090b] text-zinc-100">
      <div className="w-full max-w-2xl px-6 py-16 flex flex-col">
        {!started ? (
          <div className="text-center space-y-8 my-auto">
            <div className="space-y-4">
              <h1 className="text-4xl font-bold tracking-tighter text-white">
                PROJECT <span className="text-[#00ffaa]">GENESIS</span>
              </h1>
              <p className="text-zinc-500 max-w-sm mx-auto">
                Define your long-term strategic direction. A.I.N.D.Y. is ready to architect your MasterPlan.
              </p>
            </div>
            <button
              onClick={startGenesis}
              disabled={loading}
              className="px-8 py-4 bg-white text-black font-bold rounded-lg hover:bg-[#00ffaa] transition-colors shadow-[0_0_20px_rgba(255,255,255,0.1)] disabled:opacity-50"
            >
              {loading ? "ESTABLISHING LINK..." : "INITIALIZE"}
            </button>
          </div>
        ) : (
          <>
            {/* CHAT STREAM */}
            <div className="flex-1 space-y-6 mb-6 overflow-y-auto pr-2 custom-scrollbar">
              {messages.map((msg, index) => (
                <div
                  key={index}
                  className={`flex ${msg.role === "ai" ? "justify-start" : "justify-end"}`}
                >
                  <div
                    className={`max-w-[85%] px-5 py-4 rounded-xl text-sm leading-relaxed ${
                      msg.role === "ai"
                        ? "bg-zinc-900 border border-zinc-800 text-zinc-200"
                        : "bg-[#00ffaa] text-black font-bold shadow-[0_0_15px_rgba(0,255,170,0.2)]"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-zinc-900 border border-zinc-800 text-zinc-500 px-5 py-3 rounded-xl text-xs animate-pulse">
                    A.I.N.D.Y. is thinking...
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {/* INPUT FORM */}
            <form onSubmit={handleSubmit} className="mt-auto relative">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={2}
                disabled={loading}
                placeholder="Transmitting signal..."
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl p-4 text-white resize-none focus:outline-none focus:border-[#00ffaa]/50 transition-all placeholder-zinc-600"
              />
              <button
                type="submit"
                disabled={loading}
                className="absolute right-3 bottom-3 px-5 py-2 bg-white text-black font-bold rounded-lg disabled:opacity-50 hover:bg-[#00ffaa] transition-all"
              >
                {loading ? "..." : "SEND"}
              </button>
            </form>
          </>
        )}
      </div>

      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 4px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #27272a; border-radius: 10px; }
      `}</style>
    </div>
  );
}