import { describe, expect, it } from "vitest";
import {
  validateForm,
  formFromConfig,
  payloadFromForm,
  credentialsPayload,
  datasetSelectOptions,
  sanitizeConfigText,
  formFromImport,
  type ConfigForm,
  type ConfigSchema,
} from "@/components/ConfigPanel/utils";

function defaultForm(overrides: Partial<ConfigForm> = {}): ConfigForm {
  return {
    environment: "production",
    autoSubmit: false,
    instrumentType: "EQUITY",
    region: "USA",
    universe: "TOP3000",
    delay: 1,
    decay: 10,
    neutralization: "SUBINDUSTRY",
    dataset: "pv1",
    pasteurization: "ON",
    unitHandling: "VERIFY",
    nanHandling: "ON",
    language: "FASTEXPR",
    alphaType: "REGULAR",
    candidates: 20,
    cycles: 10,
    poolSize: 10,
    backtestBatchSize: 3,
    requireCloudSync: false,
    minSharpe: 1.25,
    minFitness: 1.0,
    minTurnover: 0.01,
    platformMaxTurnover: 0.7,
    maxSelfCorrelation: 0.7,
    maxWeightConcentration: 0.1,
    ...overrides,
  };
}

function defaultSchema(overrides: Partial<ConfigSchema> = {}): ConfigSchema {
  return {
    settings_options: {
      instrumentType: ["EQUITY"],
      region: ["USA", "CHN", "EUR", "GLB"],
      universe: ["TOP3000", "TOP1000", "TOP500"],
      delay: [0, 1],
      neutralization: ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"],
      dataset: ["pv1", "analyst4", "fundamental6"],
      pasteurization: ["ON", "OFF"],
      unitHandling: ["VERIFY", "RAW", "NONE"],
      nanHandling: ["ON", "OFF"],
      language: ["FASTEXPR"],
      type: ["REGULAR", "POWER_POOL"],
    },
    dataset_options: [
      { id: "pv1", name: "Price Volume Data for Equity", field_count: 24 },
      { id: "analyst4", name: "Analyst Estimate Data for Equity", field_count: 1324 },
      { id: "fundamental6", name: "Company Fundamental Data for Equity", field_count: 886 },
    ],
    ...overrides,
  };
}

describe("ConfigPanel utils - validateForm", () => {
  it("returns null for a valid form", () => {
    const error = validateForm(defaultForm(), defaultSchema());
    expect(error).toBeNull();
  });

  it("rejects dataset exceeding max length", () => {
    const form = defaultForm({ dataset: "a".repeat(129) });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("数据集长度不能超过");
  });

  it("rejects dataset with invalid characters", () => {
    const form = defaultForm({ dataset: "invalid dataset!" });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("数据集只能包含");
  });

  it("rejects delay value outside 0-1 range", () => {
    const form = defaultForm({ delay: 2 });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("延迟值必须为 0 或 1");
  });

  it("rejects candidates count outside 1-1000 range", () => {
    const form = defaultForm({ candidates: 0 });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("候选数必须在 1-1000 之间");
  });

  it("rejects cycles count outside 1-1000 range", () => {
    const form = defaultForm({ cycles: 1001 });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("周期数必须在 1-1000 之间");
  });

  it("rejects pool size outside 1-1000 range", () => {
    const form = defaultForm({ poolSize: 0 });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("池大小必须在 1-1000 之间");
  });

  it("rejects backtest batch size outside 1-100 range", () => {
    const form = defaultForm({ backtestBatchSize: 101 });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("回测批次大小必须在 1-100 之间");
  });

  it("rejects unsupported region", () => {
    const form = defaultForm({ region: "INVALID" });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("不支持的区域");
  });

  it("rejects unsupported universe", () => {
    const form = defaultForm({ universe: "INVALID" });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("不支持的股票池");
  });

  it("rejects unsupported neutralization", () => {
    const form = defaultForm({ neutralization: "INVALID" });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("不支持的中性化方式");
  });

  it("rejects dataset not in schema options", () => {
    const form = defaultForm({ dataset: "unknown_dataset" });
    const error = validateForm(form, defaultSchema());
    expect(error).toContain("不支持的数据集");
  });

  it("allows valid delay value of 0", () => {
    const form = defaultForm({ delay: 0 });
    const error = validateForm(form, defaultSchema());
    expect(error).toBeNull();
  });
});

describe("ConfigPanel utils - formFromConfig", () => {
  it("parses a full config into form values", () => {
    const config = {
      environment: "production",
      auto_submit: false,
      settings: {
        instrumentType: "EQUITY",
        region: "USA",
        universe: "TOP3000",
        delay: 1,
        decay: 10,
        neutralization: "SUBINDUSTRY",
        dataset: "pv1",
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
        max_weight_concentration: 0.1,
      },
    };

    const form = formFromConfig(config as any);
    expect(form.instrumentType).toBe("EQUITY");
    expect(form.region).toBe("USA");
    expect(form.dataset).toBe("pv1");
    expect(form.candidates).toBe(20);
    expect(form.cycles).toBe(10);
    expect(form.poolSize).toBe(30);
    expect(form.backtestBatchSize).toBe(3);
    expect(form.minSharpe).toBe(1.25);
    expect(form.alphaType).toBe("REGULAR");
  });

  it("returns defaults for null config", () => {
    const form = formFromConfig(null);
    expect(form.instrumentType).toBe("EQUITY");
    expect(form.region).toBe("USA");
    expect(form.universe).toBe("TOP3000");
    expect(form.candidates).toBe(20);
  });

  it("handles missing nested objects gracefully", () => {
    const config = { environment: "production" };
    const form = formFromConfig(config as any);
    expect(form.instrumentType).toBe("EQUITY");
    expect(form.candidates).toBe(20);
  });
});

