# BRAIN Alpha Ops — 部署指南

> 最后更新: 2026-06-08

## 环境要求

| 工具 | 版本 | 用途 |
|------|------|------|
| Node.js | ≥20 | 前端构建 |
| Python | ≥3.11 | 后端服务 |
| npm | ≥9 | 包管理 |

## 快速开始

### 1. 安装依赖

```bash
# 前端
cd brain_alpha_ops/web/react_app
npm ci

# 后端（项目根目录）
cd /path/to/BRAIN-Alpha
pip install -e .
```

### 2. 启动开发环境

```bash
# 终端 1: 启动后端（端口 8765）
python -m brain_alpha_ops.web

# 终端 2: 启动前端开发服务器（端口 3000）
cd brain_alpha_ops/web/react_app
npm run dev
```

访问 `http://localhost:3000`

### 3. 生产构建

```bash
cd brain_alpha_ops/web/react_app
npm run build    # 输出到 dist/
```

后端会自动服务 `dist/` 目录中的静态文件。

## 验证

```bash
# 前端类型检查
cd brain_alpha_ops/web/react_app
npx tsc --noEmit

# 前端测试
npx vitest run

# 前端构建
npx vite build

# 后端测试（项目根目录）
pytest tests/ -v
```

## 配置

### 凭证

首次使用需要在 Dashboard 的"凭证与连接"面板填写 BRAIN 账户邮箱和密码，或 Token。凭证仅保存在浏览器内存中，不写入文件。

### 为非提交模式

系统默认运行在"非提交"模式 (`auto_submit: false`)，所有操作仅为本地验证，不会向 BRAIN 官方提交 Alpha。

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| `npm ci` 失败 | 删除 `node_modules/` 和 `package-lock.json`，重新运行 |
| 后端无法启动 | 检查 Python 依赖 `pip install -e .` |
| 前端代理错误 | 确认后端在 8765 端口运行中 |
| 构建后白屏 | 检查 `dist/index.html` 的 script 路径是否指向了正确的 assets/ |
