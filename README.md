# VPS-Sentinel-Dash

Vue 3 + TypeScript 前端、FastAPI 后端与主动连接的 Agent。通过网页管理 VPS、执行哨兵操作并追踪结果。基于 [hotyue/IP-Sentinel](https://github.com/hotyue/IP-Sentinel)，采用 AGPL-3.0。

## 一键安装

在 Debian 12+ / Ubuntu 22.04+ 的 systemd 服务器上运行：

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/Su-cyber-art/VPS-Sentinel-Dash/main/install.sh)
```

如果 sudo 无法读取进程替换文件，使用保存后运行的等效命令：

```bash
curl -fsSL https://raw.githubusercontent.com/Su-cyber-art/VPS-Sentinel-Dash/main/install.sh -o sentinel-install.sh
sudo bash sentinel-install.sh
```

菜单提供主控安装、Agent 安装、升级、密码重置和卸载。主控安装时交互选择监听地址、面板端口、后端内部端口、管理员用户名，以及可选外部访问地址；自动安装 Python、Node.js 和运行依赖，构建 Vue 前端并配置 systemd。

**安装成功后会打印面板地址、管理员用户名和随机初始密码。首次登录必须修改初始密码，后端在改密前禁止节点与任务操作。** 初始密码不写入源码或配置文件；数据库仅保存密码摘要。升级保留已修改的密码与节点身份。

默认使用 **HTTP 8080**，后端只监听本机 `18087`。不安装或改动 Nginx、Caddy、证书和防火墙；是否使用反向代理或 HTTPS 由用户配置。Agent 同样支持 HTTP 和 HTTPS。

## 接入节点

1. 登录网页并完成首次改密。
2. 点击「接入节点」，填写名称并生成一次性令牌。
3. 在节点执行页面给出的安装命令，粘贴令牌。
4. 安装程序自动准备依赖、哨兵模块和 Agent 服务；完成注册及首次心跳后显示成功。

也可以直接运行统一安装器，选择「安装 Agent 节点」。Agent 只需主动访问主控，无需开放节点入站端口。令牌 15 分钟有效、只能使用一次；注册成功后换成独立节点凭证。

## 网页面板功能

- 运行概览：节点在线状态、系统指标、任务活动和操作事件。
- 节点管理：搜索、分组与地区标签、单节点或批量任务、模块开关、定时策略。
- 哨兵操作：系统快照、网络检测、IP 质量检测、哨兵巡逻、Google 区域访问、Trust 本地站点访问、日志读取、哨兵数据同步。
- 任务记录：队列状态、结构化结果、输出日志、运行中任务取消、失败原因。
- 安全与恢复：初次强制改密、会话撤销、CSRF 校验、节点凭证撤销、结果断线重传。
- Telegram：可选的离线、恢复和失败通知；管理操作统一在网页完成。

Google / Trust 是上游实验性访问模块，默认关闭。HTTP 成功不代表信誉或定位改善。网络检测展示 HTTP 可达性和页面地区信号，不等同于完整流媒体解锁。IPQuality 沿用上游第三方检测脚本及数据源。

## 项目结构

```text
frontend/                 Vue 3 + TypeScript + Vue Router + Vite 独立前端
  src/                    页面、组件、API 客户端与状态
  server.mjs              生产前端服务，提供构建资产并代理 /api、/downloads
backend/                  独立 FastAPI 项目与依赖锁
  sentinel_api/           认证、节点、任务、Agent API、SQLite 存储
  tests/                  API、首次改密、权限、调度与 Agent 测试
agent/sentinel_agent.py   独立 Python Agent，无第三方 Python 依赖
install.sh               交互式原生安装、升级、重置与卸载
core/ + data/             上游哨兵模块与区域数据
frontend/e2e/             浏览器完整流程及桌面/移动布局验证
tests/native_install.py  Linux systemd 实机安装验收（CI 环境）
```

前端与后端拥有独立的依赖、构建和运行入口。后端只提供 API，不提供 HTML。原生部署使用两个独立进程：`vps-sentinel-web` 与 `vps-sentinel-api`；也可将前端 `dist/` 部署到自己的 Web 服务器，并单独运行后端。

## 本地开发

需要 Python 3.10+ 与 Node.js 20.19+ / 22.12+。推荐 Node 22。

后端：

```bash
git clone https://github.com/Su-cyber-art/VPS-Sentinel-Dash.git
cd VPS-Sentinel-Dash/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python -m sentinel_api.cli bootstrap
.venv/bin/python -m uvicorn sentinel_api.main:app --host 127.0.0.1 --port 18087
```

初始化命令打印随机初始密码。另开终端启动前端：

```bash
cd VPS-Sentinel-Dash/frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`，使用 `admin` 与初始密码登录，再设置新密码。Vite 会代理 API 请求至后端。API 文档位于 `/api/docs`。

## 构建和测试

```bash
cd frontend
npm ci
npm run build

cd ../backend
.venv/bin/pip install -r requirements-test.lock
.venv/bin/python -m pytest -q
```

浏览器测试使用专用临时数据库、真实本机 Agent 和独立前后端进程：

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

GitHub Actions 运行 Python 3.10 / 3.12 API 测试、Chromium 完整流程、桌面和手机截图，以及 Ubuntu 22.04 / 24.04 上的真实交互式安装与 systemd 验收。Linux 验收会实际执行上游哨兵脚本，并用明确的 HTTP 测试夹具替代第三方站点流量。

## 部署与来源

端口、反代、服务命令、升级、密码恢复、备份和 v0.1 迁移见 [部署文档](deploy/README.md)。当前为单管理员、单主控版本，SQLite 持久化；不包含多租户与主控高可用。

上游基线为 `hotyue/IP-Sentinel@5d3d9a1`。上游说明保留在 [README.upstream.md](README.upstream.md)，旧安装入口保存在 `legacy/`；上游数据与 Star 图表工作流改为手动触发。2026-10-09 的本次衍生修改包括独立前后端、原生安装器与哨兵模块适配。

许可证：[AGPL-3.0](LICENSE)。
