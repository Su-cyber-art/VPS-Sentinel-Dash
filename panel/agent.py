#!/usr/bin/env python3
"""Outbound-only IP Sentinel agent; Python 3.9+, no pip dependencies."""
import argparse
import concurrent.futures
import fcntl
import ipaddress
import json
import logging
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen, build_opener, ProxyHandler

VERSION = "0.1.0"
MODULES = {"google": "mod_google.sh", "trust": "mod_trust.sh", "quality": "mod_quality.sh"}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".sentinel-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(data, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def check_master(master):
    url = urlparse(master)
    if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise ValueError("Master must be an origin such as https://sentinel.example.com")
    local = url.hostname in ("localhost", "127.0.0.1", "::1")
    if not url.hostname or (url.scheme != "https" and not (local and url.scheme == "http")):
        raise ValueError("Remote agents require HTTPS; HTTP is allowed only on loopback")
    return master.rstrip("/")


def call(master, path, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(master + path, json.dumps(payload).encode(), headers, method="POST")
    opener = build_opener(ProxyHandler({})).open if urlparse(master).hostname in ("localhost", "127.0.0.1", "::1") else urlopen
    with opener(request, timeout=20) as response:
        return json.load(response)


def snapshot():
    disk = shutil.disk_usage("/")
    result = {"hostname": socket.gethostname(), "platform": platform.system() + " " + platform.release(),
              "architecture": platform.machine(), "cpu_count": os.cpu_count(),
              "load_1m": round(os.getloadavg()[0], 2), "disk_used_percent": round(disk.used / disk.total * 100, 1),
              "disk_total_gb": round(disk.total / 1024 ** 3, 1), "memory_used_percent": None,
              "memory_total_mb": None, "collected_at": time.time()}
    try:
        mem = {line.split(":")[0]: int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()}
        result.update(memory_total_mb=round(mem["MemTotal"] / 1024),
                      memory_used_percent=round(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]), 1))
    except (OSError, ValueError, KeyError):
        pass
    return result


def request_probe(name, url):
    start = time.monotonic()
    try:
        request = Request(url, headers={"User-Agent": "IP-Sentinel/" + VERSION})
        with urlopen(request, timeout=12) as response:
            text = response.read(512000).decode("utf-8", errors="replace")
            return {"name": name, "http_status": response.status, "reachable": True,
                    "latency_ms": round((time.monotonic() - start) * 1000), "text": text}
    except HTTPError as error:
        return {"name": name, "http_status": error.code, "reachable": False,
                "latency_ms": round((time.monotonic() - start) * 1000), "error": "HTTP " + str(error.code)}
    except Exception as error:
        return {"name": name, "reachable": False, "error": str(error)[:300]}


def network_probe():
    targets = [("Cloudflare", "https://www.cloudflare.com/cdn-cgi/trace"),
               ("Google", "https://www.google.com/generate_204"),
               ("YouTube", "https://www.youtube.com/premium")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda x: request_probe(*x), targets))
    result = {"checks": [], "public_ip": None, "country": None, "youtube_region": None,
              "note": "HTTP 可达性与页面地区信号，不等同于账号可用性、完整流媒体解锁或信誉评分。"}
    for probe in results:
        text = probe.pop("text", "")
        if probe["name"] == "Cloudflare" and text:
            values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
            try:
                result["public_ip"] = str(ipaddress.ip_address(values.get("ip", "")))
            except ValueError:
                pass
            country = values.get("loc", "")
            result["country"] = country if re.fullmatch("[A-Z]{2}", country) else None
        if probe["name"] == "YouTube" and text:
            found = re.search(r'"(?:INNERTUBE_CONTEXT_GL|countryCode|contentRegion)"\s*:\s*"([A-Z]{2})"', text)
            result["youtube_region"] = found[1] if found else None
        result["checks"].append(probe)
    return result


