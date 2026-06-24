/** Unit tests for ConfirmDialog component */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ConfirmDialog from "../src/components/ConfirmDialog";

// ── ConfirmDialog Tests ────────────────────────────────────────

describe("ConfirmDialog", () => {
  const mockOnConfirm = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    mockOnConfirm.mockClear();
    mockOnCancel.mockClear();
  });

  it("does not render when open is false", () => {
    render(
      <ConfirmDialog
        open={false}
        title="Confirm Action"
        description="Are you sure?"
        onConfirm={mockOnConfirm}
        onCancel={mockOnCancel}
      />
    );

    expect(screen.queryByText("Confirm Action")).toBeNull();
  });

  it("renders when open is true", () => {
    render(
      <ConfirmDialog
        open={true}
        title="Confirm Action"
        description="Are you sure?"
        onConfirm={mockOnConfirm}
        onCancel={mockOnCancel}
      />
    );

    expect(screen.getByText("Confirm Action")).toBeDefined();
    expect(screen.getByText("Are you sure?")).toBeDefined();
  });

  it("calls onConfirm when confirm button is clicked", async () => {
    render(
      <ConfirmDialog
        open={true}
        title="Delete Item"
        description="Are you sure you want to delete this item?"
        onConfirm={mockOnConfirm}
        onCancel={mockOnCancel}
      />
    );

    await fireEvent.click(screen.getByText("确认"));
    expect(mockOnConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when cancel button is clicked", async () => {
    render(
      <ConfirmDialog
        open={true}
        title="Delete Item"
        description="Are you sure you want to delete this item?"
        onConfirm={mockOnConfirm}
        onCancel={mockOnCancel}
      />
    );

    await fireEvent.click(screen.getByText("取消"));
    expect(mockOnCancel).toHaveBeenCalledTimes(1);
  });

  it("has proper dialog role when open", () => {
    render(
      <ConfirmDialog
        open={true}
        title="Confirm Action"
        description="Are you sure?"
        onConfirm={mockOnConfirm}
        onCancel={mockOnCancel}
      />
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeDefined();
  });

  it("renders title and description", () => {
    render(
      <ConfirmDialog
        open={true}
        title="Test Title"
        description="Test Description"
        onConfirm={mockOnConfirm}
        onCancel={mockOnCancel}
      />
    );

    expect(screen.getByText("Test Title")).toBeDefined();
    expect(screen.getByText("Test Description")).toBeDefined();
  });

  it("renders with default confirm button", () => {
    render(
      <ConfirmDialog
        open={true}
        title="Test"
        onConfirm={mockOnConfirm}
        onCancel={mockOnCancel}
      />
    );

    expect(screen.getByText("确认")).toBeDefined();
    expect(screen.getByText("取消")).toBeDefined();
  });
});
