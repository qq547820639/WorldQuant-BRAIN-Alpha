/** Editable configuration panel for the next research run. */

import { useMemo, useState } from 'react';
import { safeDisplayErrorMessage } from '@/helpers/errorExperience';
import type { BrainCredentials } from '@/types';
import Skeleton from './Skeleton';
import ErrorCard from './ErrorCard';
import { useConfigForm } from '@/hooks/useConfigForm';
import CredentialsSection from './ConfigPanel/CredentialsSection';
import RunConfigSection from './ConfigPanel/RunConfigSection';
import { payloadFromForm } from './ConfigPanel/utils';

interface Props {
  notify: (type: 'success' | 'error' | 'warning' | 'info', msg: string) => void;
  credentials: BrainCredentials;
  onCredentialsChange: (credentials: BrainCredentials) => void;
  onConnectionTested?: (success: boolean, error: string | null) => void;
  connected?: boolean;
  contextFresh?: boolean;
  managedCredentialsAvailable?: boolean;
  onLoggedOut?: () => void;
}

export default function ConfigPanel({
  notify,
  credentials,
  onCredentialsChange,
  onConnectionTested,
  connected = false,
  contextFresh = false,
  managedCredentialsAvailable = false,
  onLoggedOut,
}: Props) {
  const {
    form,
    schema,
    globalConfig,
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
  } = useConfigForm({
    notify,
    credentials,
    onCredentialsChange,
    onConnectionTested,
    onLoggedOut,
  });

  const [temporaryConnectionOpen, setTemporaryConnectionOpen] = useState(false);
  const [showWeightModal, setShowWeightModal] = useState(false);

  const config = useMemo(
    () =>
      (globalConfig.data?.config ?? null) as {
        ops?: { scoring?: unknown };
        scoring?: unknown;
      } | null,
    [globalConfig.data]
  );

  const hasSessionCredentials = Boolean(
    credentials.username || credentials.password || credentials.token
  );
  const cacheOnlyMode = contextFresh && !connected;
  const showCredentialEditor = !cacheOnlyMode || temporaryConnectionOpen;

  const connectionStatusText = connectionApi.error
    ? `连接失败: ${safeDisplayErrorMessage(connectionApi.error)}`
    : connectionApi.data?.ok
      ? `连接正常: ${connectionApi.data.environment || form?.environment}`
      : hasSessionCredentials
        ? '凭证已填写，尚未测试'
        : managedCredentialsAvailable
          ? '未填写则使用维护者配置的托管凭证'
          : '请临时填写页面凭证';

  const handleLogout = () => {
    void logoutLocalSession();
    setTemporaryConnectionOpen(false);
  };

  if (globalConfig.loading && !config) {
    return (
      <div className="w-full max-w-5xl space-y-4">
        <Skeleton variant="card" className="mb-4" />
        <Skeleton variant="card" className="mb-4" />
        <Skeleton variant="card" />
      </div>
    );
  }

  if (globalConfig.error && !config) {
    return (
      <div className="w-full max-w-5xl">
        <ErrorCard
          title="加载配置失败"
          details={safeDisplayErrorMessage(globalConfig.error)}
          severity="error"
          onRetry={reload}
          className="mb-4"
        />
        <button type="button" onClick={reload} className="btn btn-secondary btn-sm">
          重试
        </button>
      </div>
    );
  }

  if (!form) return null;

  return (
    <form onSubmit={save} className="w-full max-w-5xl min-w-0 space-y-5 animate-fade-in">
      <div className="panel flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-2xl">
          <h2 className="text-xl font-semibold text-text-primary">连接与生产参数</h2>
          <p className="mt-2 text-sm leading-6 text-text-secondary">
            {cacheOnlyMode
              ? '当前使用本地缓存。需要官方同步、官方回测或提交前复核时，再临时连接官方服务。'
              : '调整本次运行参数；需要官方同步、官方回测或提交前复核时，临时填写 BRAIN 会话凭证并测试连接。保存配置不会保存账号、密码或 token。'}
          </p>
        </div>
        <div className="flex w-full flex-wrap justify-end gap-2 sm:w-auto">
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            aria-label="导入配置JSON"
            onChange={importConfig}
          />
          <button
            type="button"
            onClick={() => importInputRef.current?.click()}
            className="btn btn-secondary btn-sm"
            disabled={saveApi.loading}
          >
            导入
          </button>
          <button
            type="button"
            onClick={exportConfig}
            className="btn btn-secondary btn-sm"
            disabled={saveApi.loading}
          >
            导出
          </button>
          <button
            type="button"
            onClick={resetForm}
            className="btn btn-secondary btn-sm disabled:opacity-50"
            disabled={!dirty || saveApi.loading}
          >
            重置
          </button>
          <button
            type="submit"
            className="btn btn-primary btn-sm"
            disabled={!dirty || validationError !== null || saveApi.loading}
          >
            {saveApi.loading ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {validationError !== null && (
        <ErrorCard title="配置验证失败" details={validationError} severity="warning" />
      )}
      {saveApi.error && (
        <ErrorCard
          title="保存配置失败"
          details={safeDisplayErrorMessage(saveApi.error)}
          severity="error"
          onRetry={() =>
            void saveApi.call('/api/config', {
              method: 'POST',
              body: JSON.stringify(payloadFromForm(form)),
            })
          }
        />
      )}
      {saveSuccess && (
        <div
          className="rounded-md bg-positive/10 border border-positive/30 p-3 text-sm text-positive"
          role="status"
        >
          配置已保存成功
        </div>
      )}

      <CredentialsSection
        credentials={credentials}
        cacheOnlyMode={cacheOnlyMode}
        temporaryConnectionOpen={temporaryConnectionOpen}
        showCredentialEditor={showCredentialEditor}
        connectionApi={connectionApi}
        logoutApi={logoutApi}
        validationError={validationError}
        connectionStatusText={connectionStatusText}
        hasSessionCredentials={hasSessionCredentials}
        onUpdateCredential={updateCredential}
        onTestConnection={testConnection}
        onLogout={handleLogout}
        onOpenTemporaryConnection={() => setTemporaryConnectionOpen(true)}
        onCloseTemporaryConnection={() => setTemporaryConnectionOpen(false)}
      />

      <RunConfigSection
        form={form}
        schema={schema}
        datasetChoices={datasetChoices}
        scoring={scoring}
        showWeightModal={showWeightModal}
        onUpdate={update}
        onShowWeightModal={setShowWeightModal}
      />
    </form>
  );
}
