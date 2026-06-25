import { type ConfigForm } from './utils';
import { ConfigSection, NumberField } from './ConfigFormFields';
import { helpContent } from './fieldHelp';

interface AdvancedConfigGroupProps {
  form: ConfigForm;
  onUpdate: <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => void;
}

export default function AdvancedConfigGroup({ form, onUpdate }: AdvancedConfigGroupProps) {
  return (
    <ConfigSection
      title="质量阈值"
      description="提交前门禁，低于阈值的候选只能进入研究或优化状态。"
    >
      <NumberField
        label="最低夏普比率"
        value={form.minSharpe}
        min={0}
        step={0.01}
        help={helpContent('minSharpe')}
        debounceMs={300}
        onChange={(value) => onUpdate('minSharpe', value)}
      />
      <NumberField
        label="最低适应度"
        value={form.minFitness}
        min={0}
        step={0.01}
        help={helpContent('minFitness')}
        debounceMs={300}
        onChange={(value) => onUpdate('minFitness', value)}
      />
      <NumberField
        label="最低换手率"
        value={form.minTurnover}
        min={0}
        max={1}
        step={0.01}
        debounceMs={300}
        onChange={(value) => onUpdate('minTurnover', value)}
      />
      <NumberField
        label="最高换手率"
        value={form.platformMaxTurnover}
        min={0}
        max={1}
        step={0.01}
        debounceMs={300}
        onChange={(value) => onUpdate('platformMaxTurnover', value)}
      />
      <NumberField
        label="最大自相关性"
        value={form.maxSelfCorrelation}
        min={0}
        max={1}
        step={0.01}
        help={helpContent('maxSelfCorrelation')}
        debounceMs={300}
        onChange={(value) => onUpdate('maxSelfCorrelation', value)}
      />
      <NumberField
        label="最大权重集中度"
        value={form.maxWeightConcentration}
        min={0}
        max={1}
        step={0.01}
        debounceMs={300}
        onChange={(value) => onUpdate('maxWeightConcentration', value)}
      />
    </ConfigSection>
  );
}
