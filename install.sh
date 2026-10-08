#!/usr/bin/env bash
# VPS-Sentinel-Dash native installer. Supports HTTP and HTTPS without configuring a reverse proxy.
set -Eeuo pipefail
umask 027
REPOSITORY="${SENTINEL_REPOSITORY:-Su-cyber-art/VPS-Sentinel-Dash}"
REF="${SENTINEL_REF:-main}"
NODE_VERSION=22.23.3
ROLE= ACTION=install PREFIX= SOURCE= BIND= WEB_PORT= API_PORT= PUBLIC_URL= USERNAME= MASTER= TOKEN_FILE= MODULES=yes
YES=false
for arg in "$@"; do
  if [[ "$arg" == --help || "$arg" == -h ]]; then
    cat <<'HELP'
VPS-Sentinel-Dash 交互式安装器
  sudo bash install.sh                       交互式菜单
  sudo bash install.sh --role panel          安装主控面板
  sudo bash install.sh --role agent --master http://IP:8080
可选参数：
  --action install|upgrade|reset-password|uninstall
  --prefix /opt/vps-sentinel-dash  --source /path/to/source  --ref main
  --bind 0.0.0.0  --port 8080  --api-port 18087
  --public-url http://IP:8080  --username admin
  --master http://IP:8080  --token-file /path/to/token  --modules yes|no
  --yes    使用所提供参数和默认值，不提示输入（节点接入需 --token-file）
支持 Debian 12+ / Ubuntu 22.04+；其他 systemd Linux 可预装 Python 3.10+、curl、tar、xz 及模块依赖后运行。
HELP
    exit 0
  fi
done
while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="${2:?}"; shift 2;;
    --action) ACTION="${2:?}"; shift 2;;
    --prefix) PREFIX="${2:?}"; shift 2;;
    --source) SOURCE="${2:?}"; shift 2;;
    --ref) REF="${2:?}"; shift 2;;
    --bind) BIND="${2:?}"; shift 2;;
    --port) WEB_PORT="${2:?}"; shift 2;;
    --api-port) API_PORT="${2:?}"; shift 2;;
    --public-url) PUBLIC_URL="${2-}"; shift 2;;
    --username) USERNAME="${2:?}"; shift 2;;
    --master) MASTER="${2:?}"; shift 2;;
    --token-file) TOKEN_FILE="${2:?}"; shift 2;;
    --modules) MODULES="${2:?}"; shift 2;;
    --yes) YES=true; shift;;
    *) printf '未知参数：%s\n' "$1" >&2; exit 1;;
  esac
done
[[ "$(uname -s)" == Linux ]] || { echo '安装器需要 Linux；本地开发请参考 README。' >&2; exit 1; }
[[ "$EUID" == 0 ]] || { echo '请使用 sudo 或 root 运行安装器。' >&2; exit 1; }
command -v systemctl >/dev/null || { echo '此安装器需要 systemd。' >&2; exit 1; }
INPUT_FD=0
if ! $YES && { true </dev/tty; } 2>/dev/null; then exec 3<>/dev/tty; INPUT_FD=3; fi
prompt() {
  local variable="$1" label="$2" fallback="$3" secret="${4:-false}" answer
  if $YES; then printf -v "$variable" '%s' "$fallback"; return; fi
  printf '%s [%s]: ' "$label" "$fallback" >&2
  if [[ "$secret" == true ]]; then IFS= read -rs -u "$INPUT_FD" answer; printf '\n' >&2; else IFS= read -r -u "$INPUT_FD" answer; fi
  printf -v "$variable" '%s' "${answer:-$fallback}"
}
if [[ -z "$ROLE" ]]; then
  printf '\nVPS Sentinel Dash · 原生安装管理\n1) 安装主控面板\n2) 安装 Agent 节点\n3) 升级主控面板\n4) 升级 Agent\n5) 重置管理员初始密码\n6) 卸载主控服务（保留数据）\n7) 卸载 Agent 服务（保留数据）\n'
  prompt CHOICE '请选择' 1
  case "$CHOICE" in
    1) ROLE=panel;; 2) ROLE=agent;; 3) ROLE=panel; ACTION=upgrade;; 4) ROLE=agent; ACTION=upgrade;;
    5) ROLE=panel; ACTION=reset-password;; 6) ROLE=panel; ACTION=uninstall;; 7) ROLE=agent; ACTION=uninstall;;
    *) echo '选择无效。' >&2; exit 1;;
  esac
