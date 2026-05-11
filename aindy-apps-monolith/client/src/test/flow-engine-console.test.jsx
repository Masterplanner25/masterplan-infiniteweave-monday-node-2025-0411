import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const {
  mockGetFlowRuns,
  mockGetFlowRunHistory,
  mockResumeFlowRun,
  mockGetFlowRegistry,
  mockGetAutomationLogs,
  mockReplayAutomationLog,
  mockGetSchedulerStatus,
  mockGetFlowStrategies,
  mockReportClientError,
} = vi.hoisted(() => ({
  mockGetFlowRuns: vi.fn(),
  mockGetFlowRunHistory: vi.fn(),
  mockResumeFlowRun: vi.fn(),
  mockGetFlowRegistry: vi.fn(),
  mockGetAutomationLogs: vi.fn(),
  mockReplayAutomationLog: vi.fn(),
  mockGetSchedulerStatus: vi.fn(),
  mockGetFlowStrategies: vi.fn(),
  mockReportClientError: vi.fn(),
}));

vi.mock("../api/operator.js", () => ({
  getFlowRuns: mockGetFlowRuns,
  getFlowRunHistory: mockGetFlowRunHistory,
  resumeFlowRun: mockResumeFlowRun,
  getFlowRegistry: mockGetFlowRegistry,
  getAutomationLogs: mockGetAutomationLogs,
  replayAutomationLog: mockReplayAutomationLog,
  getSchedulerStatus: mockGetSchedulerStatus,
  getFlowStrategies: mockGetFlowStrategies,
  reportClientError: mockReportClientError,
}));

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

import FlowEngineConsole from "../components/platform/FlowEngineConsole";
import { RouteErrorBoundary } from "../components/shared/ErrorBoundary";

describe("FlowEngineConsole", () => {
  beforeEach(() => {
    mockGetFlowRuns.mockReset();
    mockGetFlowRunHistory.mockReset();
    mockResumeFlowRun.mockReset();
    mockGetFlowRegistry.mockReset();
    mockGetAutomationLogs.mockReset();
    mockReplayAutomationLog.mockReset();
    mockGetSchedulerStatus.mockReset();
    mockGetFlowStrategies.mockReset();
    mockReportClientError.mockReset();

    mockGetFlowRuns.mockResolvedValue({ runs: [] });
    mockGetFlowRunHistory.mockResolvedValue({ history: [] });
    mockResumeFlowRun.mockResolvedValue({});
    mockGetFlowRegistry.mockResolvedValue({ flow_count: 0, node_count: 0, nodes: [], flows: {} });
    mockGetAutomationLogs.mockResolvedValue({ logs: [] });
    mockReplayAutomationLog.mockResolvedValue({});
    mockGetSchedulerStatus.mockResolvedValue({ running: true, jobs: [] });
    mockGetFlowStrategies.mockResolvedValue({ strategies: [] });
    mockReportClientError.mockResolvedValue(undefined);
  });

  it("renders the console panel heading", async () => {
    render(<FlowEngineConsole />);

    expect(screen.getByRole("heading", { name: /execution console/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetFlowRuns).toHaveBeenCalled();
    });
  });

  it("shows flow list when flows are returned", async () => {
    mockGetFlowRegistry.mockResolvedValue({
      flow_count: 1,
      node_count: 2,
      nodes: ["task.start", "task.end"],
      flows: {
        "task.pipeline": {
          start: "task.start",
          end: ["task.end"],
          node_count: 2,
        },
      },
    });

    render(<FlowEngineConsole />);

    fireEvent.click(screen.getByRole("button", { name: /registry/i }));

    expect(await screen.findByText("task.pipeline")).toBeInTheDocument();
  });

  it("shows empty state when no flows are registered", async () => {
    render(<FlowEngineConsole />);

    fireEvent.click(screen.getByRole("button", { name: /registry/i }));

    expect(await screen.findByText(/no flows registered\./i)).toBeInTheDocument();
    expect(screen.getByText(/flows are registered at server startup/i)).toBeInTheDocument();
  });

  it("shows an error boundary fallback when the component throws", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    function Bomb() {
      throw new Error("boom");
    }

    render(
      <RouteErrorBoundary name="Registry">
        <Bomb />
      </RouteErrorBoundary>,
    );

    expect(screen.getByText(/registry encountered an error\./i)).toBeInTheDocument();

    consoleSpy.mockRestore();
  });
});
