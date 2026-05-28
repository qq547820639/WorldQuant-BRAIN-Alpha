# brain-alpha-ops

`brain-alpha-ops` 是 WorldQuant BRAIN Alpha 的本地操作手册式工作台。它把账号连接、云端同步、候选生成、结果查看、达标检查和提交前确认放在同一个本地页面里，适合日常研究和生产流程使用。

## 1. 产品简介与核心功能

### 1.1 它能做什么

- 在本地 Web 页面中连接 BRAIN 账号。
- 同步云端 Alpha 和本地研究数据。
- 生成和查看候选 Alpha。
- 检查候选是否满足继续处理的条件。
- 在提交前查看风险原因和阻断信息。
- 使用本地配置文件控制运行环境、端口和研究参数。

### 1.2 适合什么场景

- 想在一台电脑上集中管理 BRAIN Alpha 流程。
- 想先看结果、再决定是否继续处理提交。
- 想把常用配置保存成 `run_config.json`，以后直接复用。

### 1.3 关键默认行为

- 默认只绑定本机 `127.0.0.1`。
- 默认不会自动提交 Alpha。
- 默认使用生产环境的 BRAIN API。
- 凭据推荐通过环境变量或 Web 页面本地填写，不要写进代码或文档。

## 2. 安装与配置

### 2.1 安装环境

需要准备：

1. Python 3.10 或更高版本。
2. 可访问的 WorldQuant BRAIN 账号。
3. 一台能打开本地浏览器的电脑。

安装项目：

```bash
git clone <your-repository-url>
cd WorldQuant-BRAIN-Alpha

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[test]"
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

### 2.2 凭据配置

推荐使用环境变量：

```bash
export BRAIN_USERNAME="your_email_here"
export BRAIN_PASSWORD="your_password_here"
# 如果使用 token，就填这一项
export BRAIN_TOKEN="your_token"
```

Windows PowerShell：

```powershell
$env:BRAIN_USERNAME="your_email_here"
$env:BRAIN_PASSWORD="your_password_here"
# 如果使用 token，就填这一项
$env:BRAIN_TOKEN="your_token"
```

也可以在 Web 页面里临时输入账号信息。不要把真实账号、密码或 token 写进 README、配置文件、测试文件、截图或提交记录。

### 2.3 配置文件

默认配置文件是 [config/run_config.json](config/run_config.json)。常见字段如下：

| 字段 | 说明 |
|---|---|
| `environment` | 只使用 `production` |
| `auto_submit` | 建议保持 `false` |
| `credentials.*_env` | 对应的环境变量名 |
| `web.host` / `web.port` | 本地 Web 控制台地址 |
| `ops.storage_dir` | 运行数据和研究数据目录 |
| `ops.settings` | BRAIN 回测设置 |
| `ops.budget` | 运行节奏和候选预算 |
| `ops.thresholds` | 本地质量和官方门槛 |
| `ops.submission_policy` | 自动提交限额和保护规则 |
| `ops.official_api` | BRAIN API 路径、超时和缓存设置 |

配置文件支持只写需要覆盖的部分，加载时会先合并默认值，再做完整校验。

### 2.4 第一次运行前建议检查

1. 确认 `config/run_config.json` 存在。
2. 确认 `web.port` 没有被别的程序占用。
3. 确认 `BRAIN_USERNAME` 和 `BRAIN_PASSWORD` 或 `BRAIN_TOKEN` 已设置。
4. 确认 `auto_submit` 保持关闭。

## 3. 核心功能使用指南

### 3.1 启动 Web 控制台

```bash
python3 launch_web.py
```

默认地址：

```text
http://127.0.0.1:8765
```

如果端口被占用，修改 [config/run_config.json](config/run_config.json) 里的 `web.port`，然后重新启动。

### 3.2 典型操作流程一：先连接，再同步，再搜索

1. 打开 Web 控制台。
2. 在“连接与身份”区域输入账号信息，或先在系统环境变量里设置凭据。
3. 确认运行环境是 production。
4. 点击“同步云端数据”。
5. 等待同步完成。
6. 点击“开始生产搜索”。
7. 在候选列表里查看排序分、状态和风险原因。

### 3.3 典型操作流程二：查看候选并做达标检查

1. 在候选池中找到你要继续处理的 Alpha。
2. 切到“表格”视图，优先看“状态”和“风险 / 原因”列。
3. 确认该条目已经进入达标相关状态。
4. 点击“检查”按钮。
5. 等待检查完成。
6. 查看通过数、失败原因和阻断信息。

### 3.4 典型操作流程三：处理提交队列

1. 确认候选已经通过检查。
2. 切到“可提交”或“提交队列”视图。
3. 勾选要处理的 Alpha。
4. 再次检查“风险 / 原因”列。
5. 点击“提交勾选”。
6. 如果按钮不可点，先查看页面提示，再处理阻断原因。

### 3.5 典型操作流程四：只做查看，不提交

1. 打开 Web 控制台。
2. 同步云端数据。
3. 查看候选列表和图表。
4. 只做检查，不打开自动提交。
5. 如果只是复盘，可以打开“研究观察”或“诊断”相关页面查看状态。

### 3.6 命令行用法

配置校验：

```bash
python3 -m brain_alpha_ops.cli validate-config --config config/run_config.json
```

运行生产管线：

```bash
python3 -m brain_alpha_ops.cli run --config config/run_config.json
```

查看只读信息：

```bash
python3 -m brain_alpha_ops.cli memory-summary --config config/run_config.json
python3 -m brain_alpha_ops.cli research-observability --config config/run_config.json
python3 -m brain_alpha_ops.cli diagnose --config config/run_config.json --json
python3 -m brain_alpha_ops.cli release-gate --config config/run_config.json --json
```

## 4. 常见问题排查与解决方案

### 4.1 Web 页面打不开

可能原因：

1. `launch_web.py` 没有运行。
2. `web.port` 被占用。
3. 浏览器打开的不是 `http://127.0.0.1:8765`。

