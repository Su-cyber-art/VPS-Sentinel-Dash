# 网页主控部署与运维

## 通信流程

```text
浏览器 ──HTTPS + 管理会话──> Caddy ──HTTP──> 主控 API ──> SQLite
                                              ↑
                        Agent ──HTTPS 心跳/领取任务/上传结果
                                              │
                                     Telegram 可选事件通知
```

Agent 每 15 秒主动连接；超过 75 秒无心跳记为离线。主控每 10 秒检查超时与定时任务。每节点同时执行一个任务，最多保留 10 个等待或执行中的任务。超过 120 秒没有更新的运行租约记为失败，不自动重试可能有副作用的操作。Agent 会在执行期间继续发送心跳；任务最长运行 20 分钟。

任务结果先写入 Agent 本地，再上传；主控按任务及租约校验，重复提交已完成结果不会重复入库。Agent 执行中重启会报告任务中断，不重跑旧命令。若领取任务的响应丢失，租约超时后会显示失败，需要操作者检查并按需重新运行。

## 主控：推荐 Docker Compose

1. 将完整项目上传至主控服务器；安装 Docker 和 Compose 插件。
2. 域名 A/AAAA 记录指向主控，开放 TCP 80 和 443。
3. 复制 `.env.example` 为 `.env`，设置 `SENTINEL_DOMAIN=sentinel.example.com`（不带协议、路径、端口）。
4. 执行 `docker compose up -d --build`。
5. 执行 `docker compose logs master`，读取“首次初始化密钥”。通过 HTTPS 网页输入该密钥并设置至少 12 位的管理密码。

主控容器以非 root 用户运行。持久数据保存在 `sentinel_state` 卷，Caddy 证书保存在独立卷。重建容器不会重置管理员或节点凭证。

初始化密钥仅在没有管理员时有效。可通过 `SENTINEL_SETUP_TOKEN` 指定；如果没有设置，每次启动生成新的密钥。管理密码使用随机盐与 PBKDF2-HMAC-SHA256（600,000 次迭代）存储；登录会话与 Agent 凭证在数据库内保存 SHA-256 摘要。修改管理密码使全部网页会话失效。

## 主控：直接运行 Python

Python 3.9+，无需额外 Python 包。默认监听 `127.0.0.1:8080`，由现有反向代理转发并终止 TLS。

```bash
SENTINEL_PUBLIC_URL=https://sentinel.example.com \
  python3 -m panel.server --host 127.0.0.1 --port 8080 --data /var/lib/ip-sentinel-web
```

配置反向代理保留 Host，公共地址必须与浏览器访问的 HTTPS origin 一致。`SENTINEL_PUBLIC_URL` 开启 Secure 会话 Cookie；不要用 HTTP 地址访问已配置的生产主控。可用进程管理器或 systemd 守护主控进程。

| 配置 | 用途 |
| --- | --- |
| `SENTINEL_HOST` / `--host` | 监听地址，默认 127.0.0.1 |
| `SENTINEL_PORT` / `--port` | 监听端口，默认 8080 |
| `SENTINEL_DATA` / `--data` | SQLite 数据目录，默认 runtime/master |
| `SENTINEL_PUBLIC_URL` | 生产 HTTPS origin，如 https://sentinel.example.com |
| `SENTINEL_SETUP_TOKEN` | 可选首次初始化密钥 |
| `SENTINEL_ADMIN_PASSWORD` | 可选首次创建管理员的密码，已有管理员后不再使用 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 可选通知通道凭证，不参与节点认证 |

## Agent：Linux 安装

推荐 Debian / Ubuntu 或其他带 systemd 的 Linux。基础 Agent 需要 `python3`、`curl`。实验模块另需 Bash 4+、`jq`、`flock`、`ip`、`timeout` 及原版脚本依赖。

Debian / Ubuntu 示例：

```bash
sudo apt-get update
sudo apt-get install -y python3 curl bash jq util-linux iproute2 coreutils ca-certificates
```

在网页点击“接入节点”，填写名称，生成一次性令牌。在目标主机保存并运行安装程序：

```bash
curl -fsS 'https://sentinel.example.com/download/install-agent.sh' -o install-agent.sh
sudo bash install-agent.sh 'https://sentinel.example.com'
```

安装程序交互式读取令牌，避免将其保存在命令历史中。令牌写入权限受限的临时文件，注册成功后删除。程序安装至 `/opt/ip_sentinel_web`，服务名为 `ip-sentinel-web-agent`。该目录包含身份配置、持久任务状态和选装模块。远程接入必须使用证书有效的 HTTPS。

```bash
systemctl status ip-sentinel-web-agent
journalctl -u ip-sentinel-web-agent -f
```

安装脚本需要 systemd。Alpine/OpenRC 等系统请直接使用 `python3 agent.py` 并接入对应的进程管理器；此版本未提供 OpenRC 安装器。

