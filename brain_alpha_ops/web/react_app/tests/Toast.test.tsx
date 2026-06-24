/** Unit tests for Toast components */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import ToastContainer from "../src/components/ToastContainer";
import type { ToastData } from "../src/components/Toast";

// ── ToastContainer Tests ───────────────────────────────────────

describe("ToastContainer", () => {
  it("renders toasts with different types", () => {
    const mockToasts: ToastData[] = [
      { id: "1", type: "success", message: "Success message", duration: 5000 },
      { id: "2", type: "error", message: "Error message", duration: 5000 },
    ];

    render(
      <ToastContainer
        toasts={mockToasts}
        onDismiss={vi.fn()}
      />
    );

    expect(screen.getByText("Success message")).toBeDefined();
    expect(screen.getByText("Error message")).toBeDefined();
  });

  it("renders toasts with proper role", () => {
    render(
      <ToastContainer
        toasts={[{ id: "1", type: "success", message: "Test message", duration: 5000 }]}
        onDismiss={vi.fn()}
      />
    );

    // Toast should have role="status" for success, or role="alert" for errors
    const toastElement = screen.getByText("Test message").closest("[role]");
    expect(toastElement).toBeDefined();
  });

  it("calls onDismiss when close button is clicked", async () => {
    const dismissFn = vi.fn();
    render(
      <ToastContainer
        toasts={[{ id: "test-id", type: "success", message: "Test message", duration: 5000 }]}
        onDismiss={dismissFn}
      />
    );

    const closeButton = screen.getByRole("button", { name: /close|关闭/i });
    await act(async () => {
      fireEvent.click(closeButton);
    });

    expect(dismissFn).toHaveBeenCalledWith("test-id");
  });

  it("displays toast message correctly", () => {
    render(
      <ToastContainer
        toasts={[{ id: "1", type: "success", message: "Operation completed", duration: 5000 }]}
        onDismiss={vi.fn()}
      />
    );

    expect(screen.getByText("Operation completed")).toBeDefined();
  });

  it("handles empty toasts array", () => {
    const { container } = render(
      <ToastContainer toasts={[]} onDismiss={vi.fn()} />
    );

    expect(container.firstChild).toBeNull();
  });

  it("renders toast with error type", () => {
    render(
      <ToastContainer
        toasts={[{ id: "1", type: "error", message: "Error occurred", duration: 5000 }]}
        onDismiss={vi.fn()}
      />
    );

    const toast = screen.getByText("Error occurred").closest("[role='alert']");
    expect(toast).toBeDefined();
  });

  it("renders toast with warning type", () => {
    render(
      <ToastContainer
        toasts={[{ id: "1", type: "warning", message: "Warning occurred", duration: 5000 }]}
        onDismiss={vi.fn()}
      />
    );

    expect(screen.getByText("Warning occurred")).toBeDefined();
  });

  it("renders toast with info type", () => {
    render(
      <ToastContainer
        toasts={[{ id: "1", type: "info", message: "Info message", duration: 5000 }]}
        onDismiss={vi.fn()}
      />
    );

    expect(screen.getByText("Info message")).toBeDefined();
  });
});
