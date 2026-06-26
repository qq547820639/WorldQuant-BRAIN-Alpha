import type { BrainCredentials } from '@/types';
import { safeDisplayErrorMessage } from '@/helpers/errorExperience';
import { TextField, PasswordField } from './ConfigFormFields';
import LocalCacheConnectionSection from './LocalCacheConnectionSection';
import { ConfigSection } from './ConfigFormFields';

interface CredentialsSectionProps {
  credentials: BrainCredentials;
  cacheOnlyMode: boolean;
  temporaryConnectionOpen: boolean;
  showCredentialEditor: boolean;
  connectionApi: {
    loading: boolean;
    error: string | null;
    data?: { ok: boolean; environment?: string } | null;
  };
  logoutApi: {
    loading: boolean;
    error: string | null;
  };
  validationError: string | null;
  connectionStatusText: string;
  hasSessionCredentials: boolean;
  onUpdateCredential: <K extends keyof BrainCredentials>(
    key: K,
    value: BrainCredentials[K]
  ) => void;
  onTestConnection: () => void;
  onLogout: () => void;
  onOpenTemporaryConnection: () => void;
  onCloseTemporaryConnection: () => void;
}

export default function CredentialsSection({
  credentials,
  cacheOnlyMode,
  temporaryConnectionOpen,
  showCredentialEditor,
  connectionApi,
  logoutApi,
  validationError,
  connectionStatusText,
  onUpdateCredential,
  onTestConnection,
  onLogout,
  onOpenTemporaryConnection,
  onCloseTemporaryConnection,
}: CredentialsSectionProps) {
  const credentialFields = (
    <div className="grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">
      <TextField
        label="账户邮箱"
        value={credentials.username}
        autoComplete="off"
        inputMode="email"
        maxLength={160}
        onChange={(value) => onUpdateCredential('username', value.trim())}
      />
      <PasswordField
        label="密码"
        value={credentials.password}
        autoComplete="new-password"
        onChange={(value) => onUpdateCredential('password', value)}
      />
      <PasswordField
        label="Token"
        value={credentials.token}
        autoComplete="off"
        maxLength={512}
        onChange={(value) => onUpdateCredential('token', value.trim())}
      />
      <div className="flex flex-col gap-2 sm:items-start md:col-span-2">
        <button
          type="button"
          onClick={onTestConnection}
          className="btn btn-secondary btn-sm"
          disabled={connectionApi.loading || validationError !== null}
        >
          {connectionApi.loading ? '测试中...' : '测试 BRAIN 连接'}
        </button>
        <p
          className={`text-xs ${connectionApi.error ? 'text-negative' : connectionApi.data?.ok ? 'text-positive' : 'text-text-tertiary'}`}
          role="status"
          aria-live="polite"
        >
          {connectionStatusText}
        </p>
      </div>
    </div>
  );

  if (cacheOnlyMode) {
    return (
      <LocalCacheConnectionSection
        temporaryConnectionOpen={temporaryConnectionOpen}
        logoutLoading={logoutApi.loading}
        logoutError={logoutApi.error ? safeDisplayErrorMessage(logoutApi.error) : null}
        onOpenTemporaryConnection={onOpenTemporaryConnection}
        onCloseTemporaryConnection={onCloseTemporaryConnection}
        onLogout={onLogout}
      >
        {credentialFields}
      </LocalCacheConnectionSection>
    );
  }

  if (!showCredentialEditor) {
    return null;
  }

  return (
    <ConfigSection
      title="BRAIN 连接"
      description="这些字段只保留在当前页面，用于本次连接测试和验证。"
    >
      {credentialFields}
    </ConfigSection>
  );
}
