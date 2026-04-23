import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { Toast } from "../components/shared/Toast";

describe("Toast", () => {
  it("renders nothing when toast is null", () => {
    const { container } = render(<Toast toast={null} onDismiss={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders error toast with message", () => {
    render(<Toast toast={{ message: "Something failed", type: "error" }} onDismiss={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something failed");
  });

  it("calls onDismiss when dismiss button is clicked", () => {
    const dismiss = vi.fn();
    render(<Toast toast={{ message: "Error", type: "error" }} onDismiss={dismiss} />);

    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));

    expect(dismiss).toHaveBeenCalledOnce();
  });

  it("renders success toast", () => {
    render(<Toast toast={{ message: "Saved!", type: "success" }} onDismiss={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Saved!");
  });
});

describe("BootGate", () => {
  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("renders the loading state while identity boot is in progress", async () => {
    window.history.pushState({}, "", "/dashboard");

    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({
        isAuthenticated: true,
      }),
    }));
    vi.doMock("../context/SystemContext", () => ({
      useSystem: () => ({
        booting: true,
        booted: false,
        bootError: "",
        bootSystem: vi.fn(),
        isAdmin: false,
      }),
    }));

    const { default: App } = await import("../App.jsx");

    render(<App />);

    expect(screen.getByText(/identity boot/i)).toBeInTheDocument();
    expect(screen.getByText(/restoring memory, runs, metrics, and active flows/i)).toBeInTheDocument();
  });

  it("renders the error state and retries boot when requested", async () => {
    window.history.pushState({}, "", "/dashboard");
    const bootSystem = vi.fn().mockResolvedValue({});

    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({
        isAuthenticated: true,
      }),
    }));
    vi.doMock("../context/SystemContext", () => ({
      useSystem: () => ({
        booting: false,
        booted: false,
        bootError: "Boot failed badly",
        bootSystem,
        isAdmin: false,
      }),
    }));

    const { default: App } = await import("../App.jsx");

    render(<App />);

    expect(screen.getByText(/identity boot failed/i)).toBeInTheDocument();
    expect(screen.getByText(/boot failed badly/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /retry boot/i }));

    await waitFor(() => {
      expect(bootSystem).toHaveBeenCalledOnce();
    });
  });
});

describe("TaskDashboard error handling", () => {
  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("shows an error toast instead of alert when task creation fails", async () => {
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});

    vi.doMock("../api/tasks.js", () => ({
      getTasks: vi.fn().mockResolvedValue([]),
      createTask: vi.fn().mockRejectedValue(new Error("API Error (500): server error")),
      completeTask: vi.fn(),
      startTask: vi.fn(),
    }));

    const { default: TaskDashboard } = await import("../components/app/TaskDashboard.jsx");

    render(<TaskDashboard />);

    await screen.findByText(/no active directives/i);

    fireEvent.change(screen.getByPlaceholderText(/initialize new directive/i), {
      target: { value: "Write release checklist" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add/i }));

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("API Error (500): server error");
    expect(alertSpy).not.toHaveBeenCalled();

    alertSpy.mockRestore();
  });
});
