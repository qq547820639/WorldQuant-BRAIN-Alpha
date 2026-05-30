/** Editable configuration panel for the next research run. */

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { useApi } from "@/hooks/useApi";
import type { RunConfig, ScoringConfig } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

interface ConfigResponse {
  ok: boolean;
  config?: RunConfig;
}

interface ConfigSchemaResponse {
  ok: boolean;
  schema?: {
    settings_options?: Record<string, Array<string | number>>;
  };
}

interface ConfigForm {
  environment: string;
  autoSubmit: boolean;
  region: string;
  universe: string;
  delay: number;
  decay: number;
  neutralization: string;
  dataset: string;
  candidates: number;
  cycles: number;
  poolSize: number;
  backtestBatchSize: number;
  requireCloudSync: boolean;
  minSharpe: number;
  minFitness: number;
  minTurnover: number;
  platformMaxTurnover: number;
  maxSelfCorrelation: number;
  maxWeightConcentration: number;
}

const MAX_CONFIG_TEXT_LENGTH = 128;
const CONFIG_TEXT_PATTERN = /^[A-Za-z0-9_.:-]*$/;
const DEFAULT_REGION_OPTIONS = ["USA", "CHN", "EUR", "GLB"];
const DEFAULT_UNIVERSE_OPTIONS = ["TOP3000", "TOP1000", "TOP500"];
const DEFAULT_NEUTRALIZATION_OPTIONS = ["SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET", "NONE"];

