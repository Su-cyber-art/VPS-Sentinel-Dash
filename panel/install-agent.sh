#!/usr/bin/env bash
# Installs the web agent and optional upstream modules on a Linux systemd host.
set -euo pipefail
umask 077
if [[ "${EUID}" != 0 ]]; then
  echo "请使用 sudo bash install-agent.sh https://你的主控域名" >&2
  exit 1
fi
command -v python3 >/dev/null
command -v curl >/dev/null
command -v systemctl >/dev/null
MASTER="${1:?请提供主控地址，如 https://sentinel.example.com}"
MASTER="${MASTER%/}"
python3 - "$MASTER" <<'PY'
import sys, urllib.parse
u = urllib.parse.urlparse(sys.argv[1])
assert u.scheme == 'https' and u.hostname and not u.username and not u.password and u.path == '' and not u.query and not u.fragment, '主控地址必须为 HTTPS origin'
PY
INSTALL_ROOT=/opt/ip_sentinel_web
if [[ -e "$INSTALL_ROOT/agent.json" ]]; then
  echo "已存在 Agent 配置。升级请先停止 ip-sentinel-web-agent 并备份该目录。" >&2
  exit 1
fi
mkdir -p "$INSTALL_ROOT"
read -r -s -p '粘贴网页生成的接入令牌: ' ENROLL_TOKEN
printf '\n'
printf '%s' "$ENROLL_TOKEN" > "$INSTALL_ROOT/enrollment.token"
unset ENROLL_TOKEN
curl -fSL --proto '=https' --proto-redir '=https' "$MASTER/download/agent.py" -o "$INSTALL_ROOT/agent.py"
read -r -p '同时安装原版实验养护与 IPQuality 模块？[y/N] ' INSTALL_MODULES
if [[ "$INSTALL_MODULES" =~ ^[Yy]$ ]]; then
  for tool in bash curl jq flock ip timeout; do
    command -v "$tool" >/dev/null || { echo "缺少依赖 $tool，请先安装" >&2; exit 1; }
  done
  curl -fSL --proto '=https' --proto-redir '=https' "$MASTER/download/modules.tar.gz" -o "$INSTALL_ROOT/modules.tar.gz"
  python3 - "$INSTALL_ROOT" <<'PY'
import pathlib, sys, tarfile
root = pathlib.Path(sys.argv[1]).resolve()
with tarfile.open(root / 'modules.tar.gz') as tar:
    for item in tar.getmembers():
        target = (root / item.name).resolve()
        if root not in target.parents or not (item.isfile() or item.isdir()):
            raise SystemExit('Invalid module archive')
    tar.extractall(root)
(root / 'modules.tar.gz').unlink()
PY
fi
cat > /etc/systemd/system/ip-sentinel-web-agent.service <<EOF
[Unit]
Description=IP Sentinel Web Agent
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart=/usr/bin/env python3 $INSTALL_ROOT/agent.py --config $INSTALL_ROOT/agent.json --root $INSTALL_ROOT --master $MASTER --enroll-file $INSTALL_ROOT/enrollment.token
Restart=on-failure
RestartSec=15
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_ROOT
KillMode=control-group
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now ip-sentinel-web-agent
echo 'Agent 已启动。使用 journalctl -u ip-sentinel-web-agent -f 查看日志。'
