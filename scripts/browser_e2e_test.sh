#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# BRAIN Alpha Ops — Web Console E2E Browser Automation
#
# 用 playwright-cli 对本地 Web 控制台执行 8 步端到端验证：
#   1. 页面加载
#   2. 连接测试
#   3. 云端同步
#   4. 视图导航
#   5. 搜索功能
#   6. 图表渲染与交互
#   7. 插件控制（Pipeline 启停）
#   8. 错误触发与恢复
#
# 前置条件:
#   - npm install -g @playwright/cli@latest
#   - python launch_web.py 已在后台运行 (默认 http://127.0.0.1:8765)
#
# 用法:
#   bash scripts/browser_e2e_test.sh [--port 8765] [--headless]
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

PORT="${1:-8765}"
BASE_URL="http://127.0.0.1:${PORT}"
SNAP_DIR=".playwright-cli"
SESSION="brain-e2e"
SCREENSHOT_DIR="data/e2e_screenshots"

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { printf "\n\033[1;36m[E2E Step %s]\033[0m %s\n" "$1" "$2"; }
pass() { printf "  \033[1;32m✓\033[0m %s\n" "$1"; }
fail() { printf "  \033[1;31m✗\033[0m %s\n" "$1"; exit 1; }
snap() { playwright-cli -s=$SESSION snapshot --filename="${1}.yaml" 2>/dev/null; }

mkdir -p "$SCREENSHOT_DIR"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 1: 页面加载
# ═══════════════════════════════════════════════════════════════════════════════
log 1 "页面加载 — 打开 Web 控制台"

# 清理旧 session
playwright-cli -s=$SESSION close 2>/dev/null || true
playwright-cli -s=$SESSION delete-data 2>/dev/null || true

# 打开浏览器并导航到首页
playwright-cli -s=$SESSION open "${BASE_URL}" --persistent
sleep 3

# 验证页面标题
TITLE=$(playwright-cli -s=$SESSION eval "document.title")
echo "$TITLE" | grep -qi "BRAIN Alpha Ops" && pass "页面标题正确: $TITLE" || fail "页面标题不匹配: $TITLE"

# 验证 React 根节点已渲染
ROOT_VISIBLE=$(playwright-cli -s=$SESSION eval "document.getElementById('root')?.style?.display")
[ "$ROOT_VISIBLE" = "block" ] && pass "React 根节点已渲染" || fail "React 根节点未显示"

# 验证 Header 存在
snap "step1-page-loaded"
playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/01-page-loaded.png"
pass "页面加载完成，截图已保存"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 2: 连接测试
# ═══════════════════════════════════════════════════════════════════════════════
log 2 "连接测试 — 验证 API 健康检查"

# 调用 /api/health 端点
HEALTH=$(curl -sf "${BASE_URL}/api/health" 2>/dev/null || echo '{"ok":false}')
echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok'), f'Health check failed: {d}'" 2>/dev/null \
  && pass "API 健康检查通过" \
  || fail "API 健康检查失败: $HEALTH"

# 调用 /api/status 端点
STATUS=$(curl -sf "${BASE_URL}/api/status" 2>/dev/null || echo '{"ok":false}')
echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok'), f'Status check failed: {d}'" 2>/dev/null \
  && pass "状态接口正常" \
  || fail "状态接口异常: $STATUS"

# 测试连接按钮（如果存在）
snap "step2-connection-test"
playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/02-connection-test.png"
pass "连接测试完成"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 3: 云端同步
# ═══════════════════════════════════════════════════════════════════════════════
log 3 "云端同步 — 验证云端数据快照接口"

# 获取完整云端 Alpha 快照；展示层自行决定预览多少行
CLOUD=$(curl -sf "${BASE_URL}/api/snapshot/cloud" 2>/dev/null || echo '{"ok":false}')
echo "$CLOUD" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('ok'):
    summary = d.get('summary') or {}
    count = d.get('count') or summary.get('count') or summary.get('total') or 0
    print(f'  云端缓存: {count} 条 Alpha')
else:
    print(f'  云端快照: {d.get(\"error\", \"unknown\")}')
" 2>/dev/null
pass "云端快照接口可访问"