处理步骤：

1. 重新启动 `python3 launch_web.py`。
2. 修改 `config/run_config.json` 中的 `web.port`。
3. 再次打开页面地址。

### 4.2 页面一直显示未连接

可能原因：

1. 账号或密码输入错误。
2. 环境变量没有设置好。
3. 使用了过期 token。
4. 网络暂时不可用。

处理步骤：

1. 重新检查 `BRAIN_USERNAME`、`BRAIN_PASSWORD` 或 `BRAIN_TOKEN`。
2. 回到“连接与身份”区域重新填写。
3. 再点击“同步云端数据”。

### 4.3 同步云端失败

可能原因：

1. 凭据错误。
2. 网络不稳定。
3. BRAIN 服务暂时不可用。
4. 请求太频繁。

处理步骤：

1. 先确认凭据无误。
2. 等几分钟后再试。
3. 保持默认同步范围，不要反复快速点击。

### 4.4 没有候选生成出来

可能原因：

1. 还没有成功同步云端数据。
2. 当前参数太严格。
3. 生产搜索还在启动。

处理步骤：

1. 先同步云端数据。
2. 保持默认参数。
3. 再启动生产搜索。

### 4.5 “检查”或“提交勾选”按钮不可点

可能原因：

1. 没有达标候选。
2. 候选还没有通过检查。
3. 另一个任务正在运行。
4. 页面提示有阻断风险。

处理步骤：

1. 查看“风险 / 原因”列。
2. 先完成检查，再考虑提交。
3. 等当前任务结束后再操作。

### 4.6 配置校验失败

可能原因：

1. `run_config.json` 字段写错。
2. 端口或路径值不合法。
3. 片段配置缺少应有的类型和值。

处理步骤：

1. 运行：

```bash
python3 -m brain_alpha_ops.cli validate-config --config config/run_config.json
```

2. 根据输出修正对应字段。
3. 重新启动 Web 控制台或重新运行命令。

### 4.7 提示自动提交相关风险

处理建议：

1. 保持 `auto_submit` 关闭。
2. 先确认云端同步结果。
3. 再确认检查结果。
4. 只处理你确定要提交的条目。

## 安全提醒

- 不要把真实账号、密码、token、cookie 写进 README、日志或提交记录。
- 不要把命令行凭据长期当成默认用法。
- 如果怀疑凭据泄露，先更换密码或 token。
- `data/e2e_screenshots/` 已被忽略，不要把截图里的敏感信息重新提交。
