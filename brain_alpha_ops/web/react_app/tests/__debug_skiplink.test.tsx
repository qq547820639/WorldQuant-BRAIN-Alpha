import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import SkipLink from "@/components/A11y/SkipLink";

describe("debug", () => {
  it("smooth=false focus", () => {
    const target = document.createElement("div");
    target.id = "main-content";
    document.body.appendChild(target);
    render(<SkipLink targetId="main-content" smooth={false} />);
    const link = screen.getByRole("link", { name: "跳转到主要内容" });
    const focusSpy = vi.spyOn(target, "focus");
    fireEvent.click(link);
    console.log("focus calls:", focusSpy.mock.calls.length);
    console.log("found:", !!document.getElementById("main-content"));
    document.body.removeChild(target);
    expect(true).toBe(true);
  });
});