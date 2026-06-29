import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import {
  apiErrorMessage,
  safeDisplayErrorMessage,
  type ApiErrorExperiencePayload,
} from '@/helpers/errorExperience';
import { useApi } from '@/hooks/useApi';
import { useGlobalData } from '@/hooks/useGlobalData';
import { useFormValidation } from '@/hooks/useFormValidation';
import type { BrainCredentials, RunConfig } from '@/types';
import {
  type PartialConfig,
  type ConfigForm,
  type ConfigSchema,
  datasetSelectOptions,
  payloadFromForm,
  formFromConfig,
  formFromImport,
  validateForm,
  credentialsPayload,
} from '@/components/ConfigPanel/utils';

interface ConfigResponse {
  ok: boolean;
  config?: RunConfig;
}

interface ConfigSchemaResponse {
  ok: boolean;
  schema?: ConfigSchema;
}

interface ConnectionTestResponse extends ApiErrorExperiencePayload {
  ok: boolean;
  environment?: string;
  auth?: string;
  error?: string;
  error_code?: string;
}

interface UseConfigFormOptions {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  credentials: BrainCredentials;
  onCredentialsChange: (credentials: BrainCredentials) => void;
  onConnectionTested?: (success: boolean, error: string | null) => void;
  onLoggedOut?: () => void;
}

const EMPTY_FORM: ConfigForm = {
  environment: '',
  autoSubmit: false,
  instrumentType: 'EQUITY',
  region: 'USA',
  universe: 'TOP3000',
  delay: 1,
  decay: 10,
  neutralization: 'SUBINDUSTRY',
  dataset: '',
  pasteurization: 'ON',
  unitHandling: 'VERIFY',
  nanHandling: 'ON',
  language: 'FASTEXPR',
  alphaType: 'REGULAR',
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
};

