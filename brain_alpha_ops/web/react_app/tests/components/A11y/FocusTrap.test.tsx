import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, useRef } from "vitest";
import React from "react";
import FocusTrap from "@/components/A11y/FocusTrap";

describe("FocusTrap", () => {
  it("renders children", () => {
    render(
      <FocusTrap>
        <div>
          <button>Button 1</button>
          <button>Button 2</button>
        </div>
      </FocusTrap>
    );
    expect(screen.getByRole("button", { name: "Button 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Button 2" })).toBeInTheDocument();
  });

  it("focuses first focusable element when activated", () => {
    render(
      <FocusTrap active>
        <div>
          <button>First</button>
          <button>Second</button>
          <button>Third</button>
        </div>
      </FocusTrap>
    );

    expect(screen.getByRole("button", { name: "First" })).toHaveFocus();
  });

  it("focuses initialFocusRef element when provided", () => {
    const initialRef = { current: null };
    const TestComponent = () => {
      const ref = React.useRef<HTMLButtonElement>(null);
      initialRef.current = ref;
      return (
        <FocusTrap active initialFocusRef={ref}>
          <div>
            <button>First</button>
            <button ref={ref}>Second</button>
            <button>Third</button>
          </div>
        </FocusTrap>
      );
    };

    render(<TestComponent />);
    expect(screen.getByRole("button", { name: "Second" })).toHaveFocus();
  });

  it("traps focus with Tab key", () => {
    render(
      <FocusTrap active>
        <div>
          <button>First</button>
          <button>Second</button>
          <button>Third</button>
        </div>
      </FocusTrap>
    );

    const firstButton = screen.getByRole("button", { name: "First" });
    const secondButton = screen.getByRole("button", { name: "Second" });
    const thirdButton = screen.getByRole("button", { name: "Third" });

    expect(firstButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab" });
    expect(secondButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab" });
    expect(thirdButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab" });
    expect(firstButton).toHaveFocus();
  });

  it("traps focus in reverse with Shift+Tab", () => {
    render(
      <FocusTrap active>
        <div>
          <button>First</button>
          <button>Second</button>
          <button>Third</button>
        </div>
      </FocusTrap>
    );

    const firstButton = screen.getByRole("button", { name: "First" });
    const thirdButton = screen.getByRole("button", { name: "Third" });
    const secondButton = screen.getByRole("button", { name: "Second" });

    expect(firstButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(thirdButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(secondButton).toHaveFocus();
  });

  it("does not trap focus when inactive", () => {
    const { rerender } = render(
      <FocusTrap active={false}>
        <div>
          <button>First</button>
          <button>Second</button>
        </div>
      </FocusTrap>
    );

    const firstButton = screen.getByRole("button", { name: "First" });
    const secondButton = screen.getByRole("button", { name: "Second" });

    firstButton.focus();
    expect(firstButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab" });
    expect(secondButton).not.toHaveFocus();
  });

  it("calls onEscape when Escape key is pressed", () => {
    const onEscape = vi.fn();
    render(
      <FocusTrap active onEscape={onEscape}>
        <div>
          <button>Button</button>
        </div>
      </FocusTrap>
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onEscape).toHaveBeenCalledTimes(1);
  });

  it("does not call onEscape when inactive", () => {
    const onEscape = vi.fn();
    render(
      <FocusTrap active={false} onEscape={onEscape}>
        <div>
          <button>Button</button>
        </div>
      </FocusTrap>
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onEscape).not.toHaveBeenCalled();
  });

  it("applies custom className", () => {
    const { container } = render(
      <FocusTrap active className="custom-trap">
        <div>
          <button>Button</button>
        </div>
      </FocusTrap>
    );
    expect(container.firstChild).toHaveClass("custom-trap");
  });

  it("restores focus on deactivation", () => {
    const TestComponent = ({ active }: { active: boolean }) => (
      <div>
        <button data-testid="outside">Outside</button>
        <FocusTrap active={active}>
          <div>
            <button>Inside</button>
          </div>
        </FocusTrap>
      </div>
    );

    const { rerender } = render(<TestComponent active={false} />);
    const outsideButton = screen.getByTestId("outside");
    outsideButton.focus();
    expect(outsideButton).toHaveFocus();

    rerender(<TestComponent active={true} />);
    expect(screen.getByRole("button", { name: "Inside" })).toHaveFocus();

    rerender(<TestComponent active={false} />);
    expect(outsideButton).toHaveFocus();
  });
});
