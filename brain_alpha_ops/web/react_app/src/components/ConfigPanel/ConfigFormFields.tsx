/** Reusable form field components for ConfigPanel, with field-level help content.
 *
 *  Merges the previously separate fieldHelp.tsx (FIELD_HELP record, formatHelp,
 *  HelpIcon, helpContent) into the form-field primitives module so all
 *  field-rendering concerns live in one place. */

import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { normalizeSelectOptions, parseNumber, type SelectOption } from './utils';

const inputClass = 'form-input';

export function ConfigSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <fieldset className="panel min-w-0">
      <legend className="px-1 text-base font-semibold text-text-primary">{title}</legend>
      {description ? (
        <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">{description}</p>
      ) : null}
      <div className="mt-4 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">{children}</div>
    </fieldset>
  );
}

export function TextField({
  label,
  value,
  maxLength,
  autoComplete,
  inputMode,
  onChange,
}: {
  label: string;
  value: string;
  maxLength?: number;
  autoComplete?: string;
  inputMode?: 'email' | 'text';
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-label">
      <span className="block mb-1">{label}</span>
      <input
        type="text"
        value={value}
        maxLength={maxLength}
        autoComplete={autoComplete}
        inputMode={inputMode}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      />
    </label>
  );
}

export function PasswordField({
  label,
  value,
  maxLength,
  autoComplete = 'new-password',
  onChange,
}: {
  label: string;
  value: string;
  maxLength?: number;
  autoComplete?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-label">
      <span className="mb-1 block">{label}</span>
      <input
        type="password"
        value={value}
        maxLength={maxLength}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      />
    </label>
  );
}

export function NumberField({
  label,
  value,
  min,
  max,
  step,
  help,
  debounceMs,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  help?: ReactNode;
  debounceMs?: number;
  onChange: (value: number) => void;
}) {
  const [localValue, setLocalValue] = useState<number>(value);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 同步外部受控 value 到本地防抖状态（受控→非受控桥接）
    setLocalValue(value);
  }, [value]);

  useEffect(() => {
    if (!debounceMs) {
      return;
    }
    const timer = setTimeout(() => {
      onChange(localValue);
    }, debounceMs);
    return () => clearTimeout(timer);
  }, [localValue, debounceMs, onChange]);

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = parseNumber(event.currentTarget.value);
    if (debounceMs) {
      setLocalValue(newValue);
    } else {
      onChange(newValue);
    }
  };

  return (
    <label className="form-label">
      <span className="block mb-1">
        {label}
        {help}
      </span>
      <input
        type="number"
        value={Number.isFinite(localValue) ? localValue : ''}
        min={min}
        max={max}
        step={step}
        onChange={handleChange}
        className={inputClass}
      />
    </label>
  );
}

export function SelectField({
  label,
  value,
  options,
  placeholder,
  help,
  onChange,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  placeholder?: string;
  help?: ReactNode;
  onChange: (value: string) => void;
}) {
  const choices = normalizeSelectOptions(options);
  return (
    <label className="form-label">
      <span className="block mb-1">
        {label}
        {help}
      </span>
      <select
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      >
        {placeholder ? <option value="">{placeholder}</option> : null}
        {choices.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CheckboxField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label
      className="flex items-center justify-between gap-3 py-2 text-sm font-medium text-text-secondary"
      style={{ borderBottom: '1px solid', borderBottomColor: 'var(--color-border-default)' }}
    >
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.currentTarget.checked)}
        className="h-4 w-4"
        style={{ accentColor: 'var(--color-status-active-text)' }}
      />
    </label>
  );
}

