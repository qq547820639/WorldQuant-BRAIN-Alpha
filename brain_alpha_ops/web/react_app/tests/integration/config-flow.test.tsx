import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import React, { useState } from "react";
import ConfigPanel from "@/components/ConfigPanel";
import { ThemeProvider } from "@/components/ThemeProvider";
import { GlobalDataProvider } from "@/hooks/useGlobalData";
import type { BrainCredentials } from "@/types";

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
}

function baseConfig(dataset: string, managedCredentialsAvailable = false) {
  return {
    environment: "production",
    auto_submit: false,
    credentials: {
      username: "",
      password: "",
      token: "",
      username_env: "BRAIN_USERNAME",
      password_env: "BRAIN_PASSWORD",
      token_env: "BRAIN_TOKEN",
      managed_credentials_available: managedCredentialsAvailable,
    },
    ops: {
      settings: {
        instrumentType: "EQUITY",
        region: "USA",
        universe: "TOP3000",
        delay: 1,
        decay: 10,
        neutralization: "SUBINDUSTRY",
        dataset,
        pasteurization: "ON",
        unitHandling: "VERIFY",
        nanHandling: "ON",
        language: "FASTEXPR",
        type: "REGULAR",
      },
      budget: {
        max_candidates_per_cycle: 20,
        max_cycles: 10,
        retained_alpha_pool_size: 30,
        official_backtest_batch_size: 3,
        require_cloud_sync: false,
      },
      thresholds: {
        min_sharpe: 1.25,
        min_fitness: 1,
        min_turnover: 0.01,
        platform_max_turnover: 0.7,
        max_self_correlation: 0.7,
        max_weight_concentration: 0.5,
      },
      scoring: {
        prior_layer_weight: 0.3,
        empirical_layer_weight: 0.4,
        checklist_layer_weight: 0.3,
        market_regime: "normal",
      },
    },
  };
}

function baseConfigSchema() {
  return {
    ok: true,
    schema: {
      settings_options: {
        instrumentType: ["EQUITY", "FUTURES"],
        region: ["USA", "CHN"],
        universe: ["TOP3000", "TOP500"],
        delay: [0, 1],
        decay: [5, 10, 20],
        neutralization: ["SUBINDUSTRY", "INDUSTRY", "SECTOR"],
        dataset: ["pv1", "fundamental6", "analyst4"],
        pasteurization: ["ON", "OFF"],
        unitHandling: ["VERIFY", "RAW", "NONE"],
        nanHandling: ["ON", "OFF"],
        language: ["FASTEXPR"],
        type: ["REGULAR", "POWER_POOL"],
      },
      dataset_options: [
        { id: "pv1", name: "Price Volume Data for Equity", field_count: 24 },
        { id: "fundamental6", name: "Company Fundamental Data for Equity", field_count: 886 },
        { id: "analyst4", name: "Analyst Estimate Data for Equity", field_count: 1324 },
      ],
    },
  };
}

function ConfigPanelHarness({
  notify,
  connected = false,
  contextFresh = false,
  managedCredentialsAvailable = false,
  onLoggedOut,
}: {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
  connected?: boolean;
  contextFresh?: boolean;
  managedCredentialsAvailable?: boolean;
  onLoggedOut?: () => void;
}) {
  const [credentials, setCredentials] = useState<BrainCredentials>({ username: "", password: "", token: "" });
  return (
    <ThemeProvider>
      <GlobalDataProvider>
        <ConfigPanel
          notify={notify}
          credentials={credentials}
          onCredentialsChange={setCredentials}
          connected={connected}
          contextFresh={contextFresh}
          managedCredentialsAvailable={managedCredentialsAvailable}
          onLoggedOut={onLoggedOut}
        />
      </GlobalDataProvider>
    </ThemeProvider>
  );
}

