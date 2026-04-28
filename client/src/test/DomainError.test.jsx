import { fireEvent, render, screen } from "@testing-library/react";
import { ApiError } from "../api/_core.js";
import DomainError from "../components/shared/DomainError.jsx";

describe("DomainError", () => {
  it("renders nothing when error is null", () => {
    const { container } = render(<DomainError error={null} domain="tasks" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the 503 message with the domain name", () => {
    render(<DomainError error={new ApiError(503, "down", null)} domain="analytics" />);
    expect(screen.getByText("analytics is temporarily unavailable. Try again in a moment.")).toBeInTheDocument();
  });

  it("renders the 500 message with the domain name", () => {
    render(<DomainError error={new ApiError(500, "boom", null)} domain="ARM" />);
    expect(screen.getByText("ARM encountered an error. Our team has been notified.")).toBeInTheDocument();
  });

  it("renders a retry button when onRetry is provided", () => {
    const onRetry = vi.fn();
    render(<DomainError error={new ApiError(429, "slow down", null)} domain="tasks" onRetry={onRetry} />);

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not render a retry button when onRetry is absent", () => {
    render(<DomainError error={new ApiError(408, "timeout", null)} domain="tasks" />);
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
  });
});
