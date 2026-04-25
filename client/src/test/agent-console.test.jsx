import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { AppProviders } from "./utils";

const {
  mockCreateAgentRun,
  mockGetAgentRuns,
  mockGetAgentRunSteps,
  mockApproveAgentRun,
  mockRejectAgentRun,
  mockGetAgentTools,
  mockGetAgentTrust,
  mockUpdateAgentTrust,
  mockGetAgentSuggestions,
  mockFetchRunEvents,
  mockPostScoreFeedback,
} = vi.hoisted(() => ({
  mockCreateAgentRun: vi.fn(),
  mockGetAgentRuns: vi.fn(),
  mockGetAgentRunSteps: vi.fn(),
  mockApproveAgentRun: vi.fn(),
  mockRejectAgentRun: vi.fn(),
  mockGetAgentTools: vi.fn(),
  mockGetAgentTrust: vi.fn(),
  mockUpdateAgentTrust: vi.fn(),
  mockGetAgentSuggestions: vi.fn(),
  mockFetchRunEvents: vi.fn(),
  mockPostScoreFeedback: vi.fn(),
}));

vi.mock("../api/agent.js", () => ({
  createAgentRun: mockCreateAgentRun,
  getAgentRuns: mockGetAgentRuns,
  getAgentRunSteps: mockGetAgentRunSteps,
  approveAgentRun: mockApproveAgentRun,
  rejectAgentRun: mockRejectAgentRun,
  getAgentTools: mockGetAgentTools,
  getAgentTrust: mockGetAgentTrust,
  updateAgentTrust: mockUpdateAgentTrust,
  getAgentSuggestions: mockGetAgentSuggestions,
  fetchRunEvents: mockFetchRunEvents,
}));

vi.mock("../api/analytics.js", () => ({
  postScoreFeedback: mockPostScoreFeedback,
}));

import AgentConsole from "../components/platform/AgentConsole";

describe("AgentConsole", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockCreateAgentRun.mockReset();
    mockGetAgentRuns.mockReset();
    mockGetAgentRunSteps.mockReset();
    mockApproveAgentRun.mockReset();
    mockRejectAgentRun.mockReset();
    mockGetAgentTools.mockReset();
    mockGetAgentTrust.mockReset();
    mockUpdateAgentTrust.mockReset();
    mockGetAgentSuggestions.mockReset();
    mockFetchRunEvents.mockReset();
    mockPostScoreFeedback.mockReset();

    mockGetAgentRuns.mockResolvedValue([]);
    mockGetAgentRunSteps.mockResolvedValue([]);
    mockApproveAgentRun.mockResolvedValue({});
    mockRejectAgentRun.mockResolvedValue({});
    mockGetAgentTools.mockResolvedValue([]);
    mockGetAgentTrust.mockResolvedValue({});
    mockUpdateAgentTrust.mockResolvedValue({});
    mockGetAgentSuggestions.mockResolvedValue([]);
    mockFetchRunEvents.mockResolvedValue({ events: [] });
    mockPostScoreFeedback.mockResolvedValue({});
  });

  it("renders the heading and submit form on initial load", async () => {
    render(
      <AppProviders>
        <AgentConsole />
      </AppProviders>,
    );

    expect(screen.getByRole("heading", { name: /agent console/i })).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/find leads in the ai consulting space and create a follow-up task/i),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetAgentRuns).toHaveBeenCalled();
      expect(mockGetAgentTools).toHaveBeenCalled();
      expect(mockGetAgentTrust).toHaveBeenCalled();
    });
  });

  it("shows agent run list when runs are returned", async () => {
    mockGetAgentRuns.mockResolvedValue([
      {
        run_id: "run-1",
        goal: "Investigate enterprise leads",
        status: "pending_approval",
        overall_risk: "medium",
        plan: { steps: [] },
      },
    ]);

    render(
      <AppProviders>
        <AgentConsole />
      </AppProviders>,
    );

    expect(await screen.findByText(/investigate enterprise leads/i)).toBeInTheDocument();
  });

  it("shows empty state when run list is empty", async () => {
    render(
      <AppProviders>
        <AgentConsole />
      </AppProviders>,
    );

    expect(await screen.findByText(/no agent runs yet\./i)).toBeInTheDocument();
    expect(screen.getByText(/submit an objective above to start an agent run/i)).toBeInTheDocument();
  });

  it("shows error toast when run fetch fails", async () => {
    mockGetAgentRuns.mockRejectedValue(new Error("Agent service unavailable"));

    render(
      <AppProviders>
        <AgentConsole />
      </AppProviders>,
    );

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Agent service unavailable");
  });

  it("calls createAgentRun when form is submitted", async () => {
    mockCreateAgentRun.mockResolvedValue({
      run_id: "run-2",
      goal: "Plan launch sequence",
      status: "pending_approval",
      overall_risk: "low",
      plan: { steps: [] },
    });

    render(
      <AppProviders>
        <AgentConsole />
      </AppProviders>,
    );

    await waitFor(() => {
      expect(mockGetAgentRuns).toHaveBeenCalled();
    });

    fireEvent.change(
      screen.getByPlaceholderText(/find leads in the ai consulting space and create a follow-up task/i),
      { target: { value: "Plan launch sequence" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /run agent/i }));

    await waitFor(() => {
      expect(mockCreateAgentRun).toHaveBeenCalledWith({ goal: "Plan launch sequence" });
    });
  });
});
