"""Launch one prepared profile as an owned, bounded diagnostic workload."""

import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import subprocess
import threading
import time

import contracts
import lab
import scenario_v2


def _choose_port():
    for port in range(9875, 9699, -1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise lab.LabError("no isolated loopback bridge port is available")


def _owned_loopback_ports(pid):
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if platform.system() != "Windows" or not shell:
        raise lab.LabError("packaged runtime launcher currently requires Windows PowerShell")
    script = ("@(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | "
              f"Where-Object {{ $_.OwningProcess -eq {pid} -and $_.LocalAddress -eq '127.0.0.1' }} | "
              "Select-Object -ExpandProperty LocalPort) | ConvertTo-Json -Compress")
    result = subprocess.run([shell, "-NoProfile", "-Command", script],
                            capture_output=True, text=True, timeout=10, check=False)
    if result.returncode != 0:
        raise lab.LabError("owned loopback listener could not be inspected")
    try:
        values = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise lab.LabError("owned listener query returned invalid data") from exc
    if isinstance(values, int):
        values = [values]
    return [value for value in values if isinstance(value, int) and 1 <= value <= 65535]


def _identity(profile, data, manifest, pid, port):
    game = profile / "game"
    bridge = next(item for item in data["mods"] if item["role"] == "bridge")
    return {"schema_version": 1, "minecraft_version": "1.21.1", "loader": "fabric",
            "pid": pid, "port": port, "world_name": data["world_name"],
            "world_path": str(game / "saves" / data["world_directory"]),
            "expected_gamemode": manifest["expected_gamemode"],
            "fixture_id": data["fixture_id"], "bridge_release": "0.3.0",
            "bridge_jar": str(game / "mods" / bridge["file"]),
            "upstream_sha256": lab.UPSTREAM_SHA256,
            "derivative_sha256": bridge["sha256"],
            "bridge_classification": manifest["bridge_classification"],
            "max_group_mb": 3800, "tracked_pids": [pid, os.getpid()],
            "min_capture_width": 640, "min_capture_height": 360,
            "game_dir": str(game), "launch_log": str(game / "logs" / "latest.log")}


def _wait_ready(profile, data, manifest, process, expected_port, deadline, cancel):
    last_reason = "bridge listener or world not ready"
    while time.monotonic() < deadline:
        if cancel.is_set():
            raise lab.LabError("startup cancelled by runtime memory guard", "fail")
        if process.poll() is not None:
            raise lab.LabError("owned client exited before runtime identity was ready")
        try:
            ports = _owned_loopback_ports(process.pid)
            for port in ports:
                if port != expected_port:
                    continue
                identity = _identity(profile, data, manifest, process.pid, port)
                try:
                    lab.validate_identity(identity)
                    lab.check_derivative(identity)
                    lab.launch_check(identity)
                    lab.status_check(identity)
                    lab.world_check(identity)
                    lab.player_check(identity)
                    return identity
                except lab.LabError as exc:
                    last_reason = str(exc)
        except lab.LabError as exc:
            last_reason = str(exc)
        if cancel.wait(2):
            raise lab.LabError("startup cancelled by runtime memory guard", "fail")
    raise lab.LabError("owned client readiness timed out: " + last_reason[:120])


def _close_owned(process, world):
    if process.poll() is None:
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if not shell:
            process.terminate()
            process.wait(timeout=10)
            return {"status": "fail", "reason": "normal window close unavailable; owned client terminated"}
        script = (f"$p=Get-Process -Id {process.pid} -ErrorAction Stop; "
                  "if (-not $p.CloseMainWindow()) { exit 2 }")
        result = subprocess.run([shell, "-NoProfile", "-Command", script],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode != 0:
            process.terminate()
            process.wait(timeout=10)
            return {"status": "fail", "reason": "normal window close failed; owned client terminated"}
    try:
        code = process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=10)
        return {"status": "fail", "reason": "normal exit timed out; owned client terminated"}
    if code != 0:
        return {"status": "fail", "reason": "owned client exited with a nonzero code"}
    try:
        with lab.closed_seed_lock(world):
            pass
    except lab.LabError:
        return {"status": "fail", "reason": "world save lock remains held after exit"}
    return {"status": "pass", "exit_code": 0}


def _monitor(process, stop, cancel, memory):
    while not stop.is_set() and process.poll() is None:
        try:
            pids = (process.pid, os.getpid())
            working = sum(lab.process_mb(pid) for pid in pids)
            private = sum(lab.process_private_mb(pid) for pid in pids)
            memory["peak_working_set_mib"] = max(memory["peak_working_set_mib"], round(working, 1))
            memory["peak_private_mib"] = max(memory["peak_private_mib"], round(private, 1))
            memory["samples"] += 1
            if max(working, private) > 3800:
                cancel.set()
        except lab.LabError:
            memory["sampling_error"] = True
            cancel.set()
            return
        stop.wait(0.5)


def _probe_public_bridge(identity):
    denied = lab.http_json(identity["port"], "/api/cmd",
                           {"cmd": "execute_command", "params": {"command": "say forbidden"}})
    if denied != {"error": "command is not in public allowlist"}:
        raise lab.LabError("public bridge exposed generic command execution", "fail")
    malformed = lab.http_json(identity["port"], "/api/cmd",
                              {"cmd": "get_world_info", "params": {}, "command": "say forbidden"})
    if malformed != {"error": "invalid public request envelope"}:
        raise lab.LabError("public bridge accepted an unreviewed request envelope", "fail")
    return {"status": "pass", "denied": ["execute_command", "extra_top_level_parameter"]}


def launch(manifest_path, profile_path, scenario_path):
    manifest = contracts.load(manifest_path)
    contracts.schema_check(manifest, "runtime-profile")
    profile = Path(profile_path)
    if not profile.is_absolute() or profile.is_symlink() or not profile.is_dir():
        raise lab.LabError("prepared profile must be an existing absolute directory")
    data = contracts.load(profile / "profile.json")
    if data.get("status") != "prepared_not_launched" or data.get("fixture_id") != manifest["fixture_id"]:
        raise lab.LabError("prepared profile does not match runtime manifest")
    if data.get("bridge_classification") != manifest["bridge_classification"]:
        raise lab.LabError("bridge classification changed after preparation")
    declared_mods = {(item["role"], item["mod_id"]): item for item in manifest["mods"]}
    prepared_mods = {(item["role"], item["mod_id"]): item for item in data["mods"]}
    if set(declared_mods) != set(prepared_mods):
        raise lab.LabError("prepared mods differ from reviewed runtime manifest")
    for key, item in prepared_mods.items():
        declared = declared_mods[key]
        if (item["sha256"] != declared["sha256"]
                or item["mod_version"] != declared["mod_version"]
                or item["file"] != Path(declared["path"]).name):
            raise lab.LabError("prepared mod identity differs from reviewed runtime manifest")
    if (profile / "lifecycle-report.json").exists() or (profile / "game" / "logs" / "latest.log").exists():
        raise lab.LabError("prepared profile was already launched")
    java = Path(manifest["java_exe"])
    if not java.is_file() or lab.sha256(java) != data["java_sha256"]:
        raise lab.LabError("Java launcher changed after profile preparation")
    if lab.sha256(profile / "java.args") != data["prepared_args_sha256"]:
        raise lab.LabError("prepared Java arguments changed after preparation")
    scenario = scenario_v2.validate_scenario(contracts.load(scenario_path))
    target = next(item for item in data["mods"] if item["role"] == "target")
    if (scenario["fixture"] != data["fixture_id"]
            or scenario["runtime"]["mod_id"] != target["mod_id"]
            or scenario["runtime"]["mod_version"] != target["mod_version"]
            or scenario["runtime"]["artifact_sha256"] != target["sha256"]):
        raise lab.LabError("scenario does not match prepared packaged artifact and fixture")
    for item in data["mods"]:
        jar = profile / "game" / "mods" / item["file"]
        if jar.is_symlink() or not jar.is_file() or lab.sha256(jar) != item["sha256"]:
            raise lab.LabError("prepared mod changed before launch")
    world = profile / "game" / "saves" / data["world_directory"]
    if not world.is_dir() or (world / "session.lock").exists():
        raise lab.LabError("prepared world is missing or already locked")
    output = {"schema_version": 1, "created_at": lab.now(), "status": "unsupported",
              "bridge_classification": manifest["bridge_classification"],
              "artifact_sha256": target["sha256"], "fixture_sha256": data["fixture_sha256"],
              "scenario": scenario["id"], "scenario_status": "not_run",
              "public_bridge_security": {"status": "not_run"},
              "cleanup": {"status": "not_run"},
              "memory": {"working_set_limit_mib": 3800, "peak_working_set_mib": 0,
                         "peak_private_mib": 0, "samples": 0, "sampling_error": False,
                         "hard_cap": False, "interval_seconds": 0.5}}
    token = secrets.token_hex(32)
    port = _choose_port()
    previous = os.environ.get("MC_MOD_LAB_TOKEN")
    os.environ["MC_MOD_LAB_TOKEN"] = token
    permitted_env = ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE",
                     "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMSPEC", "HOME", "JAVA_HOME")
    env = {key: os.environ[key] for key in permitted_env if key in os.environ}
    env["MC_MOD_LAB_TOKEN"] = token
    env["MC_MCP_PORT"] = str(port)
    process = None
    stop = threading.Event()
    cancel = threading.Event()
    monitor = None
    try:
        with (profile / "stdout.log").open("w", encoding="utf-8") as stdout, \
             (profile / "stderr.log").open("w", encoding="utf-8") as stderr:
            flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            process = subprocess.Popen([str(java), "@" + str(profile / "java.args")],
                                       cwd=profile / "game", env=env, stdout=stdout,
                                       stderr=stderr, creationflags=flags)
            monitor = threading.Thread(target=_monitor, args=(process, stop, cancel, output["memory"]),
                                       daemon=True)
            monitor.start()
            identity = _wait_ready(profile, data, manifest, process, port,
                                   time.monotonic() + 180, cancel)
            if manifest["bridge_classification"] == "public_reviewed":
                output["public_bridge_security"] = _probe_public_bridge(identity)
            lab.write_json(profile / "identity.json", identity)
            artifact = profile / "game" / "mods" / target["file"]
            result = scenario_v2.run(profile / "identity.json", scenario_path, artifact,
                                     profile / "scenario-evidence", cancel_event=cancel)
            output["scenario_status"] = result["status"]
            output["status"] = result["status"]
    except (lab.LabError, OSError, subprocess.SubprocessError) as exc:
        output["status"] = exc.status if isinstance(exc, lab.LabError) else "unsupported"
        output["reason"] = (str(exc) if isinstance(exc, lab.LabError)
                            else "owned packaged runtime could not complete")[:240]
    finally:
        if process is not None:
            try:
                output["cleanup"] = _close_owned(process, world)
            except (OSError, subprocess.SubprocessError):
                output["cleanup"] = {"status": "fail", "reason": "owned client could not be closed"}
        stop.set()
        if monitor is not None:
            monitor.join(timeout=5)
        if previous is None:
            os.environ.pop("MC_MOD_LAB_TOKEN", None)
        else:
            os.environ["MC_MOD_LAB_TOKEN"] = previous
        if cancel.is_set() or output["cleanup"]["status"] == "fail":
            output["status"] = "fail"
        if output["status"] == "pass" and manifest["bridge_classification"] == "private_diagnostic":
            output["status"] = "diagnostic_only"
        lab.write_json(profile / "lifecycle-report.json", output)
    return output
