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
});
