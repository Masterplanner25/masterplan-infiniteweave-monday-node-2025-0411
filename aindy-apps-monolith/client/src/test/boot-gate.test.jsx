import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("BootGate error state", () => {
  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    vi.doUnmock("../context/AuthContext");
    vi.doUnmock("../context/SystemContext");
  });

  it("shows sign-out button when boot fails", async () => {
    window.history.pushState({}, "", "/dashboard");

    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({
        isAuthenticated: true,
        isAdmin: false,
        logout: vi.fn(),
      }),
    }));
    vi.doMock("../context/SystemContext", () => ({
      useSystem: () => ({
        booting: false,
        booted: false,
        bootError: "Server unreachable",
        bootSystem: vi.fn(),
      }),
    }));

    const { default: App } = await import("../App.jsx");
    render(<App />);

    expect(screen.getByText(/identity boot failed/i)).toBeInTheDocument();
    expect(screen.getByText(/server unreachable/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("calls logout when sign-out button is clicked", async () => {
    window.history.pushState({}, "", "/dashboard");
    const logoutMock = vi.fn();

    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({
        isAuthenticated: true,
        isAdmin: false,
        logout: logoutMock,
      }),
    }));
    vi.doMock("../context/SystemContext", () => ({
      useSystem: () => ({
        booting: false,
        booted: false,
        bootError: "Server unreachable",
        bootSystem: vi.fn(),
      }),
    }));

    const { default: App } = await import("../App.jsx");
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => {
      expect(logoutMock).toHaveBeenCalledOnce();
    });
  });
});