export default function ConfigPanel({ notify }: Props) {
  const configApi = useApi<ConfigResponse>();
  const schemaApi = useApi<ConfigSchemaResponse>();
  const saveApi = useApi<ConfigResponse>();
  const [form, setForm] = useState<ConfigForm | null>(null);
  const [initialForm, setInitialForm] = useState<ConfigForm | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void configApi.call("/api/config");
    void schemaApi.call("/api/config_schema");
  }, [configApi.call, schemaApi.call]);

  const config = useMemo(() => configApi.data?.config ?? null, [configApi.data]);
  const schema = schemaApi.data?.schema;

  useEffect(() => {
    if (!config) return;
    const next = formFromConfig(config);
    setForm(next);
    setInitialForm(next);
  }, [config]);

  const dirty = useMemo(
    () => Boolean(form && initialForm && JSON.stringify(form) !== JSON.stringify(initialForm)),
    [form, initialForm],
  );
  const validationError = form ? validateForm(form, schema?.settings_options) : "";

  const update = <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => {
    setForm((current) => current ? { ...current, [key]: value } : current);
  };

  const reload = () => {
    void configApi.call("/api/config");
    void schemaApi.call("/api/config_schema");
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form || validationError) {
      notify("warning", validationError || "Configuration is not ready to save");
      return;
    }
    const result = await saveApi.call("/api/config", {
      method: "POST",
      body: JSON.stringify(payloadFromForm(form)),
    });
    if (!result?.ok) {
      notify("error", result?.error || "Failed to save configuration");
      return;
    }
    notify("success", "Configuration saved");
    void configApi.call("/api/config");
  };

  const exportConfig = () => {
    if (!form) return;
    const blob = new Blob([JSON.stringify(payloadFromForm(form), null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `brain-alpha-config-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    notify("success", "Configuration exported");
  };

  const importConfig = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file || !form) return;
    try {
      const imported = formFromImport(JSON.parse(await file.text()), form);
      const error = validateForm(imported, schema?.settings_options);
      if (error) {
        notify("error", error);
        return;
      }
      setForm(imported);
      notify("success", "Configuration imported");
    } catch (error) {
      notify("error", error instanceof Error ? error.message : "Invalid configuration JSON");
    }
  };

  if (configApi.loading && !config) {
    return (
      <ProgressFeedback
        state="loading"
        title="Configuration"
        progress={{ phase: "config_load", status_message: "Loading configuration." }}
      />
    );
  }

  if (configApi.error && !config) {
    return (
      <div className="card">
        <p className="text-danger text-sm">Failed to load config: {configApi.error}</p>
        <button type="button" onClick={reload} className="btn-secondary text-sm mt-3">Retry</button>
      </div>
    );
  }

  if (!form) return null;

  const options = schema?.settings_options;
  const scoring = config?.ops?.scoring ?? config?.scoring;

  return (
    <form onSubmit={save} className="w-full max-w-4xl min-w-0 space-y-6 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-gray-100">Configuration</h2>
          <p className="truncate text-xs text-muted">{form.environment}</p>
        </div>
        <div className="flex w-full flex-wrap justify-end gap-2 sm:w-auto">
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            aria-label="Import configuration JSON"
            onChange={importConfig}
          />
          <button
            type="button"
            onClick={() => importInputRef.current?.click()}
            className="btn-secondary text-sm"
            disabled={saveApi.loading}
          >
            Import
          </button>
          <button
            type="button"
            onClick={exportConfig}
            className="btn-secondary text-sm"
            disabled={saveApi.loading}
          >
            Export
          </button>
          <button
            type="button"
            onClick={() => initialForm && setForm({ ...initialForm })}
            className="btn-secondary text-sm disabled:opacity-50"
            disabled={!dirty || saveApi.loading}
          >
            Reset
          </button>
          <button
            type="submit"
            className="btn-primary text-sm"
            disabled={!dirty || Boolean(validationError) || saveApi.loading}
          >
            {saveApi.loading ? "Saving..." : "Save"}
          </button>
        </div>
      </div>

      {validationError && <p role="alert" className="text-xs text-danger">{validationError}</p>}
      {saveApi.error && <p role="alert" className="text-xs text-danger">{saveApi.error}</p>}

      <ConfigSection title="Brain Settings">
        <SelectField label="Region" value={form.region} options={optionValues(options, "region", form.region)} onChange={(value) => update("region", value)} />
        <SelectField label="Universe" value={form.universe} options={optionValues(options, "universe", form.universe)} onChange={(value) => update("universe", value)} />
        <SelectField label="Delay" value={String(form.delay)} options={optionValues(options, "delay", String(form.delay))} onChange={(value) => update("delay", Number(value))} />
        <NumberField label="Decay" value={form.decay} min={0} step={1} onChange={(value) => update("decay", value)} />
        <SelectField label="Neutralization" value={form.neutralization} options={optionValues(options, "neutralization", form.neutralization)} onChange={(value) => update("neutralization", value)} />
        <TextField
          label="Dataset"
          value={form.dataset}
          maxLength={MAX_CONFIG_TEXT_LENGTH}
          onChange={(value) => update("dataset", sanitizeConfigText(value))}
        />
      </ConfigSection>

      <ConfigSection title="Budget">
        <NumberField label="Max Candidates/Cycle" value={form.candidates} min={1} max={1000} step={1} onChange={(value) => update("candidates", value)} />
        <NumberField label="Max Cycles" value={form.cycles} min={1} max={10000} step={1} onChange={(value) => update("cycles", value)} />
        <NumberField label="Pool Size" value={form.poolSize} min={1} max={5000} step={1} onChange={(value) => update("poolSize", value)} />
        <NumberField label="Backtest Batch Size" value={form.backtestBatchSize} min={1} max={100} step={1} onChange={(value) => update("backtestBatchSize", value)} />
        <CheckboxField label="Cloud Sync Required" checked={form.requireCloudSync} onChange={(value) => update("requireCloudSync", value)} />
      </ConfigSection>

      <ConfigSection title="Quality Thresholds">
        <NumberField label="Min Sharpe" value={form.minSharpe} min={0} step={0.01} onChange={(value) => update("minSharpe", value)} />
        <NumberField label="Min Fitness" value={form.minFitness} min={0} step={0.01} onChange={(value) => update("minFitness", value)} />
        <NumberField label="Min Turnover" value={form.minTurnover} min={0} max={1} step={0.01} onChange={(value) => update("minTurnover", value)} />
        <NumberField label="Max Turnover" value={form.platformMaxTurnover} min={0} max={1} step={0.01} onChange={(value) => update("platformMaxTurnover", value)} />
        <NumberField label="Max Self Correlation" value={form.maxSelfCorrelation} min={0} max={1} step={0.01} onChange={(value) => update("maxSelfCorrelation", value)} />
        <NumberField label="Max Weight Concentration" value={form.maxWeightConcentration} min={0} max={1} step={0.01} onChange={(value) => update("maxWeightConcentration", value)} />
      </ConfigSection>

      <ConfigSection title="Scoring">
        <ConfigValue label="Prior Weight" value={scoring?.prior_layer_weight} />
        <ConfigValue label="Empirical Weight" value={scoring?.empirical_layer_weight} />
        <ConfigValue label="Checklist Weight" value={scoring?.checklist_layer_weight} />
        <ConfigValue label="Market Regime" value={scoring?.market_regime} />
      </ConfigSection>

      <ConfigSection title="Environment">
        <CheckboxField label="Auto Submit" checked={form.autoSubmit} onChange={(value) => update("autoSubmit", value)} />
      </ConfigSection>
    </form>
  );
}

function formFromConfig(config: RunConfig): ConfigForm {
  const settings = config.ops?.settings ?? config.settings;
  const budget = config.ops?.budget ?? config.budget;
  const thresholds = config.ops?.thresholds ?? config.thresholds;
  return {
    environment: config.environment || "production",
    autoSubmit: Boolean(config.auto_submit),
    region: String(settings?.region || "USA"),
    universe: String(settings?.universe || "TOP3000"),
    delay: Number(settings?.delay ?? 1),
    decay: Number(settings?.decay ?? 10),
    neutralization: String(settings?.neutralization || "SUBINDUSTRY"),
    dataset: String(settings?.dataset || ""),
    candidates: Number(budget?.max_candidates_per_cycle ?? 20),
    cycles: Number(budget?.max_cycles ?? 10),
    poolSize: Number(budget?.retained_alpha_pool_size ?? 10),
    backtestBatchSize: Number(budget?.official_backtest_batch_size ?? 3),
    requireCloudSync: Boolean(budget?.require_cloud_sync),
    minSharpe: Number(thresholds?.min_sharpe ?? 1.25),
    minFitness: Number(thresholds?.min_fitness ?? 1),
    minTurnover: Number(thresholds?.min_turnover ?? 0.01),
    platformMaxTurnover: Number(thresholds?.platform_max_turnover ?? 0.7),
    maxSelfCorrelation: Number(thresholds?.max_self_correlation ?? 0.7),
    maxWeightConcentration: Number(thresholds?.max_weight_concentration ?? 0.1),
  };
}

function payloadFromForm(form: ConfigForm) {
  return {
    environment: form.environment,
    autoSubmit: form.autoSubmit,
    settings: {
      region: form.region,
      universe: form.universe,
      delay: form.delay,
      decay: form.decay,
      neutralization: form.neutralization,
      dataset: form.dataset,
    },
    candidates: form.candidates,
    cycles: form.cycles,
    poolSize: form.poolSize,
    backtestBatchSize: form.backtestBatchSize,
    requireCloudSync: form.requireCloudSync,
    minSharpe: form.minSharpe,
    minFitness: form.minFitness,
    minTurnover: form.minTurnover,
    platformMaxTurnover: form.platformMaxTurnover,
    maxSelfCorrelation: form.maxSelfCorrelation,
    maxWeightConcentration: form.maxWeightConcentration,
  };
}

function formFromImport(value: unknown, fallback: ConfigForm): ConfigForm {
  const root = asRecord(value);
  if (!root) throw new Error("Configuration JSON must be an object.");
  const source = asRecord(root.config) || root;
  if (asRecord(source.ops)) {
    return formFromConfig(source as unknown as RunConfig);
  }
  const settings = asRecord(source.settings) || {};
  return {
    ...fallback,
    environment: stringValue(source.environment, fallback.environment),
    autoSubmit: booleanValue(source.autoSubmit ?? source.auto_submit, fallback.autoSubmit),
    region: stringValue(settings.region, fallback.region),
    universe: stringValue(settings.universe, fallback.universe),
    delay: numberValue(settings.delay, fallback.delay),
    decay: numberValue(settings.decay, fallback.decay),
    neutralization: stringValue(settings.neutralization, fallback.neutralization),
    dataset: stringValue(settings.dataset, fallback.dataset),
    candidates: numberValue(source.candidates, fallback.candidates),
    cycles: numberValue(source.cycles, fallback.cycles),
    poolSize: numberValue(source.poolSize, fallback.poolSize),
    backtestBatchSize: numberValue(source.backtestBatchSize, fallback.backtestBatchSize),
    requireCloudSync: booleanValue(source.requireCloudSync, fallback.requireCloudSync),
    minSharpe: numberValue(source.minSharpe, fallback.minSharpe),
    minFitness: numberValue(source.minFitness, fallback.minFitness),
    minTurnover: numberValue(source.minTurnover, fallback.minTurnover),
    platformMaxTurnover: numberValue(source.platformMaxTurnover, fallback.platformMaxTurnover),
    maxSelfCorrelation: numberValue(source.maxSelfCorrelation, fallback.maxSelfCorrelation),
    maxWeightConcentration: numberValue(source.maxWeightConcentration, fallback.maxWeightConcentration),
  };
}

function validateForm(form: ConfigForm, options?: Record<string, Array<string | number>>) {
  if (!form.region || !form.universe || !form.neutralization) return "Brain settings are incomplete.";
  if (!isAllowedOption(form.region, options, "region", DEFAULT_REGION_OPTIONS)) return "Region is not supported.";
  if (!isAllowedOption(form.universe, options, "universe", DEFAULT_UNIVERSE_OPTIONS)) return "Universe is not supported.";
  if (!isAllowedOption(form.neutralization, options, "neutralization", DEFAULT_NEUTRALIZATION_OPTIONS)) {
    return "Neutralization is not supported.";
  }
  if (form.dataset.length > MAX_CONFIG_TEXT_LENGTH) return `Dataset must be ${MAX_CONFIG_TEXT_LENGTH} characters or fewer.`;
  if (form.dataset && !CONFIG_TEXT_PATTERN.test(form.dataset)) {
    return "Dataset may only contain letters, numbers, underscore, dash, dot, or colon.";
  }
  if (!isIntegerInRange(form.delay, 0, 1)) return "Delay must be 0 or 1.";
  if (!isIntegerInRange(form.decay, 0)) return "Decay must be a non-negative integer.";
  if (!isIntegerInRange(form.candidates, 1, 1000)) return "Max candidates per cycle must be between 1 and 1000.";
  if (!isIntegerInRange(form.cycles, 1, 10000)) return "Max cycles must be between 1 and 10000.";
  if (!isIntegerInRange(form.poolSize, 1, 5000)) return "Pool size must be between 1 and 5000.";
  if (!isIntegerInRange(form.backtestBatchSize, 1, 100)) return "Backtest batch size must be between 1 and 100.";
  for (const [label, value] of [
    ["Min Sharpe", form.minSharpe],
    ["Min Fitness", form.minFitness],
  ] as const) {
    if (!Number.isFinite(value) || value < 0) return `${label} must be a non-negative number.`;
  }
  for (const [label, value] of [
    ["Min Turnover", form.minTurnover],
    ["Max Turnover", form.platformMaxTurnover],
    ["Max Self Correlation", form.maxSelfCorrelation],
    ["Max Weight Concentration", form.maxWeightConcentration],
  ] as const) {
    if (!Number.isFinite(value) || value < 0 || value > 1) return `${label} must be between 0 and 1.`;
  }
  if (form.minTurnover > form.platformMaxTurnover) return "Min turnover cannot exceed max turnover.";
  return "";
}

function optionValues(
  options: Record<string, Array<string | number>> | undefined,
  key: string,
  current: string,
) {
  return Array.from(new Set([...(options?.[key] || []).map(String), current].filter(Boolean)));
}

function allowedOptionValues(
  options: Record<string, Array<string | number>> | undefined,
  key: string,
  fallback: string[],
) {
  const values = options?.[key]?.map(String).filter(Boolean);
  return values?.length ? values : fallback;
}

function isAllowedOption(
  value: string,
  options: Record<string, Array<string | number>> | undefined,
  key: string,
  fallback: string[],
) {
  return allowedOptionValues(options, key, fallback).includes(value);
}

function isIntegerInRange(value: number, min: number, max = Number.POSITIVE_INFINITY) {
  return Number.isInteger(value) && value >= min && value <= max;
}

function parseNumber(value: string) {
  return value.trim() ? Number(value) : Number.NaN;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function stringValue(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function booleanValue(value: unknown, fallback: boolean) {
  return typeof value === "boolean" ? value : fallback;
}

function sanitizeConfigText(value: string) {
  return value.replace(/[\x00-\x1F\x7F]/g, "").slice(0, MAX_CONFIG_TEXT_LENGTH);
}

function ConfigSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="card min-w-0">
      <legend className="text-sm font-semibold text-gray-200 px-1">{title}</legend>
      <div className="grid grid-cols-1 gap-x-5 gap-y-3 mt-2 md:grid-cols-2">{children}</div>
    </fieldset>
  );
}

function TextField({
  label,
  value,
  maxLength,
  onChange,
}: {
  label: string;
  value: string;
  maxLength?: number;
  onChange: (value: string) => void;
}) {
  return (
    <label className="text-xs text-gray-400">
      <span className="block mb-1">{label}</span>
      <input
        type="text"
        value={value}
        maxLength={maxLength}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-xs text-gray-400">
      <span className="block mb-1">{label}</span>
      <input
        type="number"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(parseNumber(event.currentTarget.value))}
        className={inputClass}
      />
    </label>
  );
}

function SelectField({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label className="text-xs text-gray-400">
      <span className="block mb-1">{label}</span>
      <select value={value} onChange={(event) => onChange(event.currentTarget.value)} className={inputClass}>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function CheckboxField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 text-xs text-gray-400 border-b border-gray-800/50 py-2">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.currentTarget.checked)} className="h-4 w-4 accent-brand-500" />
    </label>
  );
}

function ConfigValue({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex min-w-0 flex-wrap justify-between gap-x-3 gap-y-1 text-xs py-1.5 border-b border-gray-800/50">
      <span className="text-gray-400">{label}</span>
      <span className="min-w-0 break-all text-gray-200 font-mono">{String(value ?? "-")}</span>
    </div>
  );
}

const inputClass = "w-full min-w-0 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500";
