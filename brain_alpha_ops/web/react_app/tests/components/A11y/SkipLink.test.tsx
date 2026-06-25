import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SkipLink from "@/components/A11y/SkipLink";

describe("SkipLink", () => {
  it("renders with default sr-only state", () => {
    render(<SkipLink targetId="main-content" />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "#main-content");
    expect(link.style.position).toBe("absolute");
    expect(link.style.left).toBe("-9999px");
  });

  it("becomes visible on focus", () => {
    render(<SkipLink targetId="main-content" />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });

    fireEvent.focus(link);

    expect(link.style.left).toBe("16px");
    expect(link.style.top).toBe("16px");
    expect(link.style.width).toBe("auto");
    expect(link.style.height).toBe("auto");
  });

  it("hides again on blur", () => {
    render(<SkipLink targetId="main-content" />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });

    fireEvent.focus(link);
    expect(link.style.left).toBe("16px");

    fireEvent.blur(link);
    expect(link.style.left).toBe("-9999px");
  });

  it("jumps to target element on click", () => {
    const target = document.createElement("div");
    target.id = "main-content";
    document.body.appendChild(target);

    render(<SkipLink targetId="main-content" />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });

    const focusSpy = vi.spyOn(target, "focus");
    const scrollIntoViewSpy = vi.spyOn(target, "scrollIntoView");

    fireEvent.click(link);

    expect(focusSpy).toHaveBeenCalled();
    expect(scrollIntoViewSpy).toHaveBeenCalledWith({
      behavior: "smooth",
      block: "start",
    });

    document.body.removeChild(target);
  });

  it("supports custom label", () => {
    render(<SkipLink targetId="main" label="跳到内容" />);
    expect(screen.getByRole("link", { name: "跳到内容" })).toBeInTheDocument();
  });

  it("applies custom className", () => {
    render(<SkipLink targetId="main" className="custom-skip" />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });
    expect(link.className).toContain("custom-skip");
  });

  it("supports smooth=false option", () => {
    const target = document.createElement("div");
    target.id = "main-content";
    document.body.appendChild(target);

    render(<SkipLink targetId="main-content" smooth={false} />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });

    const focusSpy = vi.spyOn(target, "focus");

    fireEvent.click(link);

    expect(focusSpy).toHaveBeenCalledWith({ preventScroll: true });

    document.body.removeChild(target);
  });

  it("does nothing when target element does not exist", () => {
    render(<SkipLink targetId="nonexistent" />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });

    expect(() => fireEvent.click(link)).not.toThrow();
  });
});
