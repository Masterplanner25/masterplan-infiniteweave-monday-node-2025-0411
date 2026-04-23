import { act, render, screen } from "@testing-library/react";

import { setStoredToken } from "../api";
import { AuthProvider, useAuth } from "../context/AuthContext";

function AuthProbe() {
  const { isAuthenticated, user } = useAuth();

  return (
    <div>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="user">{user ? user.email || "has-user" : "no-user"}</span>
    </div>
  );
}

function buildJwt(payload) {
  const header = window.btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = window.btoa(JSON.stringify(payload));
  return `${header}.${body}.fake-signature`;
}

describe("AuthContext", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows unauthenticated when no token is stored", () => {
    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("user")).toHaveTextContent("no-user");
  });

  it("shows unauthenticated when stored token is expired", () => {
    const expiredToken = buildJwt({
      sub: "user-1",
      email: "a@b.com",
      exp: Math.floor(Date.now() / 1000) - 3600,
    });
    setStoredToken(expiredToken);

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("user")).toHaveTextContent("no-user");
  });

  it("shows authenticated when stored token is valid", () => {
    const validToken = buildJwt({
      sub: "user-1",
      email: "a@b.com",
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    setStoredToken(validToken);

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("authenticated")).toHaveTextContent("true");
    expect(screen.getByTestId("user")).toHaveTextContent("a@b.com");
  });

  it("clears auth state when aindy:session-expired event fires", async () => {
    const validToken = buildJwt({
      sub: "user-1",
      email: "a@b.com",
      exp: Math.floor(Date.now() / 1000) + 3600,
    });
    setStoredToken(validToken);

    render(
      <AuthProvider>
        <AuthProbe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("authenticated")).toHaveTextContent("true");

    await act(async () => {
      window.dispatchEvent(new CustomEvent("aindy:session-expired"));
    });

    expect(screen.getByTestId("authenticated")).toHaveTextContent("false");
    expect(screen.getByTestId("user")).toHaveTextContent("no-user");
  });
});
