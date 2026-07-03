/** ConfigPanel credential, local-cache connection, and scoring-weight modal sections.
 *
 *  Merges the previously separate CredentialsSection.tsx,
 *  LocalCacheConnectionSection.tsx, and ScoringWeightModal.tsx into a single
 *  module covering all credential/connection UX plus the read-only scoring
 *  weight transparency modal. All component implementations are preserved
 *  verbatim; only the module boundary changed. */

import type { ReactNode } from 'react';
import { useEffect, useRef } from 'react';
import type { BrainCredentials } from '@/types';
import { isRecord } from '@/types';
import { safeDisplayErrorMessage } from '@/helpers/errorExperience';
import type { ConfigSchema } from './utils';
import { TextField, PasswordField, ConfigSection } from './ConfigFormFields';

// ──────────────────────────────────────────────────────────────────────────
// LocalCacheConnectionSection — cache-only session UI with folding
// ──────────────────────────────────────────────────────────────────────────

interface LocalCacheConnectionSectionProps {
  temporaryConnectionOpen: boolean;
  logoutLoading: boolean;
  logoutError: string | null;
  onOpenTemporaryConnection: () => void;
  onCloseTemporaryConnection: () => void;
  onLogout: () => void;
  children?: ReactNode;
}

export function LocalCacheConnectionSection({
  temporaryConnectionOpen,
  logoutLoading,
  logoutError,
  onOpenTemporaryConnection,
  onCloseTemporaryConnection,
  onLogout,
  children,
}: LocalCacheConnectionSectionProps) {
  return (
    <fieldset className="panel min-w-0 border-info/30 bg-info/5">
      <legend className="px-1 text-base font-semibold text-text-primary">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-info" aria-hidden="true" />
          本地缓存会话
        </span>
      </legend>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
        当前使用本地缓存运行。无需登录即可浏览历史候选、查看评分结果和调整配置。
        需要官方同步、官方回测或提交前复核时，再临时连接官方服务。
      </p>

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onLogout}
          className="btn btn-secondary btn-sm"
          disabled={logoutLoading}
          aria-describedby="cache-logout-desc"
        >
          {logoutLoading ? '退出中...' : '退出本地会话'}
        </button>
        {!temporaryConnectionOpen ? (
          <button
            type="button"
            onClick={onOpenTemporaryConnection}
            className="btn btn-primary btn-sm"
            aria-describedby="temp-connect-desc"
          >
            临时连接官方服务
          </button>
        ) : (
          <button
            type="button"
            onClick={onCloseTemporaryConnection}
            className="btn btn-secondary btn-sm"
          >
            收起凭据输入
          </button>
        )}
      </div>

      <p id="cache-logout-desc" className="mt-2 text-xs text-text-tertiary">
        退出本地会话会清空当前页面的所有缓存状态和历史记录。
      </p>

      {logoutError && (
        <p role="alert" className="mt-3 text-xs text-negative">
          {logoutError}
        </p>
      )}

      {temporaryConnectionOpen && (
        <div className="mt-5 pt-4 border-t border-border-subtle">
          <p id="temp-connect-desc" className="mb-3 text-sm text-text-secondary">
            以下凭据仅用于本次临时连接，不会保存到配置文件或本地存储。
            关闭页面或退出会话后立即失效。
          </p>
          {children}
        </div>
      )}
    </fieldset>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// CredentialsSection — credential editor with cache-mode folding
// ──────────────────────────────────────────────────────────────────────────

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

export function CredentialsSection({
  credentials,
  cacheOnlyMode,
  temporaryConnectionOpen,
  showCredentialEditor,
  connectionApi,
  logoutApi,
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
          disabled={connectionApi.loading}
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

// ──────────────────────────────────────────────────────────────────────────
// ScoringWeightModal — read-only display from /api/config_schema (P2-4)
// ──────────────────────────────────────────────────────────────────────────

interface WeightDimension {
  name: string;
  weight: number;
  children?: WeightDimension[];
}

function extractScoringWeights(
  schema: ConfigSchema | undefined,
  scoring: Record<string, unknown> | undefined
): { layers: WeightDimension[] } {
  const layers: WeightDimension[] = [];

  const schemaScoring = schema?.scoring;
  const schemaWeights = schema?.scoring_weights;

  const priorWeight = Number(scoring?.prior_layer_weight ?? 0.35);
  const priorChildren = extractLayerChildren(schemaScoring, 'prior', schemaWeights);
  layers.push({ name: '先验评分', weight: priorWeight, children: priorChildren });

  const empiricalWeight = Number(scoring?.empirical_layer_weight ?? 0.4);
  const empiricalChildren = extractLayerChildren(schemaScoring, 'empirical', schemaWeights);
  layers.push({ name: '实证评分', weight: empiricalWeight, children: empiricalChildren });

  const checklistWeight = Number(scoring?.checklist_layer_weight ?? 0.25);
  const checklistChildren = extractLayerChildren(schemaScoring, 'checklist', schemaWeights);
  layers.push({ name: '提交清单', weight: checklistWeight, children: checklistChildren });

  return { layers };
}

function extractLayerChildren(
  schemaScoring: Record<string, unknown> | undefined,
  layer: string,
  schemaWeights: Record<string, unknown> | undefined
): WeightDimension[] {
  const children: WeightDimension[] = [];

  const layerRaw = schemaScoring?.[layer];
  const layerData = isRecord(layerRaw) ? layerRaw : undefined;
  const weightsRaw = schemaWeights?.[layer];
  const layerWeights = isRecord(weightsRaw) ? weightsRaw : undefined;
  const dimsRaw = layerData?.dimensions ?? layerData?.sub_dimensions ?? layerWeights ?? {};
  const dims = isRecord(dimsRaw) ? dimsRaw : {};

  if (dims && typeof dims === 'object') {
    for (const [key, value] of Object.entries(dims)) {
      if (typeof value === 'number') {
        children.push({ name: formatDimName(key), weight: value });
      } else if (isRecord(value)) {
        const weight = typeof value.weight === 'number' ? value.weight : 0;
        const subChildren = extractLayerChildren({ [key]: value }, key, undefined);
        const dimName: string | number | boolean = (value.name ?? value.label ?? key) as
          | string
          | number
          | boolean;
        children.push({
          name: formatDimName(String(dimName)),
          weight,
          children: subChildren.length ? subChildren : undefined,
        });
      }
    }
  }

  return children;
}

function formatDimName(key: string): string {
  const labels: Record<string, string> = {
    economic_logic: '经济逻辑',
    structure: '结构复杂度',
    field_operator_support: '字段与算子',
    data_compliance: '数据合规',
    horizon_turnover_proxy: '窗口/换手代理',
    risk_control_proxy: '风控代理',
    diversity: '多样性',
    explainability: '可解释性',
    economic_concepts: '经济概念',
    sharpe: 'Sharpe',
    fitness: 'Fitness',
    turnover: '换手率',
    returns: '收益率',
    drawdown: '回撤',
    self_correlation: '自相关',
    prod_correlation: '生产相关性',
    weight_concentration: '权重集中度',
    sub_universe_sharpe: '子宇宙Sharpe',
    is_oos_ratio: 'IS/OOS比率',
    margin_bps: '保证金(bps)',
    official_metrics_present: '官方指标存在',
    official_pass: '官方通过',
    economic_logic_check: '经济逻辑检查',
    data_delay_conservative: '保守延迟设置',
    local_quality: '本地质量预筛',
    self_correlation_proxy: '自相关代理',
  };
  return labels[key] ?? key.replace(/_/g, ' ');
}

export function ScoringWeightModal({
  schema,
  scoring,
  onClose,
}: {
  schema: ConfigSchema | undefined;
  scoring: Record<string, unknown> | undefined;
  onClose: () => void;
}) {
  const { layers } = extractScoringWeights(schema, scoring);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const timer = setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      document.removeEventListener('keydown', handleKeyDown);
      clearTimeout(timer);
    };
  }, [onClose]);

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--color-overlay-strong)',
        backdropFilter: 'blur(3px)',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="scoring-weight-title"
    >
      <div
        ref={dialogRef}
        style={{
          background: 'var(--color-surface-elevated)',
          borderRadius: 8,
          border: '0.5px solid var(--color-border-default)',
          maxWidth: 560,
          width: 'calc(100% - 32px)',
          maxHeight: '80vh',
          overflow: 'auto',
          padding: '24px 20px 20px',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: 20,
          }}
        >
          <div>
            <h3 id="scoring-weight-title" className="text-base font-semibold text-text-primary">
              评分配置详细权重
            </h3>
            <p className="text-xs text-text-tertiary mt-1">
              来自 /api/config_schema 的只读展示，各层及其子维度权重分配。
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="btn btn-ghost btn-sm"
            aria-label="关闭"
            style={{ padding: '2px 6px', fontSize: 18, lineHeight: 1 }}
          >
            ✕
          </button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {layers.map((layer, i) => (
            <div
              key={i}
              style={{
                border: '0.5px solid var(--color-border-default)',
                borderRadius: 6,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 14px',
                  background: 'var(--color-layer-header-bg)',
                  borderBottom:
                    layer.children && layer.children.length > 0
                      ? '0.5px solid var(--color-border-default)'
                      : 'none',
                }}
              >
                <span className="text-sm font-medium text-text-primary">{layer.name}</span>
                <span className="text-sm font-mono-value text-accent">
                  {(layer.weight * 100).toFixed(0)}%
                </span>
              </div>

              {layer.children && layer.children.length > 0 && (
                <div style={{ padding: '8px 14px' }}>
                  {layer.children.map((dim, j) => (
                    <div
                      key={j}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '6px 0',
                        borderBottom:
                          j < (layer.children?.length ?? 0) - 1
                            ? '0.5px solid var(--color-divider)'
                            : 'none',
                      }}
                    >
                      <span className="text-xs text-text-secondary">{dim.name}</span>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div
                          className="progress-bar"
                          style={{ width: 60, height: 4 }}
                          role="progressbar"
                          aria-valuemin={0}
                          aria-valuemax={1}
                          aria-valuenow={dim.weight}
                        >
                          <div
                            className="progress-bar-fill positive"
                            style={{ width: `${Math.min(100, dim.weight * 100)}%`, height: 4 }}
                          />
                        </div>
                        <span
                          className="text-xs font-mono-value text-text-tertiary"
                          style={{ minWidth: 42, textAlign: 'right' }}
                        >
                          {(dim.weight * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  ))}
                  {layer.children.length === 0 && (
                    <p className="text-xs text-text-tertiary py-2">暂无子维度数据</p>
                  )}
                </div>
              )}

              {(!layer.children || layer.children.length === 0) && (
                <div style={{ padding: '10px 14px' }}>
                  <p className="text-xs text-text-tertiary">该层无子维度权重数据</p>
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose} className="btn btn-secondary btn-sm">
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