class Agent:
    def __init__(self, config_path):
        self.config_path = Path(config_path)
        self.config = json.loads(self.config_path.read_text())
        self.master = check_master(self.config["master"])
        self.root = Path(self.config.get("root", "/opt/ip_sentinel")).resolve()
        self.state_path = self.config_path.with_suffix(".state.json")
        self.policy = {}
        self.started = time.monotonic()
        self.future = None
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        if self.state.get("active") and not self.state.get("pending"):
            job = self.state["active"]
            self.state["pending"] = {"id": job["id"], "lease": job["lease"], "ok": False,
                                     "result": {"error": "Agent 在执行期间重启；为避免重复操作，任务未重新执行"}}
            atomic_json(self.state_path, self.state)

    def capabilities(self):
        caps = ["snapshot", "network", "logs"]
        for key, filename in MODULES.items():
            if (self.root / "core" / filename).is_file() and platform.system() == "Linux":
                caps.append(key)
        return caps

    def sync_policy(self, policy):
        self.policy = policy
        if not (self.root / "core").is_dir():
            return
        config_path = self.root / "config.conf"
        config = {}
        if config_path.exists():
            for line in config_path.read_text().splitlines():
                match = re.fullmatch(r"([A-Z_][A-Z_0-9]*)=(.*)", line)
                if match:
                    try:
                        parts = shlex.split(match[2])
                        config[match[1]] = parts[0] if len(parts) == 1 else ""
                    except ValueError:
                        continue
        region_path = policy.get("region_path", "US/CA/Los_Angeles.json")
        base = (self.root / "data" / "regions").resolve()
        target = (base / region_path).resolve()
        if base not in target.parents or target.suffix != ".json":
            raise ValueError("Invalid region path")
        if not target.exists():
            raise ValueError("Region data is missing; reinstall the modules bundle")
        region = json.loads(target.read_text())
        google = region["google_module"]
        config.update(INSTALL_DIR=str(self.root), LOG_FILE=str(self.root / "logs" / "sentinel.log"),
                      AGENT_VERSION=VERSION, REGION_CODE=region_path.split("/")[0],
                      REGION_NAME=region["region_name"], REGION_JSON_PATH=str(target),
                      BASE_LAT=str(google["base_lat"]), BASE_LON=str(google["base_lon"]),
                      LANG_PARAMS=google["lang_params"], LANG_ACCEPT="en-US,en;q=0.9",
                      VALID_URL_SUFFIX=google.get("valid_url_suffix", "com"),
                      ENABLE_GOOGLE=str(policy.get("google", False)).lower(),
                      ENABLE_TRUST=str(policy.get("trust", False)).lower())
        config.setdefault("IP_PREF", "4")
        config.setdefault("PUBLIC_IP", self.state.get("network", {}).get("public_ip") or "Unknown")
        config.setdefault("BIND_IP", "")
        (self.root / "logs").mkdir(exist_ok=True)
        content = "\n".join(k + "=" + shlex.quote(str(v)) for k, v in sorted(config.items())) + "\n"
        if not config_path.exists() or config_path.read_text() != content:
            fd, temp = tempfile.mkstemp(prefix=".config-", dir=self.root)
            with os.fdopen(fd, "w") as file:
                file.write(content)
            os.replace(temp, config_path)

    def logs(self):
        path = self.root / "logs" / "sentinel.log"
        if not path.exists():
            return {"text": "尚无养护模块日志。Agent 心跳和任务记录可在网页中查看。"}
        with path.open("rb") as file:
            file.seek(max(0, path.stat().st_size - 48000))
            text = file.read().decode("utf-8", errors="replace")
        return {"text": "\n".join(text.splitlines()[-180:])}

    def execute(self, job, policy):
        action = job["action"]
        try:
            if action == "snapshot":
                result = snapshot()
            elif action == "network":
                result = network_probe()
                if not any(c.get("reachable") for c in result["checks"]):
                    return {"ok": False, "result": result}
            elif action == "logs":
                result = self.logs()
            elif action in MODULES:
                if action in ("google", "trust") and not policy.get(action):
                    raise ValueError("此实验模块未启用")
                script = self.root / "core" / MODULES[action]
                if action not in self.capabilities():
                    raise ValueError("模块未安装，或宿主系统不是 Linux")
                env = dict(os.environ, SENTINEL_ROOT=str(self.root), SENTINEL_WEB_MODE="1")
                with tempfile.TemporaryFile() as output:
                    process = subprocess.Popen(["bash", str(script)], stdout=output, stderr=subprocess.STDOUT,
                                               env=env, start_new_session=True)
                    try:
                        code = process.wait(timeout=1200)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                        raise ValueError("模块执行超过 20 分钟，已终止")
                    size = output.tell()
                    output.seek(max(0, size - 48000))
                    text = output.read().decode("utf-8", errors="replace")
                if action == "quality" and code == 0:
                    try:
                        result = {"report": json.loads(text), "source": "xykt/IPQuality"}
                    except ValueError:
                        result = {"text": text, "exit_code": code}
                else:
                    result = {"text": text or self.logs()["text"], "exit_code": code}
                return {"ok": code == 0, "result": result}
            else:
                raise ValueError("Unsupported action")
            return {"ok": True, "result": result}
        except Exception as error:
            return {"ok": False, "result": {"error": str(error)[:1000]}}

    def tick(self):
        if self.future and self.future.done():
            outcome = self.future.result()
            job = self.state["active"]
            self.state["pending"] = dict(outcome, id=job["id"], lease=job["lease"])
            if job["action"] == "network" and outcome["ok"]:
                self.state["network"] = outcome["result"]
            self.future = None
            atomic_json(self.state_path, self.state)
        if self.state.get("pending"):
            call(self.master, "/api/agent/result", self.state["pending"], self.config["token"])
            self.state.pop("pending", None)
            self.state.pop("active", None)
            atomic_json(self.state_path, self.state)
        metrics = snapshot()
        metrics["agent_uptime_seconds"] = round(time.monotonic() - self.started)
        metrics["public_ip"] = self.state.get("network", {}).get("public_ip")
        metrics["country"] = self.state.get("network", {}).get("country")
        metrics["youtube_region"] = self.state.get("network", {}).get("youtube_region")
        payload = {"metrics": metrics, "hostname": socket.gethostname(), "platform": platform.system(),
                   "version": VERSION, "capabilities": self.capabilities(), "active_job": self.state.get("active")}
        response = call(self.master, "/api/agent/heartbeat", payload, self.config["token"])
        # Persist a received lease before config I/O so setup failures are reportable.
        if not self.state.get("active"):
            job = response.get("job")
            if job:
                self.state["active"] = job
                atomic_json(self.state_path, self.state)
            try:
                self.sync_policy(response["policy"])
            except Exception as error:
                if job:
                    self.state["pending"] = {"id": job["id"], "lease": job["lease"], "ok": False,
                                             "result": {"error": "策略同步失败: " + str(error)[:500]}}
                    atomic_json(self.state_path, self.state)
                raise
            if job:
                self.future = self.executor.submit(self.execute, job, dict(self.policy))
                logging.info("Started %s task %s", job["action"], job["id"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="./runtime/agent.json")
    parser.add_argument("--master")
    parser.add_argument("--enroll", help="Single-use enrollment token (prefer --enroll-file)")
    parser.add_argument("--enroll-file", help="Read token from a protected file and delete it after enrollment")
    parser.add_argument("--root", default="/opt/ip_sentinel")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    path = Path(args.config)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = open(str(path) + ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("An agent is already using this config")
    if not path.exists():
        token = Path(args.enroll_file).read_text().strip() if args.enroll_file else args.enroll
        if not args.master or not token:
            parser.error("First start requires --master and --enroll-file/--enroll")
        master = check_master(args.master)
        credentials = call(master, "/api/agent/enroll", {"token": token})
        atomic_json(path, dict(credentials, master=master, root=str(Path(args.root).resolve())))
        if args.enroll_file:
            Path(args.enroll_file).unlink()
        logging.info("Agent registered as %s", credentials["id"])
    agent = Agent(path)
    try:
        while True:
            try:
                agent.tick()
            except HTTPError as error:
                logging.warning("Control plane returned HTTP %s", error.code)
                if error.code in (401, 403):
                    raise SystemExit("Agent credential revoked or invalid; re-enroll this node")
            except Exception as error:
                logging.warning("Heartbeat failed: %s", str(error)[:300])
            time.sleep(15)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