describe("配置流程集成测试", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it("测试配置表单渲染 - 显示配置面板标题", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    expect(await screen.findByRole("heading", { name: "连接与生产参数" })).toBeInTheDocument();
  });

  it("测试配置表单渲染 - 显示数据集下拉框", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const datasetSelect = await screen.findByRole("combobox", { name: "数据集" });
    expect(datasetSelect).toBeInTheDocument();
  });

  it("测试配置表单渲染 - 显示账户邮箱输入框", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const usernameInput = await screen.findByLabelText("账户邮箱");
    expect(usernameInput).toBeInTheDocument();
  });

  it("测试配置表单渲染 - 显示保存按钮", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const saveButton = await screen.findByRole("button", { name: "保存" });
    expect(saveButton).toBeInTheDocument();
  });

  it("测试输入修改 - 修改账户邮箱", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const usernameInput = await screen.findByLabelText("账户邮箱");
    await user.type(usernameInput, "test@example.com");

    expect(usernameInput).toHaveValue("test@example.com");
  });

  it("测试输入修改 - 修改密码", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const passwordInput = await screen.findByLabelText("密码");
    await user.type(passwordInput, "password123");

    expect(passwordInput).toHaveValue("password123");
  });

  it("测试输入修改 - 修改数据集", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const datasetSelect = await screen.findByRole("combobox", { name: "数据集" });
    await user.selectOptions(datasetSelect, "fundamental6");

    expect(datasetSelect).toHaveValue("fundamental6");
  });

  it("测试保存配置 - 点击保存按钮", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      const method = options?.method || "GET";
      if (path === "/api/config" && method === "POST") {
        return jsonResponse({ ok: true, config: baseConfig("fundamental6") });
      }
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const datasetSelect = await screen.findByRole("combobox", { name: "数据集" });
    await user.selectOptions(datasetSelect, "fundamental6");

    const saveButton = screen.getByRole("button", { name: "保存" });
    await waitFor(() => expect(saveButton).toBeEnabled());
    await user.click(saveButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/config",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });

  it("测试保存配置 - 显示保存成功提示", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      const method = options?.method || "GET";
      if (path === "/api/config" && method === "POST") {
        return jsonResponse({ ok: true, config: baseConfig("analyst4") });
      }
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const datasetSelect = await screen.findByRole("combobox", { name: "数据集" });
    await user.selectOptions(datasetSelect, "analyst4");

    const saveButton = screen.getByRole("button", { name: "保存" });
    await waitFor(() => expect(saveButton).toBeEnabled());
    await user.click(saveButton);

    await waitFor(() => {
      expect(notify).toHaveBeenCalledWith("success", "配置已保存");
    });
  });

  it("测试导入导出配置 - 导出按钮存在", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const exportButton = await screen.findByRole("button", { name: "导出" });
    expect(exportButton).toBeInTheDocument();
  });

  it("测试导入导出配置 - 导入按钮存在", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const importButton = await screen.findByRole("button", { name: "导入" });
    expect(importButton).toBeInTheDocument();
  });

  it("测试导入导出配置 - 点击导出按钮触发下载", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const createObjectURLSpy = vi.fn().mockReturnValue("blob:test");
    const revokeObjectURLSpy = vi.fn();
    // @ts-expect-error - jsdom doesn't have URL.createObjectURL
    global.URL.createObjectURL = createObjectURLSpy;
    // @ts-expect-error - jsdom doesn't have URL.revokeObjectURL
    global.URL.revokeObjectURL = revokeObjectURLSpy;

    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      const el = originalCreateElement(tagName);
      if (tagName === "a") {
        Object.defineProperty(el, "click", { value: clickSpy });
      }
      return el as HTMLElement;
    });

    render(<ConfigPanelHarness notify={notify} />);

    const exportButton = await screen.findByRole("button", { name: "导出" });
    await user.click(exportButton);

    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    vi.restoreAllMocks();
  });

  it("测试连接测试 - 测试连接按钮存在", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const testButton = await screen.findByRole("button", { name: "测试 BRAIN 连接" });
    expect(testButton).toBeInTheDocument();
  });

  it("测试连接测试 - 连接成功", async () => {
    const user = userEvent.setup();
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
      const path = String(url);
      const method = options?.method || "GET";
      if (path === "/api/test_connection" && method === "POST") {
        return jsonResponse({ ok: true, environment: "production", auth: "basic" });
      }
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} />);

    const usernameInput = await screen.findByLabelText("账户邮箱");
    const passwordInput = screen.getByLabelText("密码");
    await user.type(usernameInput, "user@example.com");
    await user.type(passwordInput, "pass123");

    const testButton = screen.getByRole("button", { name: "测试 BRAIN 连接" });
    await user.click(testButton);

    await waitFor(() => {
      expect(screen.getByText(/连接正常: production/)).toBeInTheDocument();
    });
  });

  it("测试缓存模式 - 缓存模式下凭证折叠", async () => {
    const notify = vi.fn();
    const fetchMock = vi.fn(async (url: RequestInfo | URL) => {
      const path = String(url);
      if (path === "/api/config") return jsonResponse({ ok: true, config: baseConfig("pv1") });
      if (path === "/api/config_schema") return jsonResponse(baseConfigSchema());
      throw new Error(`Unexpected: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ConfigPanelHarness notify={notify} connected={false} contextFresh />);

    expect(await screen.findByText(/当前使用本地缓存运行/)).toBeInTheDocument();
  });
});