fi
[[ "$ROLE" == panel || "$ROLE" == agent ]] || { echo 'role 必须为 panel 或 agent' >&2; exit 1; }
[[ "$ACTION" =~ ^(install|upgrade|reset-password|uninstall)$ ]] || { echo 'action 无效' >&2; exit 1; }
[[ "$MODULES" == yes || "$MODULES" == no ]] || { echo 'modules 必须为 yes 或 no' >&2; exit 1; }
if [[ -z "$PREFIX" ]]; then
  if [[ "$ROLE" == panel ]]; then PREFIX=/opt/vps-sentinel-dash; else PREFIX=/opt/vps-sentinel-agent; fi
fi
[[ "$PREFIX" =~ ^/[A-Za-z0-9_./-]+$ && "$PREFIX" != / && "$PREFIX" != /opt && "$PREFIX" != /usr && "$PREFIX" != /etc && "$PREFIX" != /var && "$PREFIX" != /tmp && "$PREFIX" != *'..'* ]] || { echo '安装目录必须是独立的绝对路径，不含空格或 ..。' >&2; exit 1; }
[[ ! -e "$PREFIX/current" || -L "$PREFIX/current" ]] || { echo 'current 路径已存在且不是本安装器的链接，请选择其他目录。' >&2; exit 1; }
STATE="$PREFIX/state"
CONFIG="$PREFIX/config"
META="$CONFIG/install.json"
if [[ "$ROLE" == panel ]]; then CHECK_SERVICES=(vps-sentinel-api vps-sentinel-web); else CHECK_SERVICES=(vps-sentinel-agent); fi
for existing_service in "${CHECK_SERVICES[@]}"; do
  if [[ -f "/etc/systemd/system/$existing_service.service" ]] && ! grep -Fq "$PREFIX/current" "/etc/systemd/system/$existing_service.service"; then
    printf '服务 %s 已从其他目录安装，请指定原来的 --prefix。\n' "$existing_service" >&2
    exit 1
  fi
done
if [[ "$ACTION" != install && ! -f "$META" ]]; then echo '未找到安装记录，请先安装或指定正确的 --prefix。' >&2; exit 1; fi
if [[ "$ACTION" == uninstall ]]; then
  prompt CONFIRM '停止并卸载对应服务？数据仍保留在安装目录 (yes/no)' no
  if [[ "$CONFIRM" != yes ]] && ! $YES; then exit 0; fi
  if [[ "$ROLE" == panel ]]; then SERVICES=(vps-sentinel-api vps-sentinel-web); else SERVICES=(vps-sentinel-agent); fi
  for service in "${SERVICES[@]}"; do
    if [[ -f "/etc/systemd/system/$service.service" ]] && grep -Fq "$PREFIX/current" "/etc/systemd/system/$service.service"; then
      systemctl disable --now "$service.service"
      rm "/etc/systemd/system/$service.service"
    fi
  done
  systemctl daemon-reload
  printf '服务已卸载；代码与数据保留于 %s。\n' "$PREFIX"
  exit 0
fi
TEMP=$(mktemp -d /tmp/vps-sentinel-install.XXXXXX)
chmod 700 "$TEMP"
OLD_CURRENT= SWITCHED=false
cleanup() { rm -rf -- "$TEMP"; }
failed() {
  local status=$?
  trap - ERR
  set +e
  if $SWITCHED && [[ -n "$OLD_CURRENT" ]]; then
    ln -sfn "$OLD_CURRENT" "$PREFIX/.current-rollback"
    mv -Tf "$PREFIX/.current-rollback" "$PREFIX/current"
    if [[ "$ROLE" == panel ]]; then systemctl restart vps-sentinel-api vps-sentinel-web; else systemctl restart vps-sentinel-agent; fi
    echo '新版本启动失败，已恢复之前的程序版本。' >&2
  fi
  printf '安装未完成（退出码 %s）。请查看上方错误及 journalctl 日志。\n' "$status" >&2
  exit "$status"
}
trap cleanup EXIT
trap failed ERR
if [[ "$ACTION" == reset-password ]]; then
  [[ "$ROLE" == panel ]] || { echo '只有主控支持密码重置。' >&2; exit 1; }
  [[ -n "$USERNAME" ]] || USERNAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["username"])' "$META")
  PYTHONPATH="$PREFIX/current/backend" "$PREFIX/current/.venv/bin/python" -m sentinel_api.cli reset-password --data "$STATE" --username "$USERNAME" --password-file "$TEMP/password" >/dev/null
  chown -R vps-sentinel:vps-sentinel "$STATE"
  printf '\n密码已重置。\n用户名：%s\n新的初始密码：%s\n首次登录后必须修改密码。\n' "$USERNAME" "$(cat "$TEMP/password")"
  exit 0
