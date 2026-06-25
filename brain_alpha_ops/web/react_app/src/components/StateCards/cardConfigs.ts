import type { CardViewId } from '@/types';

export interface CardConfig {
  id: CardViewId;
  title: string;
  description: string;
  icon: string;
  color: string;
  action: string;
}

export const CARD_CONFIGS: CardConfig[] = [
  {
    id: 'official_operations',
    title: '官方操作',
    description: '按钮驱动的官方上下文、合规与阻断复核',
    icon: '00',
    color: 'from-emerald-500 to-slate-700',
    action: '打开操作',
  },
  {
    id: 'dashboard',
    title: '运行总览',
    description: '流水线状态、进度与运行快照',
    icon: '01',
    color: 'from-slate-500 to-slate-700',
    action: '查看总览',
  },
  {
    id: 'candidates',
    title: '候选管理',
    description: '生成、查看、筛选候选Alpha',
    icon: '02',
    color: 'from-brand-500 to-brand-700',
    action: '管理候选',
  },
  {
    id: 'official_backtests',
    title: '回测监控',
    description: '官方回测槽位状态监控',
    icon: '03',
    color: 'from-blue-500 to-blue-700',
    action: '监控回测',
  },
  {
    id: 'scoring',
    title: '科学评分',
    description: '官方指标、归因与门禁评分',
    icon: '04',
    color: 'from-violet-500 to-violet-700',
    action: '查看评分',
  },
  {
    id: 'quality_check',
    title: '质量门禁',
    description: '达标检查与质量评估',
    icon: '05',
    color: 'from-success to-emerald-700',
    action: '检查质量',
  },
  {
    id: 'submission_confirm',
    title: '阻断复核',
    description: '提交前阻断原因与候选审计',
    icon: '06',
    color: 'from-warning to-amber-700',
    action: '查看阻断',
  },
  {
    id: 'checkpoint_status',
    title: '续跑记录',
    description: '上次进度与运行历史回溯',
    icon: '08',
    color: 'from-teal-500 to-emerald-700',
    action: '查看历史',
  },
  {
    id: 'config',
    title: '系统配置',
    description: '参数、阈值与运行预算',
    icon: '09',
    color: 'from-indigo-500 to-indigo-700',
    action: '系统设置',
  },
  {
    id: 'cloud',
    title: '云端快照',
    description: '云端Alpha缓存与同步状态',
    icon: '10',
    color: 'from-cyan-500 to-blue-700',
    action: '查看快照',
  },
];
