import { lazy, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import ErrorBoundary, { RouteErrorBoundary } from "./components/shared/ErrorBoundary";
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

function platformRoute(name: string, element: ReactNode) {
  return (
    <RouteErrorBoundary name={name} layer="platform" domain={name}>
      {element}
    </RouteErrorBoundary>
  );
}

export default function PlatformApp() {
  return (
    <AuthProvider>
      <SystemProvider>
        <BrowserRouter basename="/platform">
          <PlatformGuard>
            <ErrorBoundary layer="platform">
              <Routes>
                <Route path="/" element={<Navigate to="/agent" replace />} />
                <Route path="/agent" element={platformRoute("Agent Console", <AgentConsole />)} />
                <Route path="/flows" element={platformRoute("Flow Engine", <FlowEngineConsole />)} />
                <Route path="/observability" element={platformRoute("Observability", <ObservabilityDashboard />)} />
                <Route path="/health" element={platformRoute("Health", <HealthDashboard />)} />
                <Route path="/executions" element={platformRoute("Executions", <ExecutionConsole />)} />
                <Route path="/approvals" element={platformRoute("Approvals", <AgentApprovalInbox />)} />
                <Route path="/registry" element={platformRoute("Registry", <AgentRegistry />)} />
                <Route path="/trace" element={platformRoute("Trace", <RippleTraceViewer />)} />
                <Route path="*" element={<Navigate to="/agent" replace />} />
              </Routes>
            </ErrorBoundary>
          </PlatformGuard>
        </BrowserRouter>
      </SystemProvider>
    </AuthProvider>
  );
}
