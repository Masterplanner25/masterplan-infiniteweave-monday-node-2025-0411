import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { EmptyState } from "../components/shared/EmptyState";
import { LoadingPanel } from "../components/shared/LoadingPanel";
import Sidebar from "../components/shared/Sidebar";
import { Toast } from "../components/shared/Toast";

vi.mock("../context/AuthContext", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    useAuth: () => ({
      token: null,
      user: { is_admin: true },
      isAdmin: true,
      isAuthenticated: true,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
      setToken: vi.fn(),
    }),
  };
});

vi.mock("../api/agent.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    getAgentRuns: vi.fn().mockResolvedValue([]),
  };
});

describe("LoadingPanel", () => {
  it("renders the requested number of skeleton lines", () => {
    render(<LoadingPanel lines={5} label="Loading..." />);
    expect(screen.getAllByTestId("loading-panel-line")).toHaveLength(5);
  });
});

describe("EmptyState", () => {
  it("renders the message and optional hint", () => {
    render(<EmptyState message="Nothing here" hint="Try again later" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Try again later")).toBeInTheDocument();
  });
});

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

    fireEvent.click(screen.getByRole("button", { name: /^retry$/i }));

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

describe("RippleTraceViewer insight tabs", () => {
  beforeEach(() => {
    vi.doMock("../context/AuthContext", () => ({
      useAuth: () => ({
        token: null,
        user: { is_admin: true },
        isAdmin: true,
        isAuthenticated: true,
        login: vi.fn(),
        register: vi.fn(),
        logout: vi.fn(),
        setToken: vi.fn(),
      }),
    }));
  });

  afterEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
  });

  it("renders tab bar when trace data is loaded", async () => {
    vi.doMock("../api/rippletrace.js", () => ({
      getRippleTraceGraph: vi.fn().mockResolvedValue({
        nodes: [
          {
            id: "node-1",
            type: "execution.started",
            node_kind: "system_event",
            payload: {},
            timestamp: "2026-01-01T00:00:00Z",
            source: "test",
          },
        ],
        edges: [],
        root_event: { id: "node-1", type: "execution.started" },
        terminal_events: [],
        ripple_span: { node_count: 1, edge_count: 0, depth: 0, terminal_count: 0 },
        insights: {
          summary: "Loaded",
          root_cause: null,
          dominant_path: [],
          failure_clusters: [],
          recommendations: [],
        },
      }),
      getDropPointNarrative: vi.fn(),
      getDropPointPrediction: vi.fn(),
      getDropPointRecommendation: vi.fn(),
      getCausalChain: vi.fn(),
      getLearningStats: vi.fn(),
    }));

    const { default: RippleTraceViewer } = await import("../components/platform/RippleTraceViewer.jsx");

    render(<RippleTraceViewer />);

    fireEvent.change(screen.getByPlaceholderText(/enter trace_id/i), {
      target: { value: "trace-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /load trace/i }));

    expect(await screen.findByRole("button", { name: "Graph" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Narrative" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Predictions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recommendations" })).toBeInTheDocument();
  });

  it("shows EmptyState in Narrative tab when no drop_point_id", async () => {
    vi.doMock("../api/rippletrace.js", () => ({
      getRippleTraceGraph: vi.fn().mockResolvedValue({
        nodes: [
          {
            id: "node-1",
            type: "execution.started",
            node_kind: "system_event",
            payload: {},
            timestamp: "2026-01-01T00:00:00Z",
            source: "test",
          },
        ],
        edges: [],
        root_event: { id: "node-1", type: "execution.started" },
        terminal_events: [],
        ripple_span: { node_count: 1, edge_count: 0, depth: 0, terminal_count: 0 },
        insights: {
          summary: "Loaded",
          root_cause: null,
          dominant_path: [],
          failure_clusters: [],
          recommendations: [],
        },
      }),
      getDropPointNarrative: vi.fn(),
      getDropPointPrediction: vi.fn(),
      getDropPointRecommendation: vi.fn(),
      getCausalChain: vi.fn(),
      getLearningStats: vi.fn(),
    }));

    const { default: RippleTraceViewer } = await import("../components/platform/RippleTraceViewer.jsx");

    render(<RippleTraceViewer />);

    fireEvent.change(screen.getByPlaceholderText(/enter trace_id/i), {
      target: { value: "trace-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /load trace/i }));
    await screen.findByRole("button", { name: "Narrative" });

    fireEvent.click(screen.getByRole("button", { name: "Narrative" }));

    expect(
      await screen.findByText("No drop point linked to this trace.")
    ).toBeInTheDocument();
  });

  it("shows EmptyState in Predictions tab when no drop_point_id", async () => {
    vi.doMock("../api/rippletrace.js", () => ({
      getRippleTraceGraph: vi.fn().mockResolvedValue({
        nodes: [
          {
            id: "node-1",
            type: "execution.started",
            node_kind: "system_event",
            payload: {},
            timestamp: "2026-01-01T00:00:00Z",
            source: "test",
          },
        ],
        edges: [],
        root_event: { id: "node-1", type: "execution.started" },
        terminal_events: [],
        ripple_span: { node_count: 1, edge_count: 0, depth: 0, terminal_count: 0 },
        insights: {
          summary: "Loaded",
          root_cause: null,
          dominant_path: [],
          failure_clusters: [],
          recommendations: [],
        },
      }),
      getDropPointNarrative: vi.fn(),
      getDropPointPrediction: vi.fn(),
      getDropPointRecommendation: vi.fn(),
      getCausalChain: vi.fn(),
      getLearningStats: vi.fn().mockResolvedValue({
        accuracy: 0,
        total_predictions: 0,
        false_positive_rate: 0,
      }),
    }));

    const { default: RippleTraceViewer } = await import("../components/platform/RippleTraceViewer.jsx");

    render(<RippleTraceViewer />);

    fireEvent.change(screen.getByPlaceholderText(/enter trace_id/i), {
      target: { value: "trace-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /load trace/i }));
    await screen.findByRole("button", { name: "Predictions" });

    fireEvent.click(screen.getByRole("button", { name: "Predictions" }));

    expect(
      await screen.findByText("No drop point linked to this trace.")
    ).toBeInTheDocument();
  });
});

describe("Sidebar navigation", () => {
  it("renders without error when authenticated", () => {
    const { container } = render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(container.firstChild).not.toBeNull();
  });

  it("renders navigation links for authenticated admin user", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /genesis/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /master plan/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /execution engine/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /agent console/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /approval inbox/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /freelance hub/i })).toBeInTheDocument();
  });
});
