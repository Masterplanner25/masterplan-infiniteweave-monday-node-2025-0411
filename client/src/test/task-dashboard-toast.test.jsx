import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const {
  mockGetTasks,
  mockCreateTask,
  mockCompleteTask,
  mockStartTask,
} = vi.hoisted(() => ({
  mockGetTasks: vi.fn(),
  mockCreateTask: vi.fn(),
  mockCompleteTask: vi.fn(),
  mockStartTask: vi.fn(),
}));

vi.mock("../api/tasks.js", () => ({
  getTasks: mockGetTasks,
  createTask: mockCreateTask,
  completeTask: mockCompleteTask,
  startTask: mockStartTask,
}));

import TaskDashboard from "../components/app/TaskDashboard";

describe("TaskDashboard error feedback", () => {
  beforeEach(() => {
    mockGetTasks.mockReset();
    mockCreateTask.mockReset();
    mockCompleteTask.mockReset();
    mockStartTask.mockReset();
    mockGetTasks.mockResolvedValue([]);
  });

  it("renders an error toast when createTask fails instead of calling window.alert", async () => {
    const alertSpy = vi.fn();
    Object.defineProperty(window, "alert", {
      configurable: true,
      writable: true,
      value: alertSpy,
    });

    mockCreateTask.mockRejectedValue(new Error("Create task failed"));

    render(<TaskDashboard />);

    await waitFor(() => {
      expect(mockGetTasks).toHaveBeenCalled();
    });

    fireEvent.change(screen.getByPlaceholderText(/initialize new directive/i), {
      target: { value: "Write integration test" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add/i }));

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Create task failed");
    expect(alertSpy).not.toHaveBeenCalled();
  });
});