fi
if [[ "$ACTION" == install && -f "$META" ]]; then
  echo '已有安装。将按升级流程处理，保留管理员、节点凭证和数据库。'
  ACTION=upgrade
fi
printf '\n准备 %s 服务，安装目录：%s\n' "$ROLE" "$PREFIX"
if [[ "$ROLE" == panel ]]; then
  if [[ "$ACTION" == upgrade ]]; then
    readarray -t VALUES < <(python3 - "$META" <<'PY'
import json,sys
v=json.load(open(sys.argv[1]))
for key in ('bind','port','api_port','public_url','username'): print(v.get(key,''))
PY
)
    BIND="${VALUES[0]}"; WEB_PORT="${VALUES[1]}"; API_PORT="${VALUES[2]}"; PUBLIC_URL="${VALUES[3]}"; USERNAME="${VALUES[4]}"
  else
    [[ -n "$BIND" ]] || prompt BIND '面板监听地址（0.0.0.0 为全部网卡）' 0.0.0.0
    [[ -n "$WEB_PORT" ]] || prompt WEB_PORT '面板 HTTP 端口' 8080
    [[ -n "$API_PORT" ]] || prompt API_PORT '后端内部端口（只监听本机）' 18087
    [[ -n "$USERNAME" ]] || prompt USERNAME '管理员用户名' admin
    [[ -n "$PUBLIC_URL" ]] || prompt PUBLIC_URL '外部访问地址（可留空，稍后自行配置反代）' ''
  fi
  [[ "$WEB_PORT" =~ ^[0-9]+$ && "$API_PORT" =~ ^[0-9]+$ && "$WEB_PORT" -ge 1024 && "$WEB_PORT" -le 65535 && "$API_PORT" -ge 1024 && "$API_PORT" -le 65535 && "$WEB_PORT" != "$API_PORT" ]] || { echo '两个端口需不同，且在 1024–65535 之间。' >&2; exit 1; }
  [[ "$USERNAME" =~ ^[A-Za-z0-9_.-]{1,64}$ ]] || { echo '用户名格式无效。' >&2; exit 1; }
fi
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip curl tar xz-utils ca-certificates
  if [[ "$ROLE" == agent && "$MODULES" == yes ]]; then apt-get install -y -qq jq util-linux iproute2 coreutils; fi
else
  for tool in python3 curl tar xz; do command -v "$tool" >/dev/null || { printf '请先安装依赖：%s\n' "$tool" >&2; exit 1; }; done
  if [[ "$ROLE" == agent && "$MODULES" == yes ]]; then
    for tool in jq flock ip timeout; do command -v "$tool" >/dev/null || { printf '请先安装模块依赖：%s\n' "$tool" >&2; exit 1; }; done
  fi
fi
python3 -c 'import sys; assert sys.version_info >= (3,10), "需要 Python 3.10+"'
mkdir -p "$PREFIX/releases" "$STATE" "$CONFIG"
chmod 755 "$PREFIX" "$PREFIX/releases"
RELEASE="$PREFIX/releases/$(date -u +%Y%m%d%H%M%S)-$RANDOM"
mkdir -p "$RELEASE"
chmod 755 "$RELEASE"
if [[ "$ROLE" == panel ]]; then
  python3 - "$BIND" "$PUBLIC_URL" <<'PY'
import ipaddress,sys,urllib.parse
ipaddress.ip_address(sys.argv[1])
if sys.argv[2]:
    u=urllib.parse.urlsplit(sys.argv[2]); assert u.scheme in ('http','https') and u.hostname and not u.username and not u.password and u.path in ('','/') and not u.query and not u.fragment and not any(c.isspace() for c in sys.argv[2]), '外部地址格式无效'
    _=u.port
