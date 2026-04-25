import { render, screen, waitFor } from "@testing-library/react";

import { AppProviders } from "./utils";

const {
  mockRecallMemory,
  mockGetMemorySuggestions,
  mockRecordMemoryFeedback,
  mockGetNodePerformance,
  mockGetNodeHistory,
  mockTraverseMemory,
  mockGetFederatedRecall,
  mockShareMemoryNode,
  mockGetMemoryNodes,
} = vi.hoisted(() => ({
  mockRecallMemory: vi.fn(),
  mockGetMemorySuggestions: vi.fn(),
  mockRecordMemoryFeedback: vi.fn(),
  mockGetNodePerformance: vi.fn(),
  mockGetNodeHistory: vi.fn(),
  mockTraverseMemory: vi.fn(),
  mockGetFederatedRecall: vi.fn(),
  mockShareMemoryNode: vi.fn(),
  mockGetMemoryNodes: vi.fn(),
}));

vi.mock("../api/memory.js", () => ({
  recallMemory: mockRecallMemory,
  getMemorySuggestions: mockGetMemorySuggestions,
  recordMemoryFeedback: mockRecordMemoryFeedback,
  getNodePerformance: mockGetNodePerformance,
  getNodeHistory: mockGetNodeHistory,
  traverseMemory: mockTraverseMemory,
  getFederatedRecall: mockGetFederatedRecall,
  shareMemoryNode: mockShareMemoryNode,
  getMemoryNodes: mockGetMemoryNodes,
}));

import MemoryBrowser from "../components/app/MemoryBrowser";

describe("MemoryBrowser", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockRecallMemory.mockReset();
    mockGetMemorySuggestions.mockReset();
    mockRecordMemoryFeedback.mockReset();
    mockGetNodePerformance.mockReset();
    mockGetNodeHistory.mockReset();
    mockTraverseMemory.mockReset();
    mockGetFederatedRecall.mockReset();
    mockShareMemoryNode.mockReset();
    mockGetMemoryNodes.mockReset();

    mockRecallMemory.mockResolvedValue({ results: [], count: 0 });
    mockGetMemorySuggestions.mockResolvedValue({ suggestions: [] });
    mockRecordMemoryFeedback.mockResolvedValue({});
    mockGetNodePerformance.mockResolvedValue({});
    mockGetNodeHistory.mockResolvedValue({ history: [] });
    mockTraverseMemory.mockResolvedValue({ nodes: [] });
    mockGetFederatedRecall.mockResolvedValue({});
    mockShareMemoryNode.mockResolvedValue({});
    mockGetMemoryNodes.mockResolvedValue([]);
  });

  it("renders search input and button", async () => {
    render(
      <AppProviders>
        <MemoryBrowser />
      </AppProviders>,
    );

    expect(
      screen.getByPlaceholderText(/search your memory/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /search/i })).toBeInTheDocument();

    await waitFor(() => {
      expect(mockGetMemoryNodes).toHaveBeenCalled();
    });
  });

  it("displays memory nodes when results are returned", async () => {
    mockGetMemoryNodes.mockResolvedValue([
      {
        id: 1,
        content: "Architecture decision record",
        node_type: "decision",
        source_agent: "arm",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    render(
      <AppProviders>
        <MemoryBrowser />
      </AppProviders>,
    );

    expect(await screen.findByText(/architecture decision record/i)).toBeInTheDocument();
  });

  it("shows empty state when no nodes match", async () => {
    render(
      <AppProviders>
        <MemoryBrowser />
      </AppProviders>,
    );

    expect(await screen.findByText(/no memory nodes found\./i)).toBeInTheDocument();
    expect(
      screen.getByText(/memory nodes are written automatically as the system runs/i),
    ).toBeInTheDocument();
  });

  it("shows error toast when memory fetch fails", async () => {
    mockGetMemoryNodes.mockRejectedValue(new Error("Memory unavailable"));

    render(
      <AppProviders>
        <MemoryBrowser />
      </AppProviders>,
    );

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Memory unavailable");
  });
});