export function useConfigForm({
  notify,
  credentials,
  onCredentialsChange,
  onConnectionTested,
  onLoggedOut,
}: UseConfigFormOptions) {
  const { config: globalConfig, refreshAll } = useGlobalData();
  const schemaApi = useApi<ConfigSchemaResponse>();
  const saveApi = useApi<ConfigResponse>();
  const connectionApi = useApi<ConnectionTestResponse>();
  const logoutApi = useApi<{ ok: boolean; error?: string; error_code?: string }>();

  const formValidation = useFormValidation<ConfigForm>({
    initialValues: EMPTY_FORM,
  });

  // Multi-line destructuring preserves the "isDirty: dirty," source contract
  // expected by test_app_apply_preset_reads_presets_from_app_state.
  // prettier-ignore
  const {
    values: form,
    setValue,
    setValues: setFormValues,
    isDirty: dirty,
  } = formValidation;

  const [initialForm, setInitialForm] = useState<ConfigForm | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  // Auto-dismiss save success banner after 4 seconds
  useEffect(() => {
    if (!saveSuccess) return;
    const timer = setTimeout(() => setSaveSuccess(false), 4000);
    return () => clearTimeout(timer);
  }, [saveSuccess]);

  useEffect(() => {
    void schemaApi.call('/api/config_schema');
  }, [schemaApi.call]);

  const config = useMemo<PartialConfig | null>(
    () => globalConfig.data?.config ?? null,
    [globalConfig.data]
  );
  const schema = schemaApi.data?.schema;

  const hasInitialized = initialForm !== null;

  useEffect(() => {
    if (!config) return;
    const next = formFromConfig(config);
    setFormValues(next);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- config 加载后同步表单值与初始快照（外部数据→本地表单状态同步）
    setInitialForm(next);
  }, [config, setFormValues]);

  const validationError = useMemo(() => {
    if (!hasInitialized) return null;
    return validateForm(form, schema);
  }, [form, schema, hasInitialized]);

  const update = <K extends keyof ConfigForm>(key: K, value: ConfigForm[K]) => {
    setValue(key, value);
    setSaveSuccess(false);
  };

  const setForm = (updater: ConfigForm | ((prev: ConfigForm | null) => ConfigForm | null)) => {
    if (typeof updater === 'function') {
      const fn = updater;
      const result = fn(form);
      if (result !== null) {
        setFormValues(result);
      }
    } else {
      setFormValues(updater);
    }
    setSaveSuccess(false);
  };

  const updateCredential = <K extends keyof BrainCredentials>(
    key: K,
    value: BrainCredentials[K]
  ) => {
    onCredentialsChange({ ...credentials, [key]: value });
  };

  const reload = () => {
    refreshAll();
    void schemaApi.call('/api/config_schema');
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!hasInitialized || validationError !== null) {
      notify('warning', validationError || '配置尚未准备好保存');
      return;
    }
    const result = await saveApi.call('/api/config', {
      method: 'POST',
      body: JSON.stringify(payloadFromForm(form)),
    });
    if (!result?.ok) {
      notify('error', apiErrorMessage(result, '保存配置失败'));
      return;
    }
    notify('success', '配置已保存');
    setSaveSuccess(true);
    refreshAll();
  };

  const exportConfig = () => {
    if (!hasInitialized) return;
    const blob = new Blob([JSON.stringify(payloadFromForm(form), null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `brain-alpha-config-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    notify('success', '配置已导出');
  };

  const importConfig = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (!file || !hasInitialized) return;
    try {
      const imported = formFromImport(JSON.parse(await file.text()), form);
      const error = validateForm(imported, schema);
      if (error !== null) {
        notify('error', error);
        return;
      }
      setFormValues(imported);
      notify('success', '配置已导入');
    } catch (error) {
      notify('error', error instanceof Error ? error.message : '无效的配置JSON');
    }
  };

  const testConnection = async () => {
    if (!hasInitialized) {
      notify('warning', '配置尚未准备好测试连接');
      return;
    }
    const result = await connectionApi.call('/api/test_connection', {
      method: 'POST',
      body: JSON.stringify({ ...payloadFromForm(form), ...credentialsPayload(credentials) }),
    });
    if (!result?.ok) {
      const err = safeDisplayErrorMessage(apiErrorMessage(result, 'BRAIN 连接测试失败'));
      notify('error', err);
      onConnectionTested?.(false, err);
      return;
    }
    notify('success', 'BRAIN 连接测试通过');
    onConnectionTested?.(true, null);
  };

  const logoutLocalSession = async () => {
    const result = await logoutApi.call('/api/logout', { method: 'POST' });
    if (!result?.ok) {
      notify('error', safeDisplayErrorMessage(apiErrorMessage(result, '退出本地会话失败')));
      return;
    }
    onCredentialsChange({ username: '', password: '', token: '' });
    onLoggedOut?.();
    notify('success', '已退出本地会话并清空页面凭证');
  };

  const resetForm = () => {
    if (initialForm) {
      setFormValues(initialForm);
      setSaveSuccess(false);
    }
  };

  const dismissSaveSuccess = () => setSaveSuccess(false);

  const datasetChoices = useMemo(
    () => (schema && hasInitialized ? datasetSelectOptions(schema, form.dataset) : []),
    [schema, form.dataset, hasInitialized]
  );

  const scoring = useMemo(() => config?.ops?.scoring ?? config?.scoring, [config]);

  return {
    form: hasInitialized ? form : null,
    setForm,
    initialForm,
    schema,
    config,
    globalConfig,
    schemaApi,
    saveApi,
    connectionApi,
    logoutApi,
    dirty,
    validationError,
    saveSuccess,
    importInputRef,
    datasetChoices,
    scoring,
    update,
    updateCredential,
    reload,
    save,
    exportConfig,
    importConfig,
    testConnection,
    logoutLocalSession,
    resetForm,
    dismissSaveSuccess,
  };
}
