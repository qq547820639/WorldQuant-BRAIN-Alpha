import type { CardViewId } from '@/types';
import type { CardConfig } from './cardConfigs';
import type { StateCardsMetrics } from './metrics';
import { getMetricValue, getMetricLabel } from './metrics';

interface Props {
  config: CardConfig;
  metrics: StateCardsMetrics;
  onNavigate: (view: CardViewId) => void;
}

export default function StateCardItem({ config, metrics, onNavigate }: Props) {
  return (
    <button
      key={config.id}
      type="button"
      onClick={() => onNavigate(config.id)}
      className="group relative min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white p-5 text-left shadow-sm transition-all duration-200 hover:border-brand-200 hover:bg-brand-50/40 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:ring-offset-2 focus:ring-offset-slate-50"
    >
      {/* 背景渐变 */}
      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${config.color} opacity-80`} />

      {/* 图标 */}
      <div className="relative mb-4">
        <span
          className="font-mono text-xs font-semibold tracking-wide text-brand-700"
          aria-hidden="true"
        >
          {config.icon}
        </span>
      </div>

      {/* 标题和描述 */}
      <div className="relative">
        <h3 className="text-lg font-bold text-slate-950 tracking-tight">{config.title}</h3>
        <p className="mt-2 text-sm text-slate-600 leading-6">{config.description}</p>
      </div>

      {/* 指标显示 */}
      <div className="relative mt-6 pt-4 border-t border-slate-200">
        <div className="grid min-w-0 gap-2">
          <span className="min-w-0 text-sm font-medium leading-tight text-slate-600">
            {getMetricLabel(metrics, config.id)}
          </span>
          <span className="min-w-0 max-w-full break-words text-right text-2xl font-bold leading-tight tabular-nums text-slate-950 xl:text-xl 2xl:text-2xl">
            {getMetricValue(metrics, config.id)}
          </span>
        </div>
      </div>

      {/* 操作提示 */}
      <div className="relative mt-4">
        <span className="inline-flex items-center gap-2 text-sm font-medium text-brand-700 group-hover:text-brand-800 transition-colors">
          {config.action}
          <svg
            aria-hidden="true"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="transition-transform group-hover:translate-x-1"
          >
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </span>
      </div>
    </button>
  );
}
