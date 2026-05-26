# BRAIN Alpha Ops

欢迎使用 BRAIN Alpha Ops。它是一个帮助你在本地管理 WorldQuant BRAIN Alpha 研究流程的小工具：从生成想法、筛选候选、查看运行结果，到打开本地网页控制台，都可以在一个项目里完成。

你不需要一开始就理解所有内部细节。按下面的步骤走，先把项目跑起来，再逐步使用更多功能。

## 项目简介

BRAIN Alpha Ops 主要解决四件事：

1. 帮你生成和整理 Alpha 候选。
2. 在本地先做基础检查，减少无效尝试。
3. 连接 WorldQuant BRAIN 官方接口，执行必要的检查、回测和同步。
4. 提供一个本地网页控制台，让你更直观地查看进度、结果和问题。

项目默认不会自动提交 Alpha。提交相关操作需要满足配置、检查和安全条件后才会执行。

## 快速入门

### 1. 准备环境

你需要：

- Python 3.10 或更高版本
- 一个 WorldQuant BRAIN 账号
- Windows PowerShell，推荐在 Windows 上使用本项目

### 2. 安装项目

打开 PowerShell，进入你想保存项目的目录，然后执行：

```powershell
git clone https://github.com/qq547820639/WorldQuant-BRAIN-Alpha.git
cd WorldQuant-BRAIN-Alpha

python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -e .
```

如果你还要运行测试或参与开发，可以安装开发依赖：

```powershell
pip install -e ".[test,dev]"
```

### 3. 设置 BRAIN 登录信息

请不要把账号密码写进代码或配置文件。运行前在 PowerShell 里设置环境变量：

```powershell
$env:BRAIN_USERNAME = "your@email.com"
$env:BRAIN_PASSWORD = "your_password"
```

如果你使用 token，也可以设置：

```powershell
$env:BRAIN_TOKEN = "your_token"
```

### 4. 检查配置

先确认项目配置可以正常读取：

```powershell
python -m brain_alpha_ops.cli validate-config --config config/run_config.json
```

### 5. 启动本地网页控制台

```powershell
python launch_web.py
```

启动后在浏览器打开：

```text
http://127.0.0.1:8765
```

如果页面能打开，你就可以开始使用项目了。

## 常用操作

### 刷新官方字段和数据

第一次使用，或很久没有更新过官方数据时，可以运行：

```powershell
python fetch_official_context.py --config config/run_config.json --json
```

### 运行一轮 Alpha 研究

```powershell
python -m brain_alpha_ops.cli run --config config/run_config.json --cycles 1 --candidates 20
```

这会生成一批候选，并按配置进行本地筛选和记录。

### 使用带进度提示的模式

```powershell
python -m brain_alpha_ops.cli guided-run --config config/run_config.json
```

这个模式更适合新手，因为它会记录阶段进度和中间结果。

### 运行项目自检

```powershell
python scripts/quality_gate.py --skip-tests --json
```

如果你想运行完整测试：

```powershell
pytest tests/ -q --basetemp .pytest_tmp
```

## 核心功能说明

### 本地网页控制台

网页控制台是最推荐的日常入口。你可以在里面查看：

- 当前候选 Alpha
- 等待回测的候选
- 正在运行的任务
- 已通过筛选的结果
- 可提交的 Alpha
- 已提交记录
- 云端同步数据
- 运行历史和诊断结果

默认情况下，网页控制台只在你的电脑本机开放。

### Alpha 候选生成

项目可以根据配置和历史结果生成 Alpha 候选。你可以先让系统生成一批，再从结果里挑选更有希望的方向继续研究。

### 本地筛选

在调用官方接口前，项目会先做一些本地检查，比如表达式是否合理、是否重复、是否明显不符合配置门槛。这样可以减少浪费时间的官方调用。

### 官方检查与回测

配置好 BRAIN 登录信息后，项目可以连接官方接口，执行官方 Check、Simulation、云端 Alpha 同步等操作。

### 提交保护

项目默认关闭自动提交。即使开启提交相关功能，也会先检查相似度、质量门槛、官方状态和提交策略，尽量避免误提交。

### Windows EXE 打包

如果你想把项目打包成 Windows 可执行文件，可以运行：

```powershell
.\scripts\build_windows.ps1
```

打包结果会放在：

```text
dist\BrainAlphaOps.exe
```

打包后建议真实启动一次，确认页面和健康接口都能访问。

## 常见问题排查

### 页面打不开怎么办？

先确认启动命令还在运行：

```powershell
python launch_web.py
```

然后访问：

```text
http://127.0.0.1:8765
```

如果端口被占用，可以在配置文件 [config/run_config.json](config/run_config.json) 中修改 `web.port`。

### 提示缺少 BRAIN 凭据怎么办？

说明项目没有读到账号信息。重新设置环境变量：

```powershell
$env:BRAIN_USERNAME = "your@email.com"
$env:BRAIN_PASSWORD = "your_password"
```

设置后，在同一个 PowerShell 窗口里重新运行命令。

### 运行测试时失败怎么办？

先运行更小范围的检查：

```powershell
python scripts/quality_gate.py --skip-tests --json
```

如果是测试临时文件导致的问题，可以换一个临时目录：

```powershell
pytest tests/ -q --basetemp .pytest_tmp_retry
```

### 官方数据过期怎么办？

刷新官方上下文：

```powershell
python fetch_official_context.py --config config/run_config.json --json
```

如果仍然失败，通常是账号、网络或官方接口限流问题。稍后重试，并确认 BRAIN 登录信息正确。

### 为什么本地通过不代表可以提交？

本地通过只说明候选没有明显问题。真正提交前，还需要官方 Check、回测状态、相似度、质量门槛和账号状态都满足要求。

### README 里的命令应该在哪运行？

除非特别说明，所有命令都在项目根目录运行，也就是包含 [config](config)、[brain_alpha_ops](brain_alpha_ops)、[scripts](scripts) 的目录。

## 安全提醒

- 不要把 BRAIN 账号、密码或 token 写进 README、配置文件、日志或提交记录。
- 不确定时，先关闭自动提交。
- 打包后的 EXE 也要单独启动验证，不要只依赖源码测试结果。
- 如果怀疑凭据泄露，请立即修改 BRAIN 密码或重置 token。

## 下一步建议

第一次使用时，推荐顺序是：

1. 安装项目。
2. 设置 BRAIN 登录信息。
3. 运行配置检查。
4. 打开本地网页控制台。
5. 先运行一轮小规模研究。
6. 查看结果和诊断信息，再逐步扩大候选数量。