export function ConfigValue({ label, value }: { label: string; value: unknown }) {
  return (
    <div
      className="flex min-w-0 flex-wrap justify-between gap-x-3 gap-y-1 py-1.5 text-sm"
      style={{ borderBottom: '1px solid', borderBottomColor: 'var(--color-border-default)' }}
    >
      <span className="text-text-secondary">{label}</span>
      <span className="min-w-0 break-all font-mono-value text-text-primary">
        {String((value as string | number | boolean | null | undefined) ?? '-')}
      </span>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// fieldHelp — field-level help content (what / recommendation / risk)
// ──────────────────────────────────────────────────────────────────────────

export const FIELD_HELP: Record<string, { what: string; recommendation: string; risk: string }> = {
  region: {
    what: '区域决定了 Alpha 适用的股票市场。USA 针对美国市场，EUR 针对欧洲，GLOBAL 覆盖全球。',
    recommendation: '推荐从 USA (美国) 开始，这是流动性最好的市场。',
    risk: '切换区域可能导致已有候选不再适用。',
  },
  universe: {
    what: '股票池大小决定了 Alpha 覆盖的股票数量。TOP3000 覆盖最大的 3000 只股票。',
    recommendation: '推荐 TOP3000，足够的股票数能保证统计显著性。',
    risk: '股票池越小，Alpha 越容易被极端值影响。',
  },
  delay: {
    what: '延迟（天）决定了信号从产生到可交易的时间差。Delay-1 表示使用昨天的信号今天交易。',
    recommendation: '推荐 1 天延迟，这是最标准的设置。',
    risk: '延迟过短可能引入数据窥探偏差。',
  },
  decay: {
    what: '衰减系数控制历史数据的重要性递减速度。decay=10 表示权重每 10 天衰减一半。',
    recommendation: '推荐 decay=10，这是 BRAIN 平台最常用的设置。',
    risk: 'decay 太小可能过度反应近期噪音，太大可能错过趋势变化。',
  },
  neutralization: {
    what: '中性化消除特定因子（如行业、市值）对 Alpha 的影响。SUBINDUSTRY 表示在子行业内中性化。',
    recommendation: '推荐 SUBINDUSTRY，平衡了去偏效果和信号保留。',
    risk: '过度中性化可能把有用的信号也消除掉。',
  },
  pasteurization: {
    what: '数据净化自动处理异常值和缺失数据，ON 表示启用 BRAIN 平台的自动清理。',
    recommendation: '推荐保持 ON，避免脏数据污染 Alpha 表现。',
    risk: '关闭数据净化可能产生虚假的高分 Alpha（实际不可靠）。',
  },
  unitHandling: {
    what: '单位处理决定如何处理不同股票的不同价格量级。VERIFY 表示系统会自动检查并统一单位。',
    recommendation: '推荐 VERIFY，确保跨股票比较有意义。',
    risk: '关闭单位处理可能导致不同价格量级的股票不可比较。',
  },
  nanHandling: {
    what: '空值处理决定如何处理缺失数据。ON 表示自动填充或排除空值。',
    recommendation: '推荐保持 ON。',
    risk: '关闭后空值可能导致 Alpha 计算异常。',
  },
  minSharpe: {
    what: '最低 Sharpe 比率门禁。Sharpe = 收益 / 波动率，衡量风险调整后收益。',
    recommendation: 'BRAIN 平台标准：Delay-1 最低 1.25，Delay-0 最低 2.0。',
    risk: '调低门禁可能通过更多低质量 Alpha。',
  },
  minFitness: {
    what: '最低 Fitness 门禁。Fitness = Sharpe × √(|Returns|/max(Turnover, 0.125))，综合衡量收益和换手率。',
    recommendation: 'BRAIN 平台标准：Delay-1 最低 1.0，Delay-0 最低 1.3。',
    risk: '调低门禁可能通过更多低换手性价比的 Alpha。',
  },
  maxSelfCorrelation: {
    what: '最大自相关门禁。限制提交的 Alpha 与自己已有 Alpha 的相似度。',
    recommendation: 'BRAIN 平台标准：< 0.70。',
    risk: '自相关过高的 Alpha 会被 BRAIN 平台拒绝。',
  },
};

const formatHelp = (help: (typeof FIELD_HELP)[string]) =>
  `${help.what}\n\n推荐: ${help.recommendation}\n⚠️ ${help.risk}`;

const HelpIcon = ({ help }: { help: (typeof FIELD_HELP)[string] }) => (
  <span
    title={formatHelp(help)}
    className="cursor-help ml-1 text-xs opacity-60 hover:opacity-100"
    aria-label="字段帮助信息"
    role="img"
  >
    ❓
  </span>
);

export function helpContent(key: string): ReactNode {
  const entry = FIELD_HELP[key];
  return entry ? <HelpIcon help={entry} /> : null;
}
