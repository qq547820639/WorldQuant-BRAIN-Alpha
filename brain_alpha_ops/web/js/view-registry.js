// brain_alpha_ops/web/js/view-registry.js
// Central registry for table views, navigation groups, labels, and hints.

(function () {
  'use strict';

  var WORKFLOW_VIEWS = [
    'candidates', 'pending_backtest', 'running_backtest', 'backtest_rework',
    'passed', 'submittable', 'submitted', 'failed',
  ];
  var DATA_VIEWS = ['cloud', 'lifecycle'];
  var RESEARCH_VIEWS = [
    'research_memory', 'research_knowledge', 'research_observability',
    'prompt_runs', 'sqlite_indexes', 'robustness',
  ];

  var ViewRegistry = {
    VIEW_ORDER: WORKFLOW_VIEWS.concat(DATA_VIEWS, RESEARCH_VIEWS),
    WORKFLOW_VIEWS: WORKFLOW_VIEWS,
    DATA_VIEWS: DATA_VIEWS,
    RESEARCH_VIEWS: RESEARCH_VIEWS,
    VIEW_GROUPS: [
      { label: '生产流程', hint: '从候选到提交', views: WORKFLOW_VIEWS },
      { label: '数据审计', hint: '云端与生命周期', views: DATA_VIEWS },
      { label: '研究工具', hint: '记忆、知识与验证', views: RESEARCH_VIEWS },
    ],
    VIEW_TITLES: {
      candidates: '候选池',
      pending_backtest: '等待回测',
      running_backtest: '回测中',
      backtest_rework: '二次融合',
      passed: '达标',
      submittable: '可提交',
      submitted: '已提交',
      failed: '不达标',
      cloud: '云端数据',
      lifecycle: '生命周期',
      research_memory: '研究记忆',
      research_observability: '可观测性',
      research_knowledge: '知识库',
      prompt_runs: '提示账本',
      sqlite_indexes: 'SQLite 索引',
      robustness: '稳健性',
    },
    VIEW_ICONS: {
      candidates: '01', pending_backtest: '02', running_backtest: '03',
      backtest_rework: '04', passed: '05', submittable: '06',
      submitted: '07', failed: '08', cloud: 'CL', lifecycle: 'LC',
      research_memory: 'RM', research_observability: 'OB',
      research_knowledge: 'KB', prompt_runs: 'PR', sqlite_indexes: 'DB', robustness: 'RV',
    },
    VIEW_HINTS: {
      candidates: '按排序分降序展示核心候选池。',
      pending_backtest: '等待回测的 Alpha 按排队顺序展示。',
      running_backtest: '正在等待官方回测结果返回。',
      backtest_rework: '回测失败或需要二次融合的 Alpha。',
      passed: '达标 Alpha 可批量检查后提交。',
      submittable: '检查通过且仍在有效期内的 Alpha，可直接提交。',
      submitted: '已提交和云端已提交记录。',
      failed: '不达标、拒绝和阻断记录。',
      cloud: '云端快照和缓存统计。',
      lifecycle: '关键生命周期事件追踪。',
      research_memory: '本地 JSONL 研究记忆。',
      research_knowledge: '结构化规则和发现。',
      research_observability: '研究链路可观测快照。',
      prompt_runs: 'Prompt 运行账本。',
      sqlite_indexes: 'SQLite 缓存状态。',
      robustness: '反过拟合和滚动验证状态。',
    },
  };

  window.ViewRegistry = ViewRegistry;
})();
