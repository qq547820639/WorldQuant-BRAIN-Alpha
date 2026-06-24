import { describe, it, expect } from "vitest";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { useConfirm } from "@/hooks/useConfirm";
import React, { useEffect } from "react";

interface TestWrapperProps {
  onReady?: (api: ReturnType<typeof useConfirm>) => void;
}

function TestWrapper({ onReady }: TestWrapperProps) {
  const confirmApi = useConfirm();

  useEffect(() => {
    if (onReady) {
      onReady(confirmApi);
    }
  }, [confirmApi, onReady]);

  return <confirmApi.ConfirmDialogComponent />;
}

describe("useConfirm", () => {
  it("initializes with dialog closed", () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    expect(confirmApi).toBeDefined();
    expect(typeof confirmApi!.confirm).toBe("function");
    expect(typeof confirmApi!.ConfirmDialogComponent).toBe("function");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("confirm function opens the dialog", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await act(async () => {
      confirmApi!.confirm({
        title: "Confirm Action",
        description: "Are you sure?",
      });
    });

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Confirm Action")).toBeInTheDocument();
    expect(screen.getByText("Are you sure?")).toBeInTheDocument();
  });

  it("passes dialog properties correctly", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({
        title: "Delete Item",
        description: "This action cannot be undone.",
        confirmText: "Delete",
        cancelText: "Cancel",
        variant: "danger",
      });
    });

    expect(screen.getByText("Delete Item")).toBeInTheDocument();
    expect(screen.getByText("This action cannot be undone.")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
    expect(screen.getByText("Cancel")).toBeInTheDocument();

    const confirmButton = screen.getByText("Delete");
    expect(confirmButton.className).toContain("btn-danger");
  });

  it("resolves with true when confirm button is clicked", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;
    let result: boolean | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({ title: "Confirm", description: "Test" }).then((value) => {
        result = value;
      });
    });

    await act(async () => {
      fireEvent.click(screen.getByText("确认"));
    });

    expect(result).toBe(true);
  });

  it("resolves with false when cancel button is clicked", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;
    let result: boolean | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({ title: "Confirm", description: "Test" }).then((value) => {
        result = value;
      });
    });

    await act(async () => {
      fireEvent.click(screen.getByText("取消"));
    });

    expect(result).toBe(false);
  });

  it("uses default button text when not provided", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({
        title: "Test",
      });
    });

    expect(screen.getByText("确认")).toBeInTheDocument();
    expect(screen.getByText("取消")).toBeInTheDocument();
  });

  it("closes dialog after confirm", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({ title: "Test" });
    });

    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByText("确认"));
    });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes dialog when pressing Escape key", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;
    let result: boolean | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({ title: "Test" }).then((value) => {
        result = value;
      });
    });

    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await act(async () => {
      fireEvent.keyDown(document, { key: "Escape" });
    });

    expect(result).toBe(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("supports danger variant styling", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({
        title: "Dangerous Action",
        variant: "danger",
      });
    });

    const confirmButton = screen.getByText("确认");
    expect(confirmButton.className).toContain("btn-danger");
  });

  it("supports default variant styling", async () => {
    let confirmApi: ReturnType<typeof useConfirm> | undefined;

    render(
      <TestWrapper
        onReady={(api) => {
          confirmApi = api;
        }}
      />
    );

    await act(async () => {
      confirmApi!.confirm({
        title: "Normal Action",
        variant: "default",
      });
    });

    const confirmButton = screen.getByText("确认");
    expect(confirmButton.className).toContain("btn-primary");
  });
});