PY
  if [[ "$ACTION" == install ]]; then
    python3 - "$BIND" "$WEB_PORT" "$API_PORT" <<'PY'
import socket,sys
for host,port in ((sys.argv[1],int(sys.argv[2])),('127.0.0.1',int(sys.argv[3]))):
    with socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET) as s: s.bind((host,port))
PY
  fi
  if [[ -n "$SOURCE" ]]; then
    [[ -f "$SOURCE/backend/pyproject.toml" ]] || { echo '源代码目录无效' >&2; exit 1; }
    tar -C "$SOURCE" --exclude=.git --exclude=node_modules --exclude=.venv --exclude=runtime --exclude=dist --exclude=__pycache__ --exclude=.pytest_cache --exclude=test-results --exclude=playwright-report -cf - . | tar -C "$RELEASE" -xf -
  else
    [[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && "$REF" =~ ^[A-Za-z0-9_./-]+$ ]] || { echo '源码仓库或版本无效' >&2; exit 1; }
    curl -fSL --retry 3 "https://codeload.github.com/$REPOSITORY/tar.gz/$REF" -o "$TEMP/source.tar.gz"
    tar -xzf "$TEMP/source.tar.gz" --strip-components=1 -C "$RELEASE"
  fi
  NODE_BIN=
  if [[ -x "$PREFIX/runtime/node/bin/node" ]] && "$PREFIX/runtime/node/bin/node" -e 'let [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22 || (a===22&&b>=12) || (a===20&&b>=19) ? 0 : 1)'; then
    NODE_BIN="$PREFIX/runtime/node/bin/node"
  elif command -v node >/dev/null && node -e 'let [a,b]=process.versions.node.split(".").map(Number); process.exit(a>22 || (a===22&&b>=12) || (a===20&&b>=19) ? 0 : 1)'; then
    NODE_BIN=$(command -v node)
  else
    case "$(uname -m)" in x86_64) ARCH=x64;; aarch64|arm64) ARCH=arm64;; *) echo 'Node 自动安装只支持 x86_64 / arm64。' >&2; exit 1;; esac
    NODE_ARCHIVE="node-v$NODE_VERSION-linux-$ARCH.tar.xz"
    curl -fSL --retry 3 "https://nodejs.org/dist/v$NODE_VERSION/$NODE_ARCHIVE" -o "$TEMP/$NODE_ARCHIVE"
    curl -fSL --retry 3 "https://nodejs.org/dist/v$NODE_VERSION/SHASUMS256.txt" -o "$TEMP/node-checksums.txt"
    (cd "$TEMP"; awk -v file="$NODE_ARCHIVE" '$2==file' node-checksums.txt > verify.txt; [[ -s verify.txt ]]; sha256sum -c verify.txt)
    mkdir -p "$PREFIX/runtime/node"
    chmod 755 "$PREFIX/runtime" "$PREFIX/runtime/node"
    tar -xJf "$TEMP/$NODE_ARCHIVE" --strip-components=1 -C "$PREFIX/runtime/node"
    NODE_BIN="$PREFIX/runtime/node/bin/node"
  fi
  export PATH="$(dirname "$NODE_BIN"):$PATH"
  python3 -m venv "$RELEASE/.venv"
  "$RELEASE/.venv/bin/python" -m pip install --disable-pip-version-check -q -r "$RELEASE/backend/requirements.lock"
  (cd "$RELEASE/frontend"; npm ci --no-audit --no-fund; npm run build)
  id vps-sentinel >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin vps-sentinel
  chgrp -R vps-sentinel "$RELEASE"
  chmod -R g+rX "$RELEASE"
  chown -R vps-sentinel:vps-sentinel "$STATE"
  chown root:vps-sentinel "$CONFIG"; chmod 750 "$CONFIG"
  if [[ ! -f "$CONFIG/backend.env" ]]; then
    cat > "$CONFIG/backend.env" <<EOF
SENTINEL_DATA=$STATE
SENTINEL_PUBLIC_URL=${PUBLIC_URL%/}
SENTINEL_COOKIE_SECURE=false
SENTINEL_CORS_ORIGINS=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
  fi
  cat > "$CONFIG/frontend.env" <<EOF
