import type { ConfigForm, ConfigSchema } from './utils';
import ScoringWeightModal from './ScoringWeightModal';
import BasicConfigGroup from './BasicConfigGroup';
import AdvancedConfigGroup from './AdvancedConfigGroup';
import ScoringConfigGroup from './ScoringConfigGroup';

interface RunConfigSectionProps {
  form: ConfigForm;
  schema: ConfigSchema | undefined;
  datasetChoices: Array<{ value: string; label: string }>;
  scoring:
    | {
        prior_layer_weight?: number;
        empirical_layer_weight?: number;
        checklist_layer_weight?: number;
        market_regime?: string;
      }
    | undefined;
  showWeightModal: boolean;
  onUpdate: <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => void;
  onShowWeightModal: (show: boolean) => void;
}

export default function RunConfigSection({
  form,
  schema,
  datasetChoices,
  scoring,
  showWeightModal,
  onUpdate,
  onShowWeightModal,
}: RunConfigSectionProps) {
  return (
    <>
      <BasicConfigGroup
        form={form}
        schema={schema}
        datasetChoices={datasetChoices}
        onUpdate={onUpdate}
      />
      <AdvancedConfigGroup form={form} onUpdate={onUpdate} />
      <ScoringConfigGroup scoring={scoring} onShowWeightModal={onShowWeightModal} />

      {showWeightModal && (
        <ScoringWeightModal
          schema={schema}
          scoring={scoring}
          onClose={() => onShowWeightModal(false)}
        />
      )}
    </>
  );
}
