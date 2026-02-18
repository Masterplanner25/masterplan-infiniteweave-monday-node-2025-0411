import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip as ReTooltip, ResponsiveContainer } from "recharts";

export default function FreelanceDashboard() {
  const [orders, setOrders] = useState([]);
  const [feedback, setFeedback] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // --- API FIX: Added full paths ---
  const API_BASE = "http://localhost:8000";

  async function fetchOrders() {
    const res = await fetch(`${API_BASE}/freelance/orders`);
    if (!res.ok) throw new Error('Failed to fetch orders');
    return res.json();
  }

  async function fetchFeedback() {
    const res = await fetch(`${API_BASE}/freelance/feedback`);
    if (!res.ok) throw new Error('Failed to fetch feedback');
    return res.json();
  }

  async function fetchMetrics() {
    const res = await fetch(`${API_BASE}/freelance/metrics/latest`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error('Failed to fetch metrics');
    return res.json();
  }

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    Promise.all([fetchOrders(), fetchFeedback(), fetchMetrics()])
      .then(([o, f, m]) => {
        if (!mounted) return;
        setOrders(o || []);
        setFeedback(f || []);
        setMetrics(m || null);
      })
      .catch((err) => {
        console.error(err);
        if (mounted) setError(err.message);
      })
      .finally(() => mounted && setLoading(false));
    return () => (mounted = false);
  }, []);

  // --- Data Processing ---
  const ratingsDistribution = (() => {
    const map = { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 };
    feedback.forEach((f) => {
      const r = (f.rating || 0).toString();
      if (map[r] !== undefined) map[r]++;
    });
    return Object.keys(map).map((k) => ({ rating: k, count: map[k] }));
  })();

  const topOrders = orders.slice(0, 8);

  // --- Common Styles for Cards ---
  const cardClass = "bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg";

  return (
    <div className="p-6 max-w-7xl mx-auto bg-black text-zinc-100 min-h-screen">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">Freelance Hub</h1>
          <p className="text-zinc-500 text-sm">Automated delivery & feedback stream</p>
        </div>
        <button 
          onClick={() => window.location.reload()}
          className="bg-zinc-100 text-black px-4 py-2 rounded-lg font-bold hover:bg-zinc-300 transition"
        >
          Refresh Data
        </button>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-500 text-red-400 rounded-lg">
          ⚠️ {error}
        </div>
      )}

      {/* STATS GRID */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className={cardClass}>
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Total Orders</div>
          <div className="text-3xl font-bold">{orders.length}</div>
        </div>
        <div className={cardClass}>
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Delivered</div>
          <div className="text-3xl font-bold text-green-500">
            {orders.filter(o => o.status === 'delivered').length}
          </div>
        </div>
        <div className={cardClass}>
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Avg Rating</div>
          <div className="text-3xl font-bold text-yellow-500">
            {feedback.length ? ((feedback.reduce((s, f) => s + (f.rating || 0), 0) / feedback.length).toFixed(2)) : '—'}
          </div>
        </div>
        <div className={cardClass}>
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-1">Revenue</div>
          <div className="text-3xl font-bold text-blue-400">
            {metrics ? `$${metrics.total_revenue.toLocaleString()}` : '—'}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* RECENT ORDERS TABLE */}
        <section className="lg:col-span-2">
          <div className={cardClass}>
            <h2 className="text-lg font-semibold mb-4 border-b border-zinc-800 pb-2">Recent Stream</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="text-zinc-500 text-xs uppercase border-b border-zinc-800">
                    <th className="pb-3 font-medium">Client</th>
                    <th className="pb-3 font-medium">Service</th>
                    <th className="pb-3 font-medium">Price</th>
                    <th className="pb-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {topOrders.map((o) => (
                    <tr key={o.id} className="hover:bg-zinc-800/50 transition">
                      <td className="py-3 text-sm font-medium">{o.client_name}</td>
                      <td className="py-3 text-sm text-zinc-400">{o.service_type}</td>
                      <td className="py-3 text-sm text-blue-400">${o.price?.toFixed(2)}</td>
                      <td className="py-3">
                        <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded-full ${
                          o.status === 'delivered' ? 'bg-green-500/10 text-green-500' : 'bg-zinc-800 text-zinc-400'
                        }`}>
                          {o.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* CHARTS & FEEDBACK */}
        <aside className="space-y-6">
          <div className={cardClass}>
            <h3 className="text-sm font-bold text-zinc-400 mb-4 uppercase">Ratings Mix</h3>
            <div style={{ width: '100%', height: 180 }}>
              <ResponsiveContainer>
                <BarChart data={ratingsDistribution}>
                  <XAxis dataKey="rating" stroke="#52525b" fontSize={12} />
                  <YAxis hide />
                  <ReTooltip 
                    contentStyle={{ backgroundColor: '#18181b', border: '1px solid #3f3f46' }}
                    itemStyle={{ color: '#fff' }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className={cardClass}>
            <h3 className="text-sm font-bold text-zinc-400 mb-4 uppercase">Latest Feedback</h3>
            <div className="space-y-3">
              {feedback.slice(0, 4).map((f) => (
                <div key={f.id} className="p-3 bg-zinc-800/40 rounded-lg border border-zinc-700/50">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs font-bold text-yellow-500">{f.rating}/5 Stars</span>
                    <span className="text-[10px] text-zinc-500">#{f.order_id}</span>
                  </div>
                  <div className="text-xs text-zinc-300 italic">"{f.feedback_text || 'No text provided.'}"</div>
                </div>
              ))}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}