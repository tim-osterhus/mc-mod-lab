"""Install and discover the plugin using only disposable child-process config."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import zipfile

from package_plugin import ROOT, build_package


def config_fingerprints():
    paths = [Path.home() / ".codex/config.toml", Path.home() / ".agents/plugins/marketplace.json"]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None for path in paths}


def run_checked(command, cwd, env):
    run = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=45)
    if run.returncode:
        raise RuntimeError("isolated command failed: " + command[1])
    return run.stdout


def discover_skill(codex, workspace, env):
    replies = queue.Queue()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        process = subprocess.Popen([codex, "app-server", "--stdio"], cwd=workspace, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding="utf-8")
        def read():
            for line in process.stdout:
                try:
                    replies.put(json.loads(line))
                except json.JSONDecodeError:
                    pass
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        def request(identifier, method, params):
            process.stdin.write(json.dumps({"id": identifier, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            while True:
                response = replies.get(timeout=40)
                if response.get("id") == identifier:
                    if "error" in response:
                        raise RuntimeError("isolated app-server rejected " + method)
                    return response["result"]
        try:
            request(1, "initialize", {"clientInfo": {"name": "mc_mod_lab_smoke", "version": "0.1.0"}})
            process.stdin.write(json.dumps({"method": "initialized"}) + "\n")
            process.stdin.flush()
            result = request(2, "skills/list", {"cwds": [str(workspace)], "forceReload": True})
            matches = [skill for item in result["data"] for skill in item["skills"]
                       if skill["name"].split(":")[-1] == "mc-mod-lab" and skill["enabled"]]
            if len(matches) != 1:
                raise RuntimeError("installed skill was not discovered exactly once")
            return Path(matches[0]["path"])
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
            reader.join(timeout=2)
            process.stdout.close()


def smoke(codex):
    codex = str(Path(codex).resolve(strict=True))
    if os.name == "nt" and not codex.lower().endswith(".exe"):
        raise ValueError("pass the native codex.exe so the smoke owns its child process")
    before = config_fingerprints()
    with tempfile.TemporaryDirectory(prefix="mc-mod-lab-smoke-") as folder:
        root = Path(folder).resolve()
        profile, config, workspace = root / "profile", root / "config", root / "workspace"
        for path in (profile, config, workspace, root / "temp", root / "appdata", root / "localappdata"):
            path.mkdir()
        # These overrides apply only to child processes; no host configuration is changed.
        env = {key: value for key, value in os.environ.items()
               if key.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC"}}
        env.update(CODEX_HOME=str(config), HOME=str(profile), USERPROFILE=str(profile),
                   APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "localappdata"),
                   TEMP=str(root / "temp"), TMP=str(root / "temp"))
        archive = root / "plugin.zip"
        package = build_package(archive)
        market = root / "marketplace"
        plugins = market / "plugins"
        plugins.mkdir(parents=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(plugins)
        catalog = market / ".agents/plugins/marketplace.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({"name": "mc-mod-lab-smoke", "plugins": [{
            "name": "mc-mod-lab", "source": {"source": "local", "path": "./plugins/mc-mod-lab"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Developer Tools"}]}), encoding="utf-8")
        version = run_checked([codex, "--version"], workspace, env).strip()
        run_checked([codex, "plugin", "marketplace", "add", str(market), "--json"], workspace, env)
        run_checked([codex, "plugin", "add", "mc-mod-lab@mc-mod-lab-smoke", "--json"], workspace, env)
        skill = discover_skill(codex, workspace, env)
        if not skill.resolve().is_relative_to(config.resolve()):
            raise RuntimeError("skill was not loaded from isolated installed cache")
        installed = skill.parents[2]
        proof = workspace / "replay"
        run_checked([sys.executable, str(installed / "lab.py"), "replay", "--out", str(proof)], workspace, env)
        run_checked([sys.executable, str(installed / "lab.py"), "validate", "parity", str(proof / "parity.json"), "--portable"], workspace, env)
        if config_fingerprints() != before:
            raise RuntimeError("host config changed during isolated smoke")
        return {"status": "passed", "codex_version": version, "package_sha256": package["sha256"],
                "installed_skill_discovered": True, "installed_cli_replay": "passed",
                "host_config_unchanged": True, "model_or_game_started": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True)
    print(json.dumps(smoke(parser.parse_args().codex)))
