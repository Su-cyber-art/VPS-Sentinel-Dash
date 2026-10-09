# 原生部署与运维

## 部署结构

```text
浏览器 → 用户选择的 HTTP / HTTPS 地址
             ↓ 可选的自有反向代理
       Vue 前端服务 :8080
             ↓ /api 和 /downloads 转发
       FastAPI 后端 127.0.0.1:18087 → SQLite
             ↑
       Agent 主动心跳、领取任务、上传结果
```

安装器不会设置反向代理、证书、防火墙或强制 HTTPS。初始密码通过所选连接传输，公网使用时可自行配置 TLS。

## 交互式安装

```bash
curl -fsSL https://github.com/Su-cyber-art/VPS-Sentinel-Dash/releases/latest/download/install.sh -o sentinel-install.sh
sudo bash sentinel-install.sh
```

主控菜单会询问监听地址、HTTP 端口、后端内部端口、管理员用户名和外部地址。留空外部地址即可使用 IP:端口直接访问。端口范围 1024–65535，后端只监听 127.0.0.1。

安装成功的最后会打印随机初始密码。用初始密码登录后只允许修改密码或退出；直接请求节点管理 API 同样被拒绝。密码修改后，初始密码与旧会话失效。刷新页面、换浏览器或服务重启都不会绕过强制改密。

默认目录：

| 项目 | 路径 / 服务 |
| --- | --- |
| 主控目录 | `/opt/vps-sentinel-dash` |
| 后端 | `vps-sentinel-api.service` |
| 前端 | `vps-sentinel-web.service` |
| 数据库 | `/opt/vps-sentinel-dash/state/sentinel.sqlite3` |
| 环境配置 | `/opt/vps-sentinel-dash/config/backend.env`、`frontend.env` |
| Agent 目录 | `/opt/vps-sentinel-agent` |
| Agent 服务 | `vps-sentinel-agent.service` |
| Agent 凭证 | `/opt/vps-sentinel-agent/state/agent.json` |
| 哨兵模块与日志 | `/opt/vps-sentinel-agent/state/modules` |

主控以 `vps-sentinel` 系统用户运行。Agent 为兼容上游检测脚本，以 root 运行，并由 systemd 限制可写目录。Agent 不提供任意远程 Shell 接口，只执行白名单中的哨兵操作。

## 自动化参数

所有参数可与交互菜单组合。`--yes` 选择默认值并跳过提示。

```bash
sudo bash sentinel-install.sh --role panel --yes \
  --bind 0.0.0.0 --port 8080 --api-port 18087 --username admin

sudo bash sentinel-install.sh --role agent --yes \
  --master http://主控IP:8080 --token-file /root/sentinel-enroll.token
```

接入令牌文件需要由操作者保护和清理；安装器会生成一个临时副本，注册后删除副本。交互模式直接读取令牌，不将其加入命令行。`--modules no` 可只安装基础 Agent，默认安装完整哨兵模块。

可以使用 `--prefix` 设置独立安装目录，升级/重置/卸载时必须使用同一路径。Release 安装器默认从对应的 GitHub 版本标签下载源码；仓库源码内的安装器默认跟随 main。`--ref` 可指定版本或分支，`--source /path/to/repo` 使用本地源码。每次升级构建到独立 release 目录，通过 `current` 链接切换；新版本健康检查失败时恢复上一版程序。旧 release 保留以便回退，可在确认后自行清理。

自动安装依赖支持 Debian/Ubuntu APT。其他 systemd Linux 需要先安装 Python 3.10+、venv/pip、curl、tar、xz；完整 Agent 还需要 Bash、jq、flock、iproute2 和 GNU coreutils。Node.js 不满足版本要求时，安装器会下载 Node 22.23.3 的官方 x64/arm64 构建并校验 SHA-256。

## 自行反向代理

将外部站点代理至前端端口即可，API 转发由前端服务完成。Nginx 示例：

```nginx
server {
    listen 80;
    server_name sentinel.example.com;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }
}
```

HTTPS 的证书与监听配置由你自己的反代管理。配置完成后，在 `backend.env` 设置：

```dotenv
SENTINEL_PUBLIC_URL=https://sentinel.example.com
SENTINEL_COOKIE_SECURE=true
```

然后 `sudo systemctl restart vps-sentinel-api`。外部地址用于网页生成 Agent 安装命令，支持 HTTP 或 HTTPS；Secure Cookie 只在显式开启或外部地址为 HTTPS 时启用。