describe("ConfigPanel utils - payloadFromForm", () => {
  it("generates correct save payload from form", () => {
    const form = defaultForm({
      dataset: "analyst4",
      candidates: 30,
      cycles: 5,
      minSharpe: 1.5,
    });

    const payload = payloadFromForm(form);
    expect(payload.settings).toEqual(expect.objectContaining({
      dataset: "analyst4",
      instrumentType: "EQUITY",
      region: "USA",
    }));
    expect(payload.budget).toEqual(expect.objectContaining({
      max_candidates_per_cycle: 30,
      max_cycles: 5,
    }));
    expect(payload.thresholds).toEqual(expect.objectContaining({
      min_sharpe: 1.5,
    }));
  });

  it("does not include credentials in the payload", () => {
    const form = defaultForm();
    const payload = payloadFromForm(form);
    expect(payload).not.toHaveProperty("username");
    expect(payload).not.toHaveProperty("password");
    expect(payload).not.toHaveProperty("token");
  });
});

describe("ConfigPanel utils - credentialsPayload", () => {
  it("includes non-empty credentials", () => {
    const payload = credentialsPayload({
      username: "test@example.com",
      password: "secret",
      token: "tok123",
    });
    expect(payload).toEqual({
      username: "test@example.com",
      password: "secret",
      token: "tok123",
    });
  });

  it("omits empty credentials", () => {
    const payload = credentialsPayload({
      username: "",
      password: "",
      token: "",
    });
    expect(payload).toEqual({});
  });

  it("trims whitespace from username and token", () => {
    const payload = credentialsPayload({
      username: "  test@example.com  ",
      password: "secret",
      token: "  tok123  ",
    });
    expect(payload.username).toBe("test@example.com");
    expect(payload.token).toBe("tok123");
  });

  it("does not trim password", () => {
    const payload = credentialsPayload({
      username: "",
      password: "  secret  ",
      token: "",
    });
    expect(payload.password).toBe("  secret  ");
  });
});

describe("ConfigPanel utils - datasetSelectOptions", () => {
  it("returns options from schema dataset_options", () => {
    const schema = defaultSchema();
    const options = datasetSelectOptions(schema, "pv1");
    expect(options.length).toBe(3);
    expect(options[0].value).toBe("pv1");
    expect(options[0].label).toContain("Price Volume");
    expect(options[0].label).toContain("24 fields");
  });

  it("returns empty array when no schema provided", () => {
    const options = datasetSelectOptions(undefined, "pv1");
    expect(options).toEqual([]);
  });

  it("includes settings_options dataset values not in dataset_options", () => {
    const schema = defaultSchema({
      dataset_options: [{ id: "pv1", name: "Price Volume" }],
      settings_options: { dataset: ["pv1", "custom_ds"] },
    });
    const options = datasetSelectOptions(schema, "pv1");
    expect(options.some((o) => o.value === "custom_ds")).toBe(true);
  });
});

describe("ConfigPanel utils - sanitizeConfigText", () => {
  it("strips control characters", () => {
    expect(sanitizeConfigText("hello\x00world")).toBe("helloworld");
    expect(sanitizeConfigText("test\x1fvalue")).toBe("testvalue");
  });

  it("truncates to max length", () => {
    const long = "a".repeat(200);
    expect(sanitizeConfigText(long).length).toBe(128);
  });

  it("passes through valid text unchanged", () => {
    expect(sanitizeConfigText("valid_dataset-v1.0")).toBe("valid_dataset-v1.0");
  });
});

describe("ConfigPanel utils - formFromImport", () => {
  it("imports from a nested ops config structure", () => {
    const imported = {
      config: {
        environment: "production",
        settings: { dataset: "analyst4", region: "EUR" },
        budget: { max_candidates_per_cycle: 50 },
      },
    };
    const current = defaultForm();
    const result = formFromImport(imported, current);
    expect(result.dataset).toBe("analyst4");
    expect(result.region).toBe("EUR");
    expect(result.candidates).toBe(50);
  });

  it("imports from a flat settings structure", () => {
    const imported = {
      settings: { dataset: "fundamental6", universe: "TOP1000" },
      budget: { max_cycles: 20 },
    };
    const current = defaultForm();
    const result = formFromImport(imported, current);
    expect(result.dataset).toBe("fundamental6");
    expect(result.universe).toBe("TOP1000");
    expect(result.cycles).toBe(20);
  });

  it("preserves current values for missing fields", () => {
    const imported = { settings: { dataset: "analyst4" } };
    const current = defaultForm({ region: "EUR", candidates: 50 });
    const result = formFromImport(imported, current);
    expect(result.dataset).toBe("analyst4");
    expect(result.region).toBe("EUR");
    expect(result.candidates).toBe(50);
  });
});
