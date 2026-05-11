import { render, screen } from "@testing-library/react";

import { AppProviders } from "./utils";

const {
  mockStartGenesisSession,
  mockSendGenesisMessage,
  mockSynthesizeGenesisDraft,
  mockLockMasterPlan,
  mockListMasterPlans,
  mockActivateMasterPlan,
  mockSetMasterplanAnchor,
  mockGetMasterplanProjection,
} = vi.hoisted(() => ({
  mockStartGenesisSession: vi.fn(),
  mockSendGenesisMessage: vi.fn(),
  mockSynthesizeGenesisDraft: vi.fn(),
  mockLockMasterPlan: vi.fn(),
  mockListMasterPlans: vi.fn(),
  mockActivateMasterPlan: vi.fn(),
  mockSetMasterplanAnchor: vi.fn(),
  mockGetMasterplanProjection: vi.fn(),
}));

vi.mock("../api/masterplan.js", () => ({
  startGenesisSession: mockStartGenesisSession,
  sendGenesisMessage: mockSendGenesisMessage,
  synthesizeGenesisDraft: mockSynthesizeGenesisDraft,
  lockMasterPlan: mockLockMasterPlan,
  listMasterPlans: mockListMasterPlans,
  activateMasterPlan: mockActivateMasterPlan,
  setMasterplanAnchor: mockSetMasterplanAnchor,
  getMasterplanProjection: mockGetMasterplanProjection,
}));

import MasterPlanDashboard from "../components/app/MasterPlanDashboard";

describe("MasterPlanDashboard", () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockStartGenesisSession.mockReset();
    mockSendGenesisMessage.mockReset();
    mockSynthesizeGenesisDraft.mockReset();
    mockLockMasterPlan.mockReset();
    mockListMasterPlans.mockReset();
    mockActivateMasterPlan.mockReset();
    mockSetMasterplanAnchor.mockReset();
    mockGetMasterplanProjection.mockReset();

    mockListMasterPlans.mockResolvedValue({ plans: [] });
    mockActivateMasterPlan.mockResolvedValue({});
    mockSetMasterplanAnchor.mockResolvedValue({});
    mockGetMasterplanProjection.mockResolvedValue(null);
  });

  it("renders without crashing on mount", async () => {
    render(
      <AppProviders>
        <MasterPlanDashboard />
      </AppProviders>,
    );

    expect(screen.getByRole("heading", { name: /master plans/i })).toBeInTheDocument();
    expect(await screen.findByText(/no master plans yet\./i)).toBeInTheDocument();
  });

  it("shows loading state while plans are fetching", () => {
    mockListMasterPlans.mockReturnValue(new Promise(() => {}));

    render(
      <AppProviders>
        <MasterPlanDashboard />
      </AppProviders>,
    );

    expect(screen.getByText(/loading master plans/i)).toBeInTheDocument();
  });

  it("shows plans when they are returned", async () => {
    mockListMasterPlans.mockResolvedValue({
      plans: [
        {
          id: 7,
          version_label: "Plan Alpha",
          status: "locked",
          is_active: false,
        },
      ],
    });

    render(
      <AppProviders>
        <MasterPlanDashboard />
      </AppProviders>,
    );

    expect(await screen.findByText("Plan Alpha")).toBeInTheDocument();
  });

  it("shows empty state when no plans exist", async () => {
    render(
      <AppProviders>
        <MasterPlanDashboard />
      </AppProviders>,
    );

    expect(await screen.findByText(/no master plans yet\./i)).toBeInTheDocument();
    expect(screen.getByText(/create your first plan to begin tracking objectives/i)).toBeInTheDocument();
  });
});