需要独立部署前端资产时，运行 `npm ci && npm run build`，将 `frontend/dist/` 放入自己的静态服务器，并为 Vue Router 配置 SPA 回退，同时把 `/api/` 与 `/downloads/` 代理到后端。Vite 开发环境默认代理后端，地址可用 `SENTINEL_API_URL` 修改。直接跨源访问 API 可通过前端 `VITE_API_BASE` 与后端 `SENTINEL_CORS_ORIGINS` 设置明确的来源；认证使用 Cookie，建议前后端置于同一站点。

## 服务、更新与密码恢复

升级前先重新下载上方最新 Release 的安装器，再执行升级命令。

```bash
sudo systemctl status vps-sentinel-api vps-sentinel-web
sudo journalctl -u vps-sentinel-api -f
sudo journalctl -u vps-sentinel-agent -f

sudo bash sentinel-install.sh --role panel --action upgrade
sudo bash sentinel-install.sh --role agent --action upgrade
sudo bash sentinel-install.sh --role panel --action reset-password
```

升级保留数据库、已修改的密码、节点凭证和环境配置。重置密码会打印新的随机初始密码，使已有网页会话失效，并恢复首次强制改密状态。

卸载菜单停止服务并删除对应 systemd unit，但保留安装目录和数据。完全清理前应先备份、核对路径；安装器不自动删除数据库或 Agent 身份文件。

## 任务执行

每个节点最多 10 个等待或运行任务，每次只执行一个。Agent 默认每 15 秒心跳，75 秒未上报视为离线；运行任务的租约随心跳续期。请求取消后，Agent 会终止对应哨兵进程并回传确认。对已完成任务不能再取消。

任务结果先写本地，再回传主控；断线后可重传，重复回传不会重复入库。Agent 在执行中重启会报告中断，不自动重跑有副作用的任务。运行租约失效或执行超过总上限后，主控记录失败。任务和事件保留 30 天。

Google / Trust 默认关闭，需在节点策略启用。哨兵巡逻按上游调度逻辑执行已启用的模块；同步数据从当前主控获取其数据快照，不会执行任意下载代码。IPQuality 仍沿用上游探测脚本下载方式和第三方数据源。

## Telegram 通知

在 `backend.env` 填写 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`，重启 API 后，在网页设置中启用。通知仅覆盖节点离线、恢复和任务失败；凭证不会返回浏览器。发送失败最多重试 3 次，之后写入事件日志。

## 备份和 v0.1 迁移

SQLite 使用 WAL，使用 backup API 生成一致快照：

```bash
sudo /opt/vps-sentinel-dash/current/.venv/bin/python - <<'PY'
import sqlite3
with sqlite3.connect('/opt/vps-sentinel-dash/state/sentinel.sqlite3') as src:
    with sqlite3.connect('/opt/vps-sentinel-dash/state/backup.sqlite3') as dst:
        src.backup(dst)
PY
```

v0.1 的数据库可迁移到新数据目录。先停止旧主控，使用 backup API 备份；将备份命名为新目录的 `sentinel.sqlite3`，将所有权设为 `vps-sentinel:vps-sentinel` 后启动新后端。数据库迁移增加任务取消字段，保留节点和任务记录，并使旧管理会话失效、要求管理员改密一次。若旧版没有用户名，使用 `admin`。

旧 Telegram 架构的节点需重新接入网页 Agent。停止旧版 runner/updater/report 定时器和旧 Agent 服务，避免同时运行重复调度。保留旧配置用于回退。新安装器不会擅自停止旧版服务，也不自动导入 Telegram 主控数据库。

## 验收

API 与 Agent 测试覆盖首次密码限制、改密、恢复、Cookie/CSRF、节点撤销、并发领取、定时任务、取消、断线重传及旧库迁移。浏览器测试覆盖桌面与移动布局、登录强制改密、节点操作、任务结果、搜索与策略更新。Linux CI 在 Ubuntu 22.04 / 24.04 上真正运行交互安装、systemd 服务、Agent 模块执行、取消、升级、密码恢复和卸载。

Linux CI 执行原版哨兵脚本时使用隔离的 HTTP 测试夹具；这验证任务控制和脚本集成，不验证第三方服务的可用性或“养 IP”效果。当前版本面向单管理员、单主控使用，尚未进行大规模集群容量测试。
