/** Configuration panel displaying current run settings. */

import { useEffect } from "react";
import { useApi } from "@/hooks/useApi";
import type { RunConfig } from "@/types";
import ProgressFeedback from "@/components/ProgressFeedback";

interface Props {
  notify: (type: "success" | "error" | "warning" | "info", msg: string) => void;
}

export default function ConfigPanel({ notify }: Props) {
  const api = useApi<RunConfig>();

  useEffect(() => {
    api.call("/api/config");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cfg = api.data;

  if (api.loading) {
    return (
      <ProgressFeedback
        state="loading"
        title="Configuration"
        progress={{ phase: "config_load", status_message: "Loading configuration." }}
      />
    );
  }

  if (api.error) {
    return (
      <div className="card">
        <p className="text-danger text-sm">Failed to load config: {api.error}</p>
        <button onClick={() => api.call("/api/config")} className="btn-secondary text-sm mt-3">Retry</button>
      </div>
    );
  }

  if (!cfg) return null;

  return (
    <div className="space-y-6 max-w-2xl animate-fade-in">
      <ConfigSection title="Brain Settings">
        <ConfigRow label="Region" value={cfg.settings?.region} />
        <ConfigRow label="Universe" value={cfg.settings?.universe} />
        <ConfigRow label="Delay" value={cfg.settings?.delay} />
        <ConfigRow label="Decay" value={cfg.settings?.decay} />
        <ConfigRow label="Neutralization" value={cfg.settings?.neutralization} />
        <ConfigRow label="Dataset" value={cfg.settings?.dataset || "(auto)"} />
      </ConfigSection>

      <ConfigSection title="Budget">
        <ConfigRow label="Max Candidates/Cycle" value={cfg.budget?.max_candidates_per_cycle} />
        <ConfigRow label="Max Cycles" value={cfg.budget?.max_cycles} />
        <ConfigRow label="Pool Size" value={cfg.budget?.retained_alpha_pool_size} />
        <ConfigRow label="Backtest Batch Size" value={cfg.budget?.official_backtest_batch_size} />
        <ConfigRow label="Cloud Sync Required" value={cfg.budget?.require_cloud_sync ? "Yes" : "No"} />
      </ConfigSection>

      <ConfigSection title="Quality Thresholds">
        <ConfigRow label="Min Sharpe" value={cfg.thresholds?.min_sharpe} />
        <ConfigRow label="Min Fitness" value={cfg.thresholds?.min_fitness} />
        <ConfigRow label="Min Turnover" value={`${((cfg.thresholds?.min_turnover ?? 0) * 100).toFixed(0)}%`} />
        <ConfigRow label="Max Turnover" value={`${((cfg.thresholds?.platform_max_turnover ?? 0) * 100).toFixed(0)}%`} />
        <ConfigRow label="Max Self Correlation" value={cfg.thresholds?.max_self_correlation} />
        <ConfigRow label="Max Weight Concentration" value={`${((cfg.thresholds?.max_weight_concentration ?? 0) * 100).toFixed(0)}%`} />
      </ConfigSection>

      <ConfigSection title="Scoring">
        <ConfigRow label="Prior Weight" value={cfg.scoring?.prior_layer_weight} />
        <ConfigRow label="Empirical Weight" value={cfg.scoring?.empirical_layer_weight} />
        <ConfigRow label="Checklist Weight" value={cfg.scoring?.checklist_layer_weight} />
        <ConfigRow label="Market Regime" value={cfg.scoring?.market_regime} />
      </ConfigSection>

      <ConfigSection title="Environment">
        <ConfigRow label="Environment" value={cfg.environment} />
        <ConfigRow label="Auto Submit" value={cfg.auto_submit ? "Enabled" : "Disabled"} />
      </ConfigSection>
    </div>
  );
}

function ConfigSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card">
      <h3 className="text-sm font-semibold text-gray-200 mb-3">{title}</h3>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex justify-between text-xs py-1.5 border-b border-gray-800/50 last:border-0">
      <span className="text-gray-400">{label}</span>
      <span className="text-gray-200 font-mono">{String(value ?? "-")}</span>
    </div>
  );
}