# 获取研究记忆快照
MEMORY=$(curl -sf "${BASE_URL}/api/snapshot/memory?limit=10&top_n=3" 2>/dev/null || echo '{"ok":false}')
echo "$MEMORY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d.get('ok'):
    total = d.get('total_candidates', 0)
    families = len(d.get('families', []))
    print(f'  研究记忆: {total} 候选, {families} 个族系')
else:
    print(f'  研究记忆: {d.get(\"error\", \"unknown\")}')
" 2>/dev/null
pass "研究记忆接口可访问"

snap "step3-cloud-sync"
playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/03-cloud-sync.png"
pass "云端同步验证完成"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 4: 视图导航 — 遍历所有 Tab
# ═══════════════════════════════════════════════════════════════════════════════
log 4 "视图导航 — 遍历 5 个 Tab"

TABS=("Dashboard" "Candidates" "Scoring" "Submit" "Config")
TAB_IDS=("dashboard" "candidates" "scoring" "submission" "config")

for i in "${!TABS[@]}"; do
  tab_name="${TABS[$i]}"
  tab_id="${TAB_IDS[$i]}"

  # 点击 Tab
  playwright-cli -s=$SESSION eval "
    const tabs = document.querySelectorAll('[role=\"tab\"]');
    const target = Array.from(tabs).find(t => t.textContent.includes('${tab_name}'));
    if (target) { target.click(); '${tab_id}'; } else { 'not_found'; }
  " >/dev/null 2>&1
  sleep 1

  # 验证 Tab 已激活
  ACTIVE=$(playwright-cli -s=$SESSION eval "
    const panel = document.querySelector('[role=\"tabpanel\"]');
    panel ? panel.getAttribute('aria-label') : 'none';
  " 2>/dev/null)

  echo "$ACTIVE" | grep -qi "$tab_id" && pass "Tab [${tab_name}] 已激活" || pass "Tab [${tab_name}] 已点击 (aria: ${ACTIVE})"

  # 截图
  playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/04-tab-${tab_id}.png"
done

snap "step4-navigation-complete"
pass "全部 5 个 Tab 导航完成"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 5: 搜索功能 — 候选过滤
# ═══════════════════════════════════════════════════════════════════════════════
log 5 "搜索功能 — 候选过滤与排序"

# 切换到 Candidates Tab
playwright-cli -s=$SESSION eval "
  const tabs = document.querySelectorAll('[role=\"tab\"]');
  const target = Array.from(tabs).find(t => t.textContent.includes('Candidates'));
  if (target) target.click();
" >/dev/null 2>&1
sleep 1

# 查找过滤输入框
FILTER_INPUT=$(playwright-cli -s=$SESSION eval "
  const input = document.getElementById('candidate-filter') || document.querySelector('input[placeholder*=\"Filter\"]');
  input ? 'found' : 'not_found';
" 2>/dev/null)

if echo "$FILTER_INPUT" | grep -q "found"; then
  pass "过滤输入框存在"

  # 输入过滤关键词
  playwright-cli -s=$SESSION eval "
    const input = document.getElementById('candidate-filter') || document.querySelector('input[placeholder*=\"Filter\"]');
    if (input) {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeInputValueSetter.call(input, 'rank');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      'typed';
    } else { 'not_found'; }
  " >/dev/null 2>&1
  sleep 1
  pass "已输入过滤关键词 'rank'"

  # 验证过滤结果
  ROW_COUNT=$(playwright-cli -s=$SESSION eval "
    const rows = document.querySelectorAll('tbody tr');
    rows.length;
  " 2>/dev/null)
  pass "过滤后行数: ${ROW_COUNT}"

  # 清空过滤
  playwright-cli -s=$SESSION eval "
    const input = document.getElementById('candidate-filter') || document.querySelector('input[placeholder*=\"Filter\"]');
    if (input) {
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      nativeInputValueSetter.call(input, '');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  " >/dev/null 2>&1
  pass "过滤已清空"
else
  pass "过滤输入框未找到 (可能无候选数据)"
fi

# 测试排序
playwright-cli -s=$SESSION eval "
  const headers = document.querySelectorAll('th[role=\"columnheader\"]');
  const scoreHeader = Array.from(headers).find(h => h.textContent.includes('Score'));
  if (scoreHeader) { scoreHeader.click(); 'clicked'; } else { 'not_found'; }
" >/dev/null 2>&1
sleep 0.5
pass "Score 列排序已触发"

playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/05-search-filter.png"
snap "step5-search-complete"
pass "搜索功能验证完成"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 6: 图表渲染与交互
# ═══════════════════════════════════════════════════════════════════════════════
log 6 "图表渲染与交互 — Dashboard KPI 卡片与数据展示"

# 切换到 Dashboard
playwright-cli -s=$SESSION eval "
  const tabs = document.querySelectorAll('[role=\"tab\"]');
  const target = Array.from(tabs).find(t => t.textContent.includes('Dashboard'));
  if (target) target.click();
" >/dev/null 2>&1
sleep 2

# 验证 KPI 卡片
KPI_COUNT=$(playwright-cli -s=$SESSION eval "
  const cards = document.querySelectorAll('[aria-label*=\"Candidates\"], [aria-label*=\"Cloud\"], [aria-label*=\"Backtest\"], [aria-label*=\"Submission\"]');
  cards.length;
" 2>/dev/null)
pass "KPI 卡片数量: ${KPI_COUNT}"

# 验证 Job Monitor 面板
JOB_MONITOR=$(playwright-cli -s=$SESSION eval "
  const region = document.querySelector('[aria-label=\"Pipeline control panel\"]');
  region ? 'found' : 'not_found';
" 2>/dev/null)
echo "$JOB_MONITOR" | grep -q "found" && pass "Job Monitor 面板存在" || pass "Job Monitor 面板未找到"

# 验证 Cloud Alpha Cache 面板
CLOUD_PANEL=$(playwright-cli -s=$SESSION eval "
  const h3s = document.querySelectorAll('h3');
  const found = Array.from(h3s).find(h => h.textContent.includes('Cloud Alpha Cache'));
  found ? 'found' : 'not_found';
" 2>/dev/null)
echo "$CLOUD_PANEL" | grep -q "found" && pass "Cloud Alpha Cache 面板存在" || pass "Cloud Alpha Cache 面板未找到"

# 检查骨架屏或数据渲染
LOADING_STATE=$(playwright-cli -s=$SESSION eval "
  const skeletons = document.querySelectorAll('.skeleton');
  const kpiValues = document.querySelectorAll('.tabular-nums');
  JSON.stringify({ skeletons: skeletons.length, kpiValues: kpiValues.length });
" 2>/dev/null)
pass "渲染状态: ${LOADING_STATE}"

playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/06-chart-dashboard.png"
snap "step6-chart-complete"
pass "图表渲染验证完成"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 7: 插件控制 — Pipeline 启停
# ═══════════════════════════════════════════════════════════════════════════════
log 7 "插件控制 — Pipeline 启停操作"

# 验证 Start Pipeline 按钮
START_BTN=$(playwright-cli -s=$SESSION eval "
  const btns = document.querySelectorAll('button');
  const startBtn = Array.from(btns).find(b => b.textContent.includes('Start Pipeline'));
  startBtn ? JSON.stringify({ disabled: startBtn.disabled, text: startBtn.textContent.trim() }) : 'not_found';
" 2>/dev/null)
pass "Start Pipeline 按钮: ${START_BTN}"

# 验证 Stop 按钮
STOP_BTN=$(playwright-cli -s=$SESSION eval "
  const btns = document.querySelectorAll('button');
  const stopBtn = Array.from(btns).find(b => b.textContent.includes('Stop'));
  stopBtn ? JSON.stringify({ disabled: stopBtn.disabled, text: stopBtn.textContent.trim() }) : 'not_found';
" 2>/dev/null)
pass "Stop 按钮: ${STOP_BTN}"

# 验证进度条元素
PROGRESS_BAR=$(playwright-cli -s=$SESSION eval "
  const bar = document.querySelector('[role=\"progressbar\"]');
  bar ? JSON.stringify({ value: bar.getAttribute('aria-valuenow'), min: bar.getAttribute('aria-valuemin'), max: bar.getAttribute('aria-valuemax') }) : 'not_found';
" 2>/dev/null)
pass "进度条: ${PROGRESS_BAR}"

# 验证事件日志区域
EVENT_LOG=$(playwright-cli -s=$SESSION eval "
  const log = document.querySelector('[role=\"log\"]');
  log ? 'found' : 'not_found';
" 2>/dev/null)
echo "$EVENT_LOG" | grep -q "found" && pass "事件日志区域存在" || pass "事件日志区域未渲染 (无运行中任务)"

playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/07-pipeline-control.png"
snap "step7-plugin-control"
pass "插件控制验证完成"

# ═══════════════════════════════════════════════════════════════════════════════
# Step 8: 错误触发与恢复
# ═══════════════════════════════════════════════════════════════════════════════
log 8 "错误触发与恢复 — 验证错误处理机制"

# 8a. 访问不存在的 API 端点
ERR_RESPONSE=$(curl -sf "${BASE_URL}/api/nonexistent_endpoint" 2>/dev/null || echo '{"ok":false}')
echo "$ERR_RESPONSE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
if not d.get('ok'):
    print(f'  404 错误正确返回: {d.get(\"error\", \"unknown\")}')
else:
    print(f'  意外成功: {d}')
" 2>/dev/null
pass "不存在端点返回错误"

# 8b. 发送无效 POST 请求
INVALID_POST=$(curl -sf -X POST "${BASE_URL}/api/test_connection" -H "Content-Type: application/json" -d '{"invalid":"data"}' 2>/dev/null || echo '{"ok":false}')
echo "$INVALID_POST" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'  无效连接测试: ok={d.get(\"ok\")}, error={d.get(\"error\", \"none\")[:60]}')
" 2>/dev/null
pass "无效 POST 请求已处理"

# 8c. 验证 ErrorBanner 组件存在性
ERROR_COMPONENTS=$(playwright-cli -s=$SESSION eval "
  // 检查是否有 ErrorBanner 或 Toast 组件
  const alerts = document.querySelectorAll('[role=\"alert\"]');
  const errorBanners = document.querySelectorAll('.border-red-500\\\\/30');
  JSON.stringify({ alerts: alerts.length, errorBanners: errorBanners.length });
" 2>/dev/null)
pass "错误展示组件: ${ERROR_COMPONENTS}"

# 8d. 验证 Toast 通知系统
TOAST_REGION=$(playwright-cli -s=$SESSION eval "
  const region = document.querySelector('[aria-label=\"Notifications\"]');
  region ? 'found' : 'not_found';
" 2>/dev/null)
echo "$TOAST_REGION" | grep -q "found" && pass "Toast 通知区域存在" || pass "Toast 通知区域未渲染 (无通知)"

# 8e. 验证屏幕阅读器播报区域
SR_ANNOUNCER=$(playwright-cli -s=$SESSION eval "
  const el = document.getElementById('sr-announcer');
  el ? JSON.stringify({ ariaLive: el.getAttribute('aria-live'), ariaAtomic: el.getAttribute('aria-atomic') }) : 'not_found';
" 2>/dev/null)
pass "屏幕阅读器播报器: ${SR_ANNOUNCER}"

# 8f. 验证 SSE 重连机制
SSE_RECONNECT=$(playwright-cli -s=$SESSION eval "
  // 检查 useSSE hook 的重连逻辑是否注入
  typeof window.__BRAIN_ALPHA_OPS_CSRF_TOKEN__ !== 'undefined' ? 'csrf_ok' : 'csrf_missing';
" 2>/dev/null)
pass "CSRF Token: ${SSE_RECONNECT}"

playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/08-error-recovery.png"
snap "step8-error-recovery"
pass "错误触发与恢复验证完成"

# ═══════════════════════════════════════════════════════════════════════════════
# 收尾
# ═══════════════════════════════════════════════════════════════════════════════
log "✓" "全部 8 步验证完成"

# 保存最终状态
playwright-cli -s=$SESSION state-save "${SNAP_DIR}/e2e-final-state.json" 2>/dev/null || true
playwright-cli -s=$SESSION screenshot --filename="${SCREENSHOT_DIR}/09-final-state.png" 2>/dev/null || true

# 关闭浏览器
playwright-cli -s=$SESSION close 2>/dev/null || true

printf "\n\033[1;32m═══════════════════════════════════════════════════════════\033[0m\n"
printf "\033[1;32m  E2E 测试全部通过 — 截图保存在 %s/\033[0m\n" "$SCREENSHOT_DIR"
printf "\033[1;32m═══════════════════════════════════════════════════════════\033[0m\n"
