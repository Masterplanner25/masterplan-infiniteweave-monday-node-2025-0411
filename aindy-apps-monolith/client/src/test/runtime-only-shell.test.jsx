import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("runtime-only shell", () => {
  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("hides app-profile navigation groups in AppShell", async () => {
    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({
        user: { email: "runtime@aindy.test" },
        isAdmin: true,
        logout: vi.fn(),
      }),
    }));
    vi.doMock("../context/SystemContext", () => ({
      useSystem: () => ({
        system: {
          runtime: {
            boot_mode: "runtime-only",
          },
        },
      }),
    }));

    const { default: AppShell } = await import("../components/shared/AppShell.jsx");

    render(
      <MemoryRouter initialEntries={["/memory"]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/memory" element={<div>Memory content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/runtime-only mode/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /memory/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /identity/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /agent console/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /tasks/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /analytics/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /executions/i })).not.toBeInTheDocument();
  });

  it("redirects app-profile routes to memory in runtime-only mode", async () => {
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
        booted: true,
        bootError: "",
        bootSystem: vi.fn(),
        system: {
          runtime: {
            boot_mode: "runtime-only",
          },
        },
      }),
    }));
    vi.doMock("../components/app/MemoryBrowser", () => ({
      default: () => <div>Runtime Memory</div>,
    }));

    const { default: App } = await import("../App.jsx");

    render(<App />);

    expect(await screen.findByText("Runtime Memory")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/memory");
  });
});