## 已安装旧版 IP-Sentinel 的节点

网页 Agent 使用独立的节点凭证，不能直接将原 Telegram Chat ID 当作接入令牌。支持分阶段迁移：

1. 安装新的网页 Agent，使用独立的 `/opt/ip_sentinel_web` 目录，按需选装模块。
2. 确认新节点在线、系统快照执行成功，再配置目标地区和定时策略。
3. 关闭旧版 `ip-sentinel-runner.timer`、`ip-sentinel-updater.timer`、`ip-sentinel-report.timer` 和 `ip-sentinel-agent-daemon.service`，避免重复养护、旧版自动更新及双重管理。具体以服务器已有服务为准。
4. 旧版脚本若曾写入 crontab 或其他调度器，也需要停止对应任务；关闭之前先核对条目，保留原配置作为回退。

本版本不自动迁移 Telegram 主控数据库，也不会自动停止旧服务。旧节点应重新接入网页主控。

## 原版模块与数据

Google 和 Trust 作为实验性访问模块，默认关闭。先选装模块，再在网页节点策略中启用；定时任务可选择系统快照、网络检测、IPQuality 或对应实验模块。周期设置为 0 表示关闭，最小 5 分钟。

主控向 Agent 同步地区文件路径；Agent 校验路径必须位于区域目录内，并由白名单字段生成配置。仅执行预定义任务，不提供任意 Shell 输入。模块包中保留上游数据快照；当前不会自动更新关键词和 User-Agent 库。

IPQuality 模块沿用上游行为：首次执行会从 `xykt/IPQuality` 等上游地址下载检测脚本并运行；结果受第三方数据源和配额影响。网页版将 JSON 返回主控，不向 Telegram 发送原版检测报告。Google/Trust 的访问日志仍包含上游命名，但不应据此判定信誉改善。

网页 Agent 的基础网络检测通过系统默认路由访问 Cloudflare、Google、YouTube，不切换 WARP 或代理。原版模块保留已有 `BIND_IP` 配置支持，网页当前没有提供多出口 IP 管理界面。

## Telegram 仅做通知

在 `.env` 设置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`，执行 `docker compose up -d` 后，在网页“控制台设置”启用通知。凭证不会通过网页返回。

只对节点离线、恢复连接和任务失败发通知。启用前的历史事件不会补发。发送失败最多尝试 3 次，之后记录通知失败事件。关闭通知会清空待发送通知标记。

## 更新与卸载

主控：保存数据卷，更新本地源码后执行 `docker compose up -d --build`。升级前先备份。当前没有数据库跨大版本迁移器，v0.1 内仅初始化缺失表。

Agent：停止 `ip-sentinel-web-agent`，备份安装目录，替换 `agent.py` 及所需模块后重启。已有 `agent.json` 会复用节点身份；不要重新运行初次安装器覆盖凭证。此版本不包含在线 OTA。

移除网页中的节点会立即撤销认证，但不会删除服务器文件或主动杀死已启动的模块进程。完全卸载：

```bash
sudo systemctl disable --now ip-sentinel-web-agent
sudo rm /etc/systemd/system/ip-sentinel-web-agent.service
sudo systemctl daemon-reload
# 核对 /opt/ip_sentinel_web 内没有需要保留的数据后，再手动删除目录。
```

## 备份

SQLite 使用 WAL。不要只复制正在运行的 `.sqlite3` 文件；使用 SQLite backup API 获取一致快照：

```bash
docker compose exec master python -c "import sqlite3; src=sqlite3.connect('/state/sentinel.sqlite3'); dst=sqlite3.connect('/state/backup.sqlite3'); src.backup(dst); dst.close(); src.close()"
docker compose cp master:/state/backup.sqlite3 ./backup.sqlite3
```

备份包含节点凭证摘要、管理员密码摘要、任务和事件，请妥善保存。恢复时停止主控，在空的持久目录放入备份并命名为 `sentinel.sqlite3`，保持容器用户 UID 10001 可读写；不要混入其他时间点的 WAL 文件。

## 验证范围

`python3 -m unittest discover -s panel/tests -v` 在本机启动真实 HTTP 服务及真实 Agent，验证注册、权限、并发领取、任务回传、断线持久化、定时策略、超时失败和凭证撤销。测试不向 Telegram 发信，不运行外部实验访问模块。

本机没有 Docker 或 Linux systemd 环境，因此容器构建、HTTPS 证书签发和 Linux 安装流程尚未实机验证。网页入口已可访问；核心主控/Agent 流程已通过本机 HTTP 集成测试。完整浏览器交互与移动端布局尚未完成验证。v0.1 面向个人、单主控、单管理员使用；高并发容量、长期运行稳定性及上游“养 IP”效果不在本次验证范围内。