SENTINEL_WEB_HOST=$BIND
SENTINEL_WEB_PORT=$WEB_PORT
SENTINEL_API_URL=http://127.0.0.1:$API_PORT
EOF
  chmod 640 "$CONFIG/"*.env; chown root:vps-sentinel "$CONFIG/"*.env
  cat > /etc/systemd/system/vps-sentinel-api.service <<EOF
[Unit]
Description=VPS Sentinel FastAPI backend
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=vps-sentinel
Group=vps-sentinel
WorkingDirectory=$PREFIX/current/backend
EnvironmentFile=$CONFIG/backend.env
ExecStart=$PREFIX/current/.venv/bin/python -m uvicorn sentinel_api.main:app --host 127.0.0.1 --port $API_PORT --no-proxy-headers
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$STATE
[Install]
WantedBy=multi-user.target
EOF
  cat > /etc/systemd/system/vps-sentinel-web.service <<EOF
[Unit]
Description=VPS Sentinel Vue frontend
After=network-online.target vps-sentinel-api.service
Wants=vps-sentinel-api.service
[Service]
Type=simple
User=vps-sentinel
Group=vps-sentinel
WorkingDirectory=$PREFIX/current/frontend
EnvironmentFile=$CONFIG/frontend.env
ExecStart=$NODE_BIN $PREFIX/current/frontend/server.mjs
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
[Install]
WantedBy=multi-user.target
EOF
else
  if [[ "$ACTION" == upgrade ]]; then
    MASTER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["master"])' "$STATE/agent.json")
  else
    [[ -n "$MASTER" ]] || prompt MASTER '主控访问地址（HTTP 或 HTTPS）' ''
  fi
  MASTER="${MASTER%/}"
  python3 - "$MASTER" <<'PY'
import sys,urllib.parse
u=urllib.parse.urlsplit(sys.argv[1]); assert u.scheme in ('http','https') and u.hostname and not u.username and not u.password and not u.path and not u.query and not u.fragment and not any(c.isspace() for c in sys.argv[1]), '主控地址格式无效'
_=u.port
PY
  curl -fSL --retry 3 "$MASTER/downloads/agent.py" -o "$RELEASE/sentinel_agent.py"
  if [[ "$MODULES" == yes ]]; then
    curl -fSL --retry 3 "$MASTER/downloads/modules.tar.gz" -o "$TEMP/modules.tar.gz"
    mkdir -p "$STATE/modules"
    python3 - "$STATE/modules" "$TEMP/modules.tar.gz" <<'PY'
import pathlib,sys,tarfile
root=pathlib.Path(sys.argv[1]).resolve()
with tarfile.open(sys.argv[2]) as archive:
    for item in archive.getmembers():
        target=(root/item.name).resolve()
        if root not in target.parents or not (item.isfile() or item.isdir()) or item.size > 8*1024*1024: raise SystemExit('无效的模块包')
    archive.extractall(root)
PY
    chmod +x "$STATE/modules/core/"*.sh
  fi
  if [[ ! -f "$STATE/agent.json" ]]; then
    if [[ -n "$TOKEN_FILE" ]]; then
      [[ -s "$TOKEN_FILE" ]] || { echo '接入令牌文件不存在或为空' >&2; exit 1; }
      cp "$TOKEN_FILE" "$TEMP/enrollment.token"
    else
      $YES && { echo '自动安装 Agent 需要 --token-file。' >&2; exit 1; }
      prompt ENROLL_TOKEN '粘贴网页生成的接入令牌' '' true
      printf '%s' "$ENROLL_TOKEN" > "$TEMP/enrollment.token"
      unset ENROLL_TOKEN
    fi
    chmod 600 "$TEMP/enrollment.token"
    python3 "$RELEASE/sentinel_agent.py" --config "$STATE/agent.json" --root "$STATE/modules" --master "$MASTER" --enroll-file "$TEMP/enrollment.token" --register-only
  fi
  cat > /etc/systemd/system/vps-sentinel-agent.service <<EOF
