# VPS-Sentinel-Dash · 主控 + Agent 网页面板

基于 [hotyue/IP-Sentinel](https://github.com/hotyue/IP-Sentinel) 的网页管理版本。网页是管理入口，Telegram 是可选通知通道。

## 已实现

- 中文响应式面板：运行概览、节点管理、任务记录、事件日志、控制台设置。
- Agent 主动上报心跳并领取任务；节点无需开放入站端口。
- 一次性接入令牌、每节点独立凭证、节点移除即撤销凭证。
- 系统快照、网络可达性和地区信号检测、日志回传。
- 原版 Google / Trust 实验模块与 IPQuality 检测的适配，结果直接进入网页。
- 节点策略、分组与地区标签、定时任务、持久化任务队列及结果。
- 管理员登录、CSRF 校验、密码更换、操作事件记录。
- Telegram 可选发送节点离线、恢复和任务失败通知。

## 本地启动

需要 Python 3.9+。没有 pip 或 npm 依赖，也无需前端构建。

```bash
git clone https://github.com/Su-cyber-art/VPS-Sentinel-Dash.git
cd VPS-Sentinel-Dash
python3 -m panel.server
```

打开 <http://127.0.0.1:8080>，使用终端打印的初始化密钥设置管理员密码。默认只监听本机，数据库位于 `runtime/master/`。

在网页点击「接入节点」，生成令牌；在另一个终端启动本机 Agent：

```bash
python3 panel/agent.py \
  --config runtime/local-agent.json \
  --master http://127.0.0.1:8080 \
  --enroll '<网页生成的令牌>'
```

本机 Agent 在 macOS / Linux 上均可回传系统快照、网络检测与日志；原版实验模块仅在 Linux 上执行。内存指标在非 Linux 系统上显示为缺失，不会填入虚构数值。

## VPS 部署

```bash
cp .env.example .env
# 编辑 .env，将 SENTINEL_DOMAIN 改为已解析到主控服务器的域名。
docker compose up -d --build
docker compose logs master
```

开放主控 80/443 端口，通过 `https://你的域名` 完成初始化。Caddy 负责 HTTPS，主控 8080 端口不映射到公网。详细步骤、迁移注意事项、备份和卸载见 [部署文档](panel/README.md)。

在网页生成令牌后，根据接入窗口中的命令安装 Agent。安装时可选择原版模块；默认只安装基础 Agent，实验模块默认关闭。

## 验证

```bash
python3 -m unittest discover -s panel/tests -v
node --check panel/static/app.js
bash -n panel/install-agent.sh core/mod_google.sh core/mod_trust.sh core/mod_quality.sh
```

集成测试启动真实 HTTP 主控与本机 Agent，覆盖任务往返、结果断线重传、令牌一次性使用、会话权限、节点撤销、任务领取并发、定时调度与失联处理；测试不连接第三方探测服务或 Telegram。

## 范围

这是可运行的 v0.1 单管理员版本。当前不包含多用户权限、SSO、主控高可用、Agent 自动升级或数据图表分析平台。提供的 Docker 与 systemd 文件需在目标 Linux 环境验证。

网络检测显示 HTTP 可达性和页面地区信号，不能等同于账号可用性或完整流媒体解锁。原版“养 IP”功能作为实验模块保留；请求成功不代表信誉或定位得到改善。IPQuality 模块沿用上游的数据源及脚本下载行为，应自行审核其执行内容。

上游基线：`5d3d9a1`（2026-10-08）。保留上游 `core/`、`data/` 及原有 Telegram 管理实现，原说明见 [README.upstream.md](README.upstream.md)。本版仅对三个核心模块增加安装目录配置及网页 JSON 回传适配。

上游 GitHub Actions 数据与 Star 图表工作流保留为手动触发；此仓库默认不会定时修改数据文件。

许可证：AGPL-3.0，详见 [LICENSE](LICENSE)。
