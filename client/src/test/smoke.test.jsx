import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";

import ErrorBoundary from "../components/shared/ErrorBoundary";
import LoginPage from "../components/shared/LoginPage";
import { AuthProvider, useAuth } from "../context/AuthContext";
import { SystemProvider } from "../context/SystemContext";

function AppProviders({ children }) {
  return (
    <BrowserRouter>
      <AuthProvider>
        <SystemProvider>{children}</SystemProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

function AuthStateProbe() {
  const { isAuthenticated, user, token } = useAuth();

  return (
    <div>
      <span data-testid="is-authenticated">{String(isAuthenticated)}</span>
      <span data-testid="has-user">{String(Boolean(user))}</span>
      <span data-testid="token">{token}</span>
    </div>
  );
}

function ThrowingComponent() {
  throw new Error("test error");
}

function makeJwt(payload) {
  const header = window.btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = window.btoa(JSON.stringify(payload));
  return `${header}.${body}.signature`;
}

describe("frontend smoke tests", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("renders LoginPage without crashing", () => {
    render(
      <AppProviders>
        <LoginPage />
      </AppProviders>,
    );

    expect(screen.getByRole("heading", { name: /activate a\.i\.n\.d\.y\./i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /login and boot/i })).toBeInTheDocument();
  });

  it("renders ErrorBoundary fallback when a child throws", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>,
    );

    expect(screen.getByText(/something went wrong loading this page/i)).toBeInTheDocument();

    consoleSpy.mockRestore();
  });

  it("provides an initial unauthenticated auth context state", () => {
    render(
      <AuthProvider>
        <AuthStateProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("is-authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("has-user")).toHaveTextContent("false");
    expect(screen.getByTestId("token")).toHaveTextContent("");
  });

  it("clears an expired stored token on mount", () => {
    const expired = makeJwt({
      sub: "user-1",
      exp: Math.floor(Date.now() / 1000) - 60,
    });
    window.localStorage.setItem("token", expired);
    window.localStorage.setItem("aindy_token", expired);

    render(
      <AuthProvider>
        <AuthStateProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("is-authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("has-user")).toHaveTextContent("false");
    expect(screen.getByTestId("token")).toHaveTextContent("");
    expect(window.localStorage.getItem("token")).toBeNull();
    expect(window.localStorage.getItem("aindy_token")).toBeNull();
  });

  it("AppShell renders without dangerouslySetInnerHTML", async () => {
    vi.resetModules();
    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({ isAuthenticated: true }),
      AuthProvider: ({ children }) => children,
    }));
    vi.doMock("../context/SystemContext", () => ({
      useSystem: () => ({
        booting: false,
        booted: true,
        bootError: "",
        bootSystem: vi.fn(),
        isAdmin: false,
      }),
      SystemProvider: ({ children }) => children,
    }));

    const { default: App } = await import("../App.jsx");
    const { container } = render(<App />);

    const injectedStyles = container.querySelectorAll("style");
    expect(injectedStyles.length).toBe(0);

    vi.resetModules();
    vi.doUnmock("../context/AuthContext");
    vi.doUnmock("../context/SystemContext");
  });

  it("ErrorBoundary reports errors to the backend", async () => {
    vi.resetModules();
    const reportSpy = vi.fn();
    vi.doMock("../api/operator.js", async () => ({
      reportClientError: reportSpy,
    }));

    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    function Bomb() { throw new Error("test explosion"); }

    const { default: EB } = await import("../components/shared/ErrorBoundary.jsx");
    render(<EB><Bomb /></EB>);

    expect(reportSpy).toHaveBeenCalledOnce();
    const [payload] = reportSpy.mock.calls[0];
    expect(payload.error_message).toContain("test explosion");
    expect(payload.error_type).toBe("boundary");

    spy.mockRestore();
    vi.resetModules();
    vi.doUnmock("../api/operator.js");
  });

  it("reportClientError does not throw when fetch fails", async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error("Network error"));
    vi.stubGlobal("fetch", fetchSpy);

    const { reportClientError } = await import("../api/operator.js");

    await expect(reportClientError({ error_message: "test" })).resolves.toBeUndefined();

    vi.unstubAllGlobals();
  });
});
