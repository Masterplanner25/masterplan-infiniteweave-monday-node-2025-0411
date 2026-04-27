import { Suspense, lazy, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./context/AuthContext";
import { SystemProvider } from "./context/SystemContext";

const AgentConsole = lazy(() => import("./components/platform/AgentConsole"));
const FlowEngineConsole = lazy(() => import("./components/platform/FlowEngineConsole"));
const ObservabilityDashboard = lazy(() => import("./components/platform/ObservabilityDashboard"));
const HealthDashboard = lazy(() => import("./components/platform/HealthDashboard"));
const ExecutionConsole = lazy(() => import("./components/platform/ExecutionConsole"));
const AgentApprovalInbox = lazy(() => import("./components/platform/AgentApprovalInbox"));
const AgentRegistry = lazy(() => import("./components/platform/AgentRegistry"));
const RippleTraceViewer = lazy(() => import("./components/platform/RippleTraceViewer"));

function redirectToApp(path: string) {
  const base = import.meta.env.VITE_APP_BASE_URL ?? "/";
  const normalizedBase = base.endsWith("/") ? base.slice(0, -1) : base;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  window.location.href = `${normalizedBase}${normalizedPath}` || normalizedPath;
}

function PlatformGuard({ children }: { children: ReactNode }) {
  const { isAdmin, isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    redirectToApp("/login");
    return null;
  }

  if (!isAdmin) {
    redirectToApp("/");
    return null;
  }

  return <>{children}</>;
}

export default function PlatformApp() {
  return (
    <AuthProvider>
      <SystemProvider>
        <BrowserRouter basename="/platform">
          <PlatformGuard>
            <Suspense fallback={<div>Loading...</div>}>
              <Routes>
                <Route path="/" element={<Navigate to="/agent" replace />} />
                <Route path="/agent" element={<AgentConsole />} />
                <Route path="/flows" element={<FlowEngineConsole />} />
                <Route path="/observability" element={<ObservabilityDashboard />} />
                <Route path="/health" element={<HealthDashboard />} />
                <Route path="/executions" element={<ExecutionConsole />} />
                <Route path="/approvals" element={<AgentApprovalInbox />} />
                <Route path="/registry" element={<AgentRegistry />} />
                <Route path="/trace" element={<RippleTraceViewer />} />
                <Route path="*" element={<Navigate to="/agent" replace />} />
              </Routes>
            </Suspense>
          </PlatformGuard>
        </BrowserRouter>
      </SystemProvider>
    </AuthProvider>
  );
}
