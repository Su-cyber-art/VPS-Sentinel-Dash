#!/usr/bin/env python3
"""Build a versioned release from committed sources and a production Vue build."""
import argparse
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Su-cyber-art/VPS-Sentinel-Dash"


def git(*arguments):
    return subprocess.check_output(["git", *arguments], cwd=ROOT)


def constant_version(path):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Missing VERSION: " + str(path))


def validate(version):
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        raise ValueError("版本格式必须为 vX.Y.Z")
    versions = {
        "frontend": json.loads((ROOT / "frontend/package.json").read_text())["version"],
        "backend package": tomllib.loads((ROOT / "backend/pyproject.toml").read_text())["project"]["version"],
        "API": constant_version(ROOT / "backend/sentinel_api/config.py"),
        "Agent": constant_version(ROOT / "agent/sentinel_agent.py"),
    }
    if any(value != version[1:] for value in versions.values()):
        raise ValueError("版本标签与组件版本不一致: " + json.dumps(versions))
    return versions


def build(version, output):
    validate(version)
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    dist = ROOT / "frontend/dist"
    if not (dist / "index.html").is_file():
        raise ValueError("先运行 frontend 的 npm ci && npm run build")
    commit = git("rev-parse", "HEAD").decode().strip()
    epoch = int(git("show", "-s", "--format=%ct", "HEAD").decode())
    output.mkdir(parents=True, exist_ok=True)
    files = {}
    for entry in git("ls-tree", "-rz", "HEAD").split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, sha = metadata.decode().split()
        name = raw_path.decode()
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("Unsupported release entry: " + name)
        if any(part in (".git", "runtime", ".venv", "node_modules", "__pycache__") for part in Path(name).parts):
            raise ValueError("Runtime file must not be released: " + name)
        if Path(name).name == ".env" or name.endswith((".sqlite3", ".pyc", ".pem", ".key")):
            raise ValueError("Credential/runtime file must not be released: " + name)
        files[name] = (git("cat-file", "blob", sha), int(mode[-3:], 8))
    marker = b'REF="${SENTINEL_REF:-main}"'
    installer, mode = files["install.sh"]
    if installer.count(marker) != 1:
        raise ValueError("Installer default version marker changed")
    installer = installer.replace(marker, ('REF="${SENTINEL_REF:-' + version + '}"').encode())
    files["install.sh"] = (installer, mode)
    for path in sorted(dist.rglob("*")):
        if path.is_symlink():
            raise ValueError("Unexpected frontend symlink: " + str(path))
        if path.is_file():
            files[path.relative_to(ROOT).as_posix()] = (path.read_bytes(), 0o644)
    # Preserve notices for runtime libraries included in the frontend bundle.
    for package in ("vue", "vue-router", "@vue/shared", "@vue/reactivity", "@vue/runtime-core", "@vue/runtime-dom"):
        license_path = ROOT / "frontend/node_modules" / package / "LICENSE"
        if not license_path.is_file():
            raise ValueError("Missing frontend dependency license: " + package)
        files["THIRD_PARTY_LICENSES/" + package.replace("/", "-") + ".txt"] = (license_path.read_bytes(), 0o644)
    manifest = (json.dumps({"name": "VPS-Sentinel-Dash", "version": version, "commit": commit,
                           "source_url": f"https://github.com/{REPOSITORY}/tree/{version}",
                           "source_date_epoch": epoch}, ensure_ascii=False, indent=2) + "\n").encode()
    files["release.json"] = (manifest, 0o644)
    archive_name = "VPS-Sentinel-Dash-" + version + ".tar.gz"
    prefix = "VPS-Sentinel-Dash-" + version + "/"
    with (output / archive_name).open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for name, (content, mode) in sorted(files.items()):
                    info = tarfile.TarInfo(prefix + name)
                    info.size, info.mode, info.mtime = len(content), mode, epoch
                    archive.addfile(info, io.BytesIO(content))
    (output / "install.sh").write_bytes(installer)
    (output / "sentinel_agent.py").write_bytes(files["agent/sentinel_agent.py"][0])
    (output / "release.json").write_bytes(manifest)
    assets = [archive_name, "install.sh", "sentinel_agent.py", "release.json"]
    checksums = "".join(hashlib.sha256((output / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in assets)
    (output / "SHA256SUMS").write_text(checksums)
    notes = f"""VPS-Sentinel-Dash {version}：首个正式网页面板版本。

- Vue 3 + TypeScript 独立前端、FastAPI 独立后端、主动连接的 Agent。
- 交互式原生安装，systemd 管理；支持 HTTP，由用户自行配置反代与 HTTPS。
- 安装成功后打印随机初始密码，首次登录强制改密，后端 API 同样执行限制。
- 网页执行检测、巡逻、区域访问、本地站点访问、日志读取、数据同步及任务取消。
- 支持批量操作、定时策略、断线重传，以及可选 Telegram 通知。

## 一键安装

```bash
curl -fsSL https://github.com/{REPOSITORY}/releases/download/{version}/install.sh -o sentinel-install.sh && sudo bash sentinel-install.sh
```

此安装器默认固定到 `{version}` 的源码。使用 root 时可省略 `sudo`。

## 发布文件

- `{archive_name}`：完整对应源码、许可证、已构建的 Vue 前端 `frontend/dist/`。
- `install.sh`：固定版本的交互式安装器。
- `sentinel_agent.py`：独立 Agent。
- `release.json`、`SHA256SUMS`：源码提交信息与下载校验。

交互安装会自动准备依赖并构建前端；包内 `frontend/dist/` 也可用于单独部署。

## 验收

本次发版在发布前运行 Python 3.10/3.12 API 与 Agent 测试、Chromium 桌面/手机完整流程，以及 Ubuntu 22.04/24.04 真实交互式安装、哨兵任务、升级、密码恢复和卸载验收。Linux 哨兵脚本测试使用明确的外部 HTTP 夹具，不验证第三方风控评分或养护效果。

源码提交：[{commit[:7]}](https://github.com/{REPOSITORY}/commit/{commit})。
部署详情：[部署文档](https://github.com/{REPOSITORY}/blob/{version}/deploy/README.md)。
"""
    (output / "RELEASE_NOTES.md").write_text(notes)
    # Confirm the exact payload can be unpacked and has the advertised version.
    with tarfile.open(output / archive_name) as archive:
        assert archive.extractfile(prefix + "frontend/dist/index.html").read()
        assert archive.extractfile(prefix + "install.sh").read() == installer
        assert json.load(archive.extractfile(prefix + "release.json"))["commit"] == commit
    subprocess.run(["bash", "-n", str(output / "install.sh")], check=True)
    print(json.dumps({"version": version, "commit": commit, "assets": [*assets, "SHA256SUMS"], "files": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "release-dist")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(validate(args.version), ensure_ascii=False))
    else:
        build(args.version, args.output)
