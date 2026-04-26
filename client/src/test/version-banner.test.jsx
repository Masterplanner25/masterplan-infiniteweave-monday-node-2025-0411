import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VersionMismatchBanner } from "../components/shared/VersionMismatchBanner";

describe("VersionMismatchBanner", () => {
  it("renders a red background for major_mismatch", () => {
    render(
      <VersionMismatchBanner
        status="major_mismatch"
        apiVersion="2.0.0"
        clientVersion="1.0.0"
      />,
    );

    expect(screen.getByRole("alert")).toHaveStyle({ background: "#b91c1c" });
  });

  it("renders dismiss button for patch_mismatch", () => {
    render(
      <VersionMismatchBanner
        status="patch_mismatch"
        apiVersion="1.3.1"
        clientVersion="1.3.0"
        onDismiss={() => {}}
      />,
    );

    expect(screen.getByLabelText(/dismiss version warning/i)).toBeInTheDocument();
  });

  it("does not render dismiss button for major_mismatch", () => {
    render(
      <VersionMismatchBanner
        status="major_mismatch"
        apiVersion="2.0.0"
        clientVersion="1.0.0"
        onDismiss={() => {}}
      />,
    );

    expect(screen.queryByLabelText(/dismiss version warning/i)).toBeNull();
  });

  it("calls onDismiss when dismiss is clicked", () => {
    const onDismiss = vi.fn();

    render(
      <VersionMismatchBanner
        status="client_ahead"
        apiVersion="1.9.0"
        clientVersion="2.0.0"
        onDismiss={onDismiss}
      />,
    );

    fireEvent.click(screen.getByLabelText(/dismiss version warning/i));

    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("renders null for unknown status", () => {
    const { container } = render(
      <VersionMismatchBanner
        status={"unknown"}
        apiVersion="?"
        clientVersion="1.0.0"
      />,
    );

    expect(container.firstChild).toBeNull();
  });
});
