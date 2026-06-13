# BRAIN-Alpha Ops v0.3.0 — 部署指南 (Deployment Guide)

> **版本**: 0.3.0
> **日期**: 2026-06-13
> **目标读者**: 运维 / 部署工程师
> **目标环境**: macOS 12+ / Ubuntu 20.04+ / Windows 10+

---

## 目录

1. [部署模式选择](#1-部署模式选择)
2. [系统要求](#2-系统要求)
3. [源码部署](#3-源码部署)
4. [PyInstaller 打包部署](#4-pyinstaller-打包部署)
5. [远程访问部署](#5-远程访问部署)
6. [生产环境加固](#6-生产环境加固)
7. [升级与回滚](#7-升级与回滚)
8. [监控与告警](#8-监控与告警)
9. [故障排查](#9-故障排查)

---

## 1. 部署模式选择

### 1.1 三种部署模式对比

| 模式 | 优点 | 缺点 | 适用 |
|---|---|---|---|
| **A. 源码直跑** | 易调试, 易升级, 体积小 | 需 Python 3.10+ 环境 | 研发 / 自定义 |
| **B. PyInstaller onefile** | 单文件分发, 跨平台 | 体积大 (50MB+), 启动稍慢 (3-5s) | 生产单机 |
| **C. Docker** (未提供官方镜像) | 环境隔离, 易扩缩 | 需写 Dockerfile, 文件 IO 性能损耗 | 多用户 / 服务化 |

**推荐**:
- 个人研究机 → 模式 A
- 公司内部分发 → 模式 B
- 云端服务化 → 模式 C (PAN 自定义 Dockerfile)

### 1.2 单机 vs 多机

**当前版本设计为单机**:
- 数据存在 `data/` 本地目录
- 凭据只读本机 env
- 任务调度单进程
- **不支持**多机负载均衡 / 主备

如需多机: 自行实现 `data/` 目录 NFS 共享 + Leader 选举。

---

## 2. 系统要求

### 2.1 最低配置

| 资源 | 最低 | 推荐 |
|---|---|---|
| OS | macOS 12 / Win 10 / Ubuntu 20.04 | macOS 14 / Win 11 / Ubuntu 22.04 |
| CPU | 2 核 | 4 核+ |
| 内存 | 1 GB | 4 GB+ |
| 磁盘 | 500 MB (源码) + 1 GB (运行时数据) | 5 GB+ |
| 网络 | 出向 HTTPS api.worldquantbrain.com 稳定 | < 200ms 延迟 |
| 浏览器 | Chrome 90 / Edge 90 | Chrome 124+ |

### 2.2 软件依赖

| 软件 | 版本 | 用途 |
|---|---|---|
| Python | 3.10 - 3.12 | 核心运行时 |
| pip | 22+ | 依赖管理 |
| Node.js | 18+ (仅源码部署) | 前端构建 |
| npm | 9+ (仅源码部署) | 前端依赖 |
| PyInstaller | 6+ (仅打包部署) | 打包 |

### 2.3 网络要求

- **出向**: `https://api.worldquantbrain.com/` (443, HTTPS)
- **可选**: LLM provider endpoint (如 `api.openai.com`, `api.anthropic.com` 等)
- **入向 (可选)**: 8765 端口, 默认仅本地

---

## 3. 源码部署

### 3.1 准备部署目录

```bash
DEPLOY_DIR=/opt/brain-alpha-ops  # 或 D:\brain-alpha-ops (Windows)
mkdir -p $DEPLOY_DIR
cd $DEPLOY_DIR

# 拷贝项目 (PAN 自行决定传输方式)
# 例: scp /Volumes/Extra/CodeProj/WorldQuant-BRAIN-Alpha/ user@host:$DEPLOY_DIR/
```

### 3.2 安装 Python 依赖

```bash
python3.10+ -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.lock
```

### 3.3 安装前端依赖并构建

```bash
cd brain_alpha_ops/web/react_app
npm ci
npm run build   # 输出到 dist/
cd ../../../
```

### 3.4 配置 BRAIN 凭据 (推荐环境变量方式)

```bash
# 创建 systemd override / launchd plist 时注入:
export BRAIN_USERNAME="your@email.com"
export BRAIN_PASSWORD="your_password"
# 或
export BRAIN_TOKEN="your_brain_token"
```

> ⚠️ **不要**把凭据写入配置文件或脚本。环境变量是首选。

### 3.5 配置预设 (可选)

```bash
# 选择运行模式
# (生产推荐) 默认 balanced
# (保守研究) 改 config/run_config.json 中的 scoring.min_sharpe
```

### 3.6 启动

#### 方式 1: 前台 (调试)

```bash
source .venv/bin/activate
python launch_web.py
# 访问 http://127.0.0.1:8765/
```

#### 方式 2: 后台 (nohup)

```bash
source .venv/bin/activate
nohup python launch_web.py --no-browser > /var/log/brain-alpha-ops.log 2>&1 &
echo $! > /var/run/brain-alpha-ops.pid
```

#### 方式 3: systemd (推荐 Linux 生产)

`/etc/systemd/system/brain-alpha-ops.service`:

```ini
[Unit]
Description=BRAIN Alpha Ops Web Console
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=brain
Group=brain
WorkingDirectory=/opt/brain-alpha-ops
EnvironmentFile=/opt/brain-alpha-ops/.env
ExecStart=/opt/brain-alpha-ops/.venv/bin/python launch_web.py --no-browser
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/brain-alpha-ops.log
StandardError=append:/var/log/brain-alpha-ops.log

[Install]
WantedBy=multi-user.target
```

启动:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now brain-alpha-ops
sudo systemctl status brain-alpha-ops
```

#### 方式 4: launchd (macOS)

`~/Library/LaunchAgents/com.brain.alpha.ops.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.brain.alpha.ops</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/brain-alpha-ops/.venv/bin/python</string>
        <string>/opt/brain-alpha-ops/launch_web.py</string>
        <string>--no-browser</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/opt/brain-alpha-ops</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>BRAIN_USERNAME</key>
        <string>your@email.com</string>
        <key>BRAIN_PASSWORD</key>
        <string>your_password</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/brain-alpha-ops.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/brain-alpha-ops.log</string>
</dict>
</plist>
```

启动:

```bash
launchctl load ~/Library/LaunchAgents/com.brain.alpha.ops.plist
launchctl list | grep brain.alpha
```

#### 方式 5: Windows Service (NSSM)

```cmd
# 下载 NSSM: https://nssm.cc/download
nssm install BrainAlphaOps "D:\brain-alpha-ops\.venv\python.exe" "D:\brain-alpha-ops\launch_web.py --no-browser"
nssm set BrainAlphaOps AppDirectory D:\brain-alpha-ops
nssm set BrainAlphaOps AppEnvironmentExtra BRAIN_USERNAME=your@email.com BRAIN_PASSWORD=...
nssm start BrainAlphaOps
```

### 3.7 健康检查

```bash
curl -s http://127.0.0.1:8765/api/health
# 期望: {"ok": true, "status": "ready", "cloud_sync_stale_seconds": 86400}
```

### 3.8 验证

```bash
# 1. 静态分析
python scripts/quality_gate.py
# 期望: 26/28 PASS, 2 项 P1 治理债 (历史)

# 2. 单元测试
python -m pytest tests/ -q
# 期望: 2595 passed, 3 skipped

# 3. 前端测试
cd brain_alpha_ops/web/react_app
npx vitest run
# 期望: 240 passed
```

---

## 4. PyInstaller 打包部署

### 4.1 macOS 打包

```bash
# 在 macOS 上执行
pip install pyinstaller
python build_prod.py
# 产物: dist/BrainAlphaOps (无后缀, 可执行 Mach-O)
ls -lh dist/BrainAlphaOps
# 期望: ~50MB
```

### 4.2 Windows 打包

```powershell
# 在 Windows 上执行
pip install pyinstaller
.\scripts\build_windows.ps1
# 产物: dist\BrainAlphaOps.exe
dir dist\BrainAlphaOps.exe
```

### 4.3 分发 (单文件模式)

#### macOS:

```bash
# 1. (推荐) 代码签名, 避免 Gatekeeper 拦截
codesign --deep --force --options runtime --sign "Developer ID Application: Your Org" dist/BrainAlphaOps
codesign --verify --verbose dist/BrainAlphaOps
spctl --assess --verbose dist/BrainAlphaOps

# 2. 公证 (notarization)
xcrun notarytool submit dist/BrainAlphaOps --keychain-profile "AC_PASSWORD" --wait
xcrun stapler staple dist/BrainAlphaOps

# 3. 分发
scp dist/BrainAlphaOps user@host:/usr/local/bin/
```

#### Windows:

```powershell
# 1. (推荐) 代码签名, 避免 SmartScreen 警告
signtool sign /fd SHA256 /a /tr http://timestamp.digicert.com /td SHA256 dist\BrainAlphaOps.exe
# (需代码签名证书)

# 2. 分发
copy dist\BrainAlphaOps.exe \\fileserver\share\
```

### 4.4 启动打包产物

#### macOS:

```bash
chmod +x BrainAlphaOps
./BrainAlphaOps
# 默认 127.0.0.1:8765
```

#### Windows:

```cmd
BrainAlphaOps.exe
# 默认 127.0.0.1:8765
```

### 4.5 打包产物的数据目录

打包后, `data/` 目录默认**当前工作目录**下:

```bash
# 显式指定
cd /opt/brain-alpha-ops  # 任何目录都可
./BrainAlphaOps
# 会自动创建 ./data/ 目录存放运行时数据
```

> 💡 **生产建议**: 用 systemd 启动, `WorkingDirectory=/opt/brain-alpha-ops`, 数据持久化到 `/opt/brain-alpha-ops/data/`。

---

## 5. 远程访问部署

### 5.1 何时需要

- 多用户 (团队) 共享一台机器
- 不想每次都 SSH 进去

### 5.2 安全前提 (必做)

⚠️ **远程访问需多重防护**:

1. **HTTPS 终止**: 用 nginx + Let's Encrypt (强烈推荐)
2. **admin token**: 强随机 token
3. **firewall**: 限制源 IP
4. **审计日志**: 开启

### 5.3 部署架构

```
Internet
   │
   ▼
nginx (443, HTTPS + Let's Encrypt)
   │
   ▼ (proxy_pass http://127.0.0.1:8765/)
   │
BRAIN-Alpha Ops (127.0.0.1:8765, allow_remote=true)
   │
   ▼ (urllib HTTPS)
api.worldquantbrain.com
```

### 5.4 nginx 配置

`/etc/nginx/sites-available/brain-alpha-ops`:

```nginx
server {
    listen 443 ssl http2;
    server_name brain-alpha-ops.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/brain-alpha-ops.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/brain-alpha-ops.yourdomain.com/privkey.pem;

    # 强制 HTTPS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer" always;

    # 限制源 IP (替换为你的 IP)
    # allow 1.2.3.4;
    # deny all;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }
}

server {
    listen 80;
    server_name brain-alpha-ops.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/brain-alpha-ops /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 5.5 BRAIN-Alpha Ops 启动 (远程模式)

```bash
export BRAIN_ALPHA_OPS_WEB_ALLOW_REMOTE=true
export BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN="$(openssl rand -hex 32)"

# /opt/brain-alpha-ops/.env 中持久化
cat > /opt/brain-alpha-ops/.env <<EOF
BRAIN_ALPHA_OPS_WEB_ALLOW_REMOTE=true
BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN=<paste-token>
BRAIN_USERNAME=...
BRAIN_PASSWORD=...
EOF

chmod 600 /opt/brain-alpha-ops/.env

# 启动
sudo systemctl restart brain-alpha-ops
```

### 5.6 Let's Encrypt 证书

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d brain-alpha-ops.yourdomain.com
# 自动续期: certbot renew
```

---

## 6. 生产环境加固

### 6.1 OS 层

```bash
# 1. 创建独立用户
sudo useradd -r -s /bin/false brain
sudo chown -R brain:brain /opt/brain-alpha-ops

# 2. 文件权限
sudo chmod 700 /opt/brain-alpha-ops
sudo chmod 600 /opt/brain-alpha-ops/.env
sudo chmod 755 /opt/brain-alpha-ops/.venv/bin/python

# 3. firewall
sudo ufw allow 443/tcp  # nginx
sudo ufw deny 8765/tcp  # 阻断 BRAIN 端口 (仅本机)
sudo ufw enable

# 4. 自动更新
sudo apt install unattended-upgrades
```

### 6.2 应用层

| 配置 | 值 | 原因 |
|---|---|---|
| `BRAIN_ALPHA_OPS_WEB_ALLOW_REMOTE` | 仅远程时 `true` | 默认安全 |
| `BRAIN_ALPHA_OPS_WEB_ADMIN_TOKEN` | 32 字节随机 | 远程访问必备 |
| `BRAIN_ALPHA_ENABLE_REAL_SUBMIT_TESTS` | 生产**不设** | 防误提交 |
| `BRAIN_ALPHA_FORCE_REAL_SUBMIT` | **不设** | 防误提交 |
| `web.debug` | `false` | 防止 stack trace 泄露 |

### 6.3 数据层

```bash
# 1. 定期备份 data/ (排除 events.jsonl 因太大)
0 2 * * * rsync -a /opt/brain-alpha-ops/data/ /backup/brain-alpha-ops/data/ --exclude='events.jsonl'

# 2. 日志轮转 /etc/logrotate.d/brain-alpha-ops
/var/log/brain-alpha-ops.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
    create 0640 brain brain
    postrotate
        systemctl reload brain-alpha-ops
    endscript
}
```

### 6.4 监控

详见 [§8 监控与告警](#8-监控与告警)。

---

## 7. 升级与回滚

### 7.1 升级流程

```bash
# 1. 停服
sudo systemctl stop brain-alpha-ops

# 2. 备份当前版本
sudo cp -a /opt/brain-alpha-ops /opt/brain-alpha-ops.bak.$(date +%Y%m%d)

# 3. 部署新版本
cd /opt/brain-alpha-ops
git pull  # 或 scp 新文件
pip install -r requirements.lock
cd brain_alpha_ops/web/react_app
npm ci && npm run build
cd ../../..

# 4. 跑 quality gate
source .venv/bin/activate
python scripts/quality_gate.py

# 5. 启服
sudo systemctl start brain-alpha-ops
sudo systemctl status brain-alpha-ops

# 6. 健康检查
curl -s http://127.0.0.1:8765/api/health
```

### 7.2 回滚流程

```bash
# 1. 停服
sudo systemctl stop brain-alpha-ops

# 2. 切回旧版本
sudo rm -rf /opt/brain-alpha-ops
sudo mv /opt/brain-alpha-ops.bak.<日期> /opt/brain-alpha-ops

# 3. 启服
sudo systemctl start brain-alpha-ops
```

### 7.3 数据库迁移

**当前版本无 ORM, 升级无需数据库迁移**。数据是 JSONL append, 新字段走 `extra_fields` 兜底。

如果将来引入 schema 升级:
- 增量脚本: `scripts/migrate_data_v0.3.0_to_v0.4.0.py`
- 备份优先: 先 cp -a data/ data.bak.<日期>/

---

## 8. 监控与告警

### 8.1 健康检查端点

```bash
curl http://127.0.0.1:8765/api/health
# 返回: {"ok": true, "status": "ready", "cloud_sync_stale_seconds": 86400}
```

### 8.2 Prometheus 集成 (可选, 自定义)

**当前版本未内置 Prometheus exporter**。如需, 自行加:

```python
# prometheus.py (新增)
from prometheus_client import start_http_server, Counter
candidates_total = Counter('candidates_total', 'Total candidates')
# 在 web/__init__.py 中启动 start_http_server(9090)
```

接入 Prometheus:

```yaml
scrape_configs:
  - job_name: 'brain-alpha-ops'
    static_configs:
      - targets: ['localhost:9090']
```

### 8.3 简单告警 (cron + curl)

```bash
# /usr/local/bin/brain-alpha-ops-healthcheck.sh
#!/bin/bash
RESULT=$(curl -s http://127.0.0.1:8765/api/health)
if ! echo "$RESULT" | grep -q '"ok": true'; then
    echo "BRAIN-Alpha Ops unhealthy: $RESULT" | mail -s "ALERT" admin@yourdomain.com
fi
```

```cron
# crontab -e
*/5 * * * * /usr/local/bin/brain-alpha-ops-healthcheck.sh
```

### 8.4 关键指标 (手动)

| 指标 | 怎么看 | 健康阈值 |
|---|---|---|
| `/api/health` 返回 ok | curl | 必须 true |
| `data/events.jsonl` 大小 | ls -lh | < 5 GB |
| `data/expression_index.sqlite` 大小 | ls -lh | < 500 MB |
| 进程内存 | ps | < 1 GB |
| BRAIN API 限频触发 | logs | < 10 次/小时 |
| REAL_SUBMIT 拦截触发 | logs | 0 (生产) |

---

## 9. 故障排查

### 9.1 服务起不来

| 症状 | 排查 |
|---|---|
| `Address already in use` | `lsof -i :8765` → kill 占用进程 |
| `ModuleNotFoundError` | `pip install -r requirements.lock` |
| `Permission denied` | 文件权限, `chmod +x` / `chown` |
| `Web 流程长时间没有明确进度` | 等 5 分钟自动停止, 或手动 `kill` |
| 系统日志 (Linux) | `journalctl -u brain-alpha-ops -f` |
| 系统日志 (macOS) | `tail -F /var/log/brain-alpha-ops.log` |

### 9.2 连接 BRAIN 失败

| 症状 | 排查 |
|---|---|
| 401/403 | 凭据失效, 重测连接 |
| 5xx | 平台问题, 等 5 分钟 |
| 网络超时 | `curl -v https://api.worldquantbrain.com/` |
| token=*** 出现在日志 | bug, 请报 issue |

### 9.3 数据丢失

**默认设计是 append-only, 不会丢数据**。如果出现:

| 症状 | 解决 |
|---|---|
| 候选不显示 | 检查 `data/candidates.jsonl` 是否被外部删除 |
| sqlite 索引缺失 | `data/expression_index.sqlite` 可删, 下次启动重建 |
| `jobs_*.json` 损坏 | 删除 (会丢任务状态, 但 JSONL 历史还在) |

### 9.4 性能问题

| 症状 | 排查 |
|---|---|
| cycle 慢 | 正常 (5-15 min/cycle), 不要调高 API 限频 |
| 启动慢 (>30s) | 1GB+ events.jsonl 重建索引耗时, 正常 |
| 内存膨胀 | 检查 SQLite WAL 是否开 |

### 9.5 安全事件

| 事件 | 响应 |
|---|---|
| 日志发现 token=*** | 立即 `unset BRAIN_TOKEN` + 重新测试连接 |
| 可疑 IP 访问 | 阻断 IP, 改 admin token |
| 凭据疑似泄露 | BRAIN 平台重置密码 + token |
| 服务被外部访问 (未授权) | 立即 `sudo systemctl stop brain-alpha-ops` |

---

## 10. 部署后验证清单 (Post-Deploy Verification)

部署完成后, **逐项确认**:

- [ ] 服务进程运行 (`ps aux | grep brain_alpha` 或 `systemctl status`)
- [ ] `/api/health` 返回 200
- [ ] 浏览器能打开 `http://127.0.0.1:8765/`
- [ ] "测试连接" 通过 (BRAIN 凭据正确)
- [ ] 启动一次 cycle, 看到候选生成
- [ ] 跑一次云端同步, 数据回填
- [ ] 数据写入 `data/candidates.jsonl`
- [ ] (远程) nginx 转发 + HTTPS 正常
- [ ] (远程) admin token 校验生效
- [ ] (生产) REAL_SUBMIT 拦截生效
- [ ] (生产) 凭据仅来自 env, 配置文件无明文
- [ ] (生产) logrotate 配置生效
- [ ] (生产) 备份 cron 配置生效
- [ ] (生产) firewall 规则生效
- [ ] (生产) systemd 启动 + 自动重启

---

**部署就绪** ✅

**配套文档**:
- `DELIVERY_REPORT_FINAL_20260613.md` — 交付报告
- `USER_MANUAL_20260613.md` — 用户手册
- `TEST_REPORT_20260613.md` — 测试报告
- `DEEP_STATIC_ANALYSIS_20260613_v3.md` — 静态分析

**维护**: PAN
**版本**: v0.3.0 (2026-06-13)