[Unit]
Description=VPS Sentinel outbound Agent
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=$PREFIX
ExecStart=/usr/bin/python3 $PREFIX/current/sentinel_agent.py --config $STATE/agent.json
Restart=on-failure
RestartSec=10
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$STATE
KillMode=control-group
[Install]
WantedBy=multi-user.target
EOF
fi
OLD_CURRENT=$(readlink "$PREFIX/current" || true)
ln -s "$RELEASE" "$PREFIX/.current-new"
mv -Tf "$PREFIX/.current-new" "$PREFIX/current"
SWITCHED=true
systemctl daemon-reload
if [[ "$ROLE" == panel ]]; then
  systemctl enable vps-sentinel-api vps-sentinel-web >/dev/null
  systemctl restart vps-sentinel-api vps-sentinel-web
  HEALTH_HOST="$BIND"
  [[ "$HEALTH_HOST" != 0.0.0.0 ]] || HEALTH_HOST=127.0.0.1
  [[ "$HEALTH_HOST" != :: ]] || HEALTH_HOST=::1
  [[ "$HEALTH_HOST" != *:* ]] || HEALTH_HOST="[$HEALTH_HOST]"
  READY=false
  for attempt in $(seq 1 40); do
    if curl --noproxy '*' -fsS "http://$HEALTH_HOST:$WEB_PORT/api/health" > "$TEMP/health.json" && python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["ok"] is True' "$TEMP/health.json"; then READY=true; break; fi
    sleep 1
  done
  $READY || { echo '服务健康检查失败。' >&2; false; }
  PYTHONPATH="$PREFIX/current/backend" "$PREFIX/current/.venv/bin/python" -m sentinel_api.cli bootstrap --data "$STATE" --username "$USERNAME" --password-file "$TEMP/password" > "$TEMP/bootstrap.json"
  chown -R vps-sentinel:vps-sentinel "$STATE"
else
  systemctl enable vps-sentinel-agent >/dev/null
  STARTED_AT=$(date +%s)
  systemctl restart vps-sentinel-agent
  READY=false
  for attempt in $(seq 1 40); do
    if python3 - "$STATE/agent.heartbeat.json" "$STARTED_AT" <<'PY' 2>/dev/null
import json,sys
assert json.load(open(sys.argv[1]))['last_seen'] >= int(sys.argv[2])
PY
    then READY=true; break; fi
    sleep 1
  done
  $READY || { echo 'Agent 未能完成首次心跳，请检查主控地址和节点日志。' >&2; false; }
  systemctl is-active --quiet vps-sentinel-agent
fi
python3 - "$META" "$ROLE" "$BIND" "$WEB_PORT" "$API_PORT" "$PUBLIC_URL" "$USERNAME" <<'PY'
import json,os,sys
keys=('role','bind','port','api_port','public_url','username')
with open(sys.argv[1],'w') as file: json.dump(dict(zip(keys,sys.argv[2:])),file)
os.chmod(sys.argv[1],0o600)
PY
SWITCHED=false
printf '\n========================================\n安装完成 · VPS Sentinel Dash\n'
if [[ "$ROLE" == panel ]]; then
  ADDRESS="$PUBLIC_URL"
  if [[ -z "$ADDRESS" ]]; then
    ADDRESS_IP="$BIND"
    if [[ "$BIND" == 0.0.0.0 || "$BIND" == :: ]]; then ADDRESS_IP=$(hostname -I | awk '{print $1}'); fi
    [[ "$ADDRESS_IP" != *:* ]] || ADDRESS_IP="[$ADDRESS_IP]"
    ADDRESS="http://${ADDRESS_IP:-127.0.0.1}:$WEB_PORT"
  fi
  printf '面板地址：%s\n管理员：%s\n' "$ADDRESS" "$USERNAME"
  if [[ -s "$TEMP/password" ]]; then printf '初始密码：%s\n首次使用此密码登录后，必须先修改密码。\n' "$(cat "$TEMP/password")"; else printf '管理员密码保持不变。\n'; fi
  printf '前端服务：vps-sentinel-web\n后端服务：vps-sentinel-api\n配置目录：%s\n' "$CONFIG"
  printf '面板使用 HTTP；反代和证书可由你自行配置。\n'
else
  printf 'Agent 已连接：%s\n服务名称：vps-sentinel-agent\n凭证与日志目录：%s\n' "$MASTER" "$STATE"
fi
printf '========================================\n'
