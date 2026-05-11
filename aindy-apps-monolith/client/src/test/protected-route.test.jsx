import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("ProtectedRoute", () => {
  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  async function renderWithAuth(
    authValue,
    initialPath = "/platform/agent",
    routePath = "/platform/agent",
  ) {
    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => authValue,
    }));

    const { default: ProtectedRoute } = await import("../components/shared/ProtectedRoute.jsx");

    return render(
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={<div>Login Page</div>} />
          <Route path="/dashboard" element={<div>Dashboard</div>} />
          <Route element={<ProtectedRoute requireAdmin />}>
            <Route path={routePath} element={<div>Platform Page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
  }

  it("redirects unauthenticated users to /login", async () => {
    await renderWithAuth({ isAuthenticated: false, isAdmin: false });
    expect(screen.getByText("Login Page")).toBeInTheDocument();
    expect(screen.queryByText("Platform Page")).not.toBeInTheDocument();
  });

  it("redirects authenticated non-admin users to /dashboard", async () => {
    await renderWithAuth({ isAuthenticated: true, isAdmin: false });
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Platform Page")).not.toBeInTheDocument();
  });

  it("renders platform content for authenticated admin users", async () => {
    await renderWithAuth({ isAuthenticated: true, isAdmin: true });
    expect(screen.getByText("Platform Page")).toBeInTheDocument();
  });

  it.each([
    "/platform/agent",
    "/platform/flows",
    "/platform/observability",
    "/platform/health",
    "/platform/executions",
    "/platform/approvals",
    "/platform/registry",
    "/platform/trace",
  ])("blocks non-admin users from %s", async (path) => {
    await renderWithAuth(
      { isAuthenticated: true, isAdmin: false },
      path,
      path,
    );
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.queryByText("Platform Page")).not.toBeInTheDocument();
  });

  it("renders AdminAccessRequired when AgentConsole is reached with isAdmin=false", async () => {
    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({ isAuthenticated: true, isAdmin: false }),
    }));
    vi.doMock("../context/SystemContext", () => ({
      useSystem: () => ({ system: {} }),
    }));

    const { default: AgentConsole } = await import("../components/platform/AgentConsole.jsx");
    render(<AgentConsole />);

    expect(screen.getByText("Admin Access Required")).toBeInTheDocument();
  });
});
