import type { SnapshotMetric, SnapshotPayload, SnapshotRow } from './utils';
import { cloudRows, cloudMetrics } from './SnapshotPanelCloud';
import {
  checkpointStatusRows,
  checkpointStatusMetrics,
  lifecycleRows,
  researchMemoryRows,
  researchMemoryMetrics,
  researchKnowledgeRows,
  researchKnowledgeMetrics,
  researchObservabilityRows,
  researchObservabilityMetrics,
  promptRunRows,
  sqliteIndexRows,
  sqliteIndexMetrics,
} from './SnapshotPanelLocal';
import { robustnessRows, robustnessMetrics } from './SnapshotPanelCompare';

export type SnapshotView =
  | 'cloud'
  | 'checkpoint_status'
  | 'lifecycle'
  | 'research_memory'
  | 'research_knowledge'
  | 'research_observability'
  | 'prompt_runs'
  | 'sqlite_indexes'
  | 'robustness';

export interface SnapshotConfig {
  title: string;
  subtitle: string;
  endpoint: string;
  empty: string;
  rows: (payload: SnapshotPayload) => SnapshotRow[];
  metrics?: (payload: SnapshotPayload, rows: SnapshotRow[]) => SnapshotMetric[];
}

export const SNAPSHOT_VIEWS: Record<SnapshotView, SnapshotConfig> = {
  cloud: {
    title: '云端数据',
    subtitle: '完整缓存的 Alpha 状态',
    endpoint: '/api/snapshot/cloud',
    empty: '暂无云端 Alpha 记录',
    rows: cloudRows,
    metrics: cloudMetrics,
  },
  checkpoint_status: {
    title: '续跑记录',
    subtitle: '上次进度、运行历史与收敛趋势',
    endpoint: '/api/checkpoint_status',
    empty: '暂无可续跑记录或运行历史',
    rows: checkpointStatusRows,
    metrics: checkpointStatusMetrics,
  },
  lifecycle: {
    title: '生命周期',
    subtitle: '审计跟踪',
    endpoint: '/api/lifecycle',
    empty: '暂无生命周期事件',
    rows: lifecycleRows,
  },
  research_memory: {
    title: '研究记忆',
    subtitle: '本地研究摘要',
    endpoint: '/api/research_memory?limit=5000&top_n=10',
    empty: '暂无研究记忆记录',
    rows: researchMemoryRows,
    metrics: researchMemoryMetrics,
  },
  research_knowledge: {
    title: '知识库',
    subtitle: '规则、发现、失败',
    endpoint: '/api/research_knowledge?limit=100&min_confidence=0',
    empty: '暂无知识记录',
    rows: researchKnowledgeRows,
    metrics: researchKnowledgeMetrics,
  },
  research_observability: {
    title: '可观测性',
    subtitle: '研究健康状态',
    endpoint: '/api/research_observability?limit=5000&top_n=10&include_cloud=true',
    empty: '暂无可观测性信号',
    rows: researchObservabilityRows,
    metrics: researchObservabilityMetrics,
  },
  prompt_runs: {
    title: '提示运行',
    subtitle: '提示账本',
    endpoint: '/api/prompt_runs?limit=100',
    empty: '暂无提示运行记录',
    rows: promptRunRows,
  },
  sqlite_indexes: {
    title: 'SQLite 索引',
    subtitle: '缓存健康状态',
    endpoint: '/api/sqlite_indexes?top_n=10',
    empty: '暂无 SQLite 索引记录',
    rows: sqliteIndexRows,
    metrics: sqliteIndexMetrics,
  },
  robustness: {
    title: '稳健性',
    subtitle: '防过拟合与滚动验证',
    endpoint: '/api/latest_result',
    empty: '暂无稳健性证据',
    rows: robustnessRows,
    metrics: robustnessMetrics,
  },
};
