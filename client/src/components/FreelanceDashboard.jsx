import React, { useEffect, useState } from "react";
// Tailwind-based React component designed to be dropped into your Vite/React app
// Uses shadcn/ui components style (available) and recharts for lightweight visuals

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { BarChart, Bar, XAxis, YAxis, Tooltip as ReTooltip, ResponsiveContainer } from "recharts";

export default function FreelanceDashboard() {
  const [orders, setOrders] = useState([]);
  const [feedback, setFeedback] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  async function fetchOrders() {
    const res = await fetch('/freelance/orders');
    if (!res.ok) throw new Error('Failed to fetch orders');
    return res.json();
  }

  async function fetchFeedback() {
    const res = await fetch('/freelance/feedback');
    if (!res.ok) throw new Error('Failed to fetch feedback');
    return res.json();
  }

  async function fetchMetrics() {
    const res = await fetch('/freelance/metrics/latest');
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
        if (!mounted) return;
        setError(err.message);
      })
      .finally(() => mounted && setLoading(false));
    return () => (mounted = false);
  }, []);

  const ratingsDistribution = (() => {
    const map = { '1': 0, '2': 0, '3': 0, '4': 0, '5': 0 };
    feedback.forEach((f) => {
      const r = (f.rating || 0).toString();
      if (map[r] !== undefined) map[r]++;
    });
    return Object.keys(map).map((k) => ({ rating: k, count: map[k] }));
  })();

  const topOrders = orders.slice(0, 8);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Freelance Dashboard</h1>
        <div className="flex gap-2 items-center">
          <Button onClick={() => window.location.reload()}>Refresh</Button>
          <Tooltip content="Open the Freelancing Automation brief">
            <a href={'/mnt/data/Freelancing Automation Plan .docx'} className="text-sm underline">Source Doc</a>
          </Tooltip>
        </div>
      </div>

      {error && (
        <div className="mb-4 text-sm text-red-600">Error: {error}</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <Card>
          <CardContent>
            <div className="text-sm uppercase text-muted-foreground">Total Orders</div>
            <div className="text-2xl font-bold">{orders.length}</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <div className="text-sm uppercase text-muted-foreground">Delivered</div>
            <div className="text-2xl font-bold">{orders.filter(o=>o.status==='delivered').length}</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <div className="text-sm uppercase text-muted-foreground">Avg Rating</div>
            <div className="text-2xl font-bold">
              {feedback.length ? ( (feedback.reduce((s,f)=>s+(f.rating||0),0)/feedback.length).toFixed(2) ) : '—'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <div className="text-sm uppercase text-muted-foreground">Total Revenue</div>
            <div className="text-2xl font-bold">{metrics ? `$${metrics.total_revenue.toFixed(2)}` : '—'}</div>
            <div className="text-xs text-muted-foreground">Last updated: {metrics ? new Date(metrics.date).toLocaleString() : '—'}</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2">
          <Card>
            <CardContent>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-medium">Recent Orders</h2>
                <div className="text-sm text-muted-foreground">Showing latest {topOrders.length}</div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full table-auto border-collapse">
                  <thead>
                    <tr className="text-left text-sm text-muted-foreground">
                      <th className="pb-2">#</th>
                      <th className="pb-2">Client</th>
                      <th className="pb-2">Service</th>
                      <th className="pb-2">Price</th>
                      <th className="pb-2">Status</th>
                      <th className="pb-2">Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topOrders.map((o) => (
                      <tr key={o.id} className="border-t">
                        <td className="py-2 text-sm">{o.id}</td>
                        <td className="py-2 text-sm">{o.client_name}</td>
                        <td className="py-2 text-sm">{o.service_type}</td>
                        <td className="py-2 text-sm">${o.price?.toFixed(2)}</td>
                        <td className="py-2 text-sm">{o.status}</td>
                        <td className="py-2 text-sm">{new Date(o.created_at).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </section>

        <aside>
          <Card className="mb-4">
            <CardContent>
              <h3 className="text-md font-medium mb-2">Ratings Distribution</h3>
              <div style={{ width: '100%', height: 180 }}>
                <ResponsiveContainer>
                  <BarChart data={ratingsDistribution}>
                    <XAxis dataKey="rating" />
                    <YAxis allowDecimals={false} />
                    <ReTooltip />
                    <Bar dataKey="count" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <h3 className="text-md font-medium mb-2">Latest Feedback</h3>
              <div className="space-y-3">
                {feedback.slice(0,5).map((f) => (
                  <div key={f.id} className="p-2 border rounded">
                    <div className="text-sm font-medium">Order #{f.order_id} — {f.rating || '—'}/5</div>
                    <div className="text-xs text-muted-foreground">{f.feedback_text ? f.feedback_text : 'No text feedback.'}</div>
                  </div>
                ))}
                {!feedback.length && <div className="text-sm text-muted-foreground">No feedback yet.</div>}
              </div>
            </CardContent>
          </Card>
        </aside>
      </div>

    </div>
  );
}
