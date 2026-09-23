#!/usr/bin/env python3
"""Small, deliberately bounded Minecraft Mod Lab CLI."""

import argparse
import base64
import binascii
import ctypes
import hashlib
import json
import ntpath
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


MARKER = ".mc-mod-lab-fixture.json"
BRIDGE_VERSION = "0.3.0"
UPSTREAM_SHA256 = "55aab04b1d7ac9203817e071cb83b6d6cf3da7164636867da33877750de64636"
MAX_TOOL_GROUP_MB = 3800
IDENTITY_REQUIRED = ("minecraft_version", "loader", "pid", "port", "world_name", "world_path",
                     "fixture_id", "bridge_jar", "upstream_sha256", "derivative_sha256",
                     "max_group_mb", "tracked_pids", "min_capture_width", "min_capture_height",
                     "game_dir", "launch_log", "expected_gamemode")


class LabError(Exception):
    def __init__(self, message, status="unsupported"):
        super().__init__(message)
        self.status = status


def read_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_identity(identity):
    if identity.get("schema_version") != 1 or any(key not in identity for key in IDENTITY_REQUIRED):
        raise LabError("identity schema is incomplete")
    if (identity["minecraft_version"] != "1.21.1" or identity["loader"] != "fabric"
            or identity.get("bridge_release") != BRIDGE_VERSION):
        raise LabError("this checkpoint supports only Minecraft 1.21.1 Fabric")
    if identity["expected_gamemode"] not in {"creative", "survival", "adventure", "spectator"}:
        raise LabError("expected_gamemode must name a Minecraft game mode")
    if not isinstance(identity["pid"], int) or identity["pid"] <= 0:
        raise LabError("identity PID must be positive")
    if not isinstance(identity["port"], int) or not 1 <= identity["port"] <= 65535:
        raise LabError("identity port is invalid")
    if (not isinstance(identity["tracked_pids"], list) or identity["pid"] not in identity["tracked_pids"]
            or any(not isinstance(pid, int) or pid <= 0 for pid in identity["tracked_pids"])):
        raise LabError("tracked_pids must include the selected client PID")
    if (not isinstance(identity["max_group_mb"], (int, float))
            or not 0 < identity["max_group_mb"] <= MAX_TOOL_GROUP_MB):
        raise LabError("max_group_mb must be positive and at most 3800 MiB")
    informational = identity.get("informational_pids", [])
    if (not isinstance(informational, list)
            or any(not isinstance(pid, int) or pid <= 0 for pid in informational)):
        raise LabError("informational_pids must be a list of positive PIDs")
    if any(not isinstance(identity[key], int) or identity[key] <= 0
           for key in ("min_capture_width", "min_capture_height")):
        raise LabError("minimum capture dimensions must be positive integers")
    world_path = Path(identity["world_path"])
    if not world_path.is_absolute() or not world_path.is_dir():
        raise LabError("world_path must be an existing absolute disposable fixture")
    marker_path = world_path / MARKER
    if not marker_path.is_file():
        raise LabError("world_path lacks a Mod Lab fixture marker")
    marker = read_json(marker_path)
    if marker.get("fixture_id") != identity["fixture_id"] or marker.get("world_name") != identity["world_name"]:
        raise LabError("fixture marker does not match identity")
    game_dir = Path(identity["game_dir"])
    launch_log = Path(identity["launch_log"])
    if not game_dir.is_absolute() or not game_dir.is_dir() or not launch_log.is_file():
        raise LabError("game_dir and launch_log must be existing absolute paths")
    if not world_path.resolve().is_relative_to((game_dir / "saves").resolve()):
        raise LabError("disposable fixture must be inside selected game_dir/saves")
    if not launch_log.resolve().is_relative_to(game_dir.resolve()):
        raise LabError("launch_log must be inside selected game_dir")


def launch_check(identity):
    if platform.system() != "Windows":
        raise LabError("live launch identity check is implemented for Windows only")
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        raise LabError("PowerShell is required to inspect the selected process")
    pid = identity["pid"]
    command = (f'$p=Get-CimInstance Win32_Process -Filter "ProcessId = {pid}"; '
               "if($p){[pscustomobject]@{ProcessId=$p.ProcessId;CommandLine=$p.CommandLine;ExecutablePath=$p.ExecutablePath;"
               "Created=$p.CreationDate.ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress}")
    result = subprocess.run([shell, "-NoProfile", "-Command", command], capture_output=True,
                            text=True, timeout=10, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        raise LabError("selected process command line is unavailable")
    try:
        process = json.loads(result.stdout)
        if process["ProcessId"] != pid or not isinstance(process["CommandLine"], str):
            raise ValueError("unexpected process metadata")
        started = datetime.fromisoformat(process["Created"])
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise LabError("selected process metadata is invalid") from exc
    if started.tzinfo is None:
        raise LabError("selected process metadata is invalid")
    game_dir = str(Path(identity["game_dir"]).resolve()).replace("/", "\\").casefold()
    launched_dir = _launch_game_dir(process["CommandLine"], started)
    if launched_dir != game_dir:
        raise LabError("selected process command line does not identify declared game_dir")
    log = Path(identity["launch_log"])
    if log.stat().st_mtime < started.timestamp() - 120:
        raise LabError("launch log predates selected client process")
    with log.open(encoding="utf-8", errors="replace") as stream:
        start = stream.read(512 * 1024)
    match = re.search(r"Loading Minecraft 1\.21\.1 with Fabric Loader\s+([0-9][A-Za-z0-9.+-]*)", start, re.IGNORECASE)
    if not match:
        raise LabError("fresh launch log does not confirm Minecraft 1.21.1 Fabric")
    return {"minecraft_version": "1.21.1", "fabric_loader_version": match.group(1),
            "jdk_version": jdk_release_version(process.get("ExecutablePath")),
            "version_source": "selected_process_and_fresh_launch_log"}


def jdk_release_version(executable):
    if not isinstance(executable, str) or not Path(executable).is_absolute():
        return "unknown"
    try:
        release = Path(executable).resolve(strict=True).parent.parent / "release"
        with release.open(encoding="utf-8") as stream:
            text = stream.read(65536)
        match = re.search(r'^JAVA_VERSION="([0-9][A-Za-z0-9.+_-]*)"$', text, re.MULTILINE)
        return match.group(1) if match else "unknown"
    except (OSError, UnicodeError):
        return "unknown"


def _launch_game_dir(command_line, started):
    argc = ctypes.c_int()
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    argv = shell32.CommandLineToArgvW(command_line, ctypes.byref(argc))
    if not argv:
        raise LabError("selected process arguments are unavailable")
    try:
        args = [argv[index] for index in range(argc.value)]
    finally:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))
    if not args or ntpath.basename(args[0]).casefold() not in {"java", "java.exe", "javaw.exe"}:
        raise LabError("selected process is not a Java launcher")
    if "--disable-@files" in args:
        raise LabError("Java argument-file expansion is disabled")
    references = [arg[1:] for arg in args[1:] if arg.startswith("@")]
    if len(references) > 1 or any(not reference for reference in references):
        raise LabError("selected process must reference at most one Java argument file")
    if references:
        reference = Path(references[0])
        if not reference.is_absolute() or reference.drive.startswith("\\\\") or reference.is_symlink():
            raise LabError("Java argument file must be a local absolute file")
        try:
            resolved = reference.resolve(strict=True)
            if resolved.drive.startswith("\\\\") or not resolved.is_file():
                raise OSError("not a local file")
            before = resolved.stat()
            if before.st_size > 1024 * 1024 or before.st_mtime > started.timestamp():
                raise OSError("argument file changed after launch or exceeds limit")
            content = resolved.read_text(encoding="utf-8")
            after = resolved.stat()
            if (after.st_size, after.st_mtime_ns, after.st_ino) != (
                    before.st_size, before.st_mtime_ns, before.st_ino):
                raise OSError("argument file changed during inspection")
            file_args = shlex.split(content, comments=True, posix=True)
        except (OSError, UnicodeError, ValueError) as exc:
            raise LabError("Java argument file is unreadable or untrusted") from exc
        if any(arg.startswith("@") or arg == "--disable-@files" for arg in file_args):
            raise LabError("nested Java argument files are unsupported")
        index = next(i for i, arg in enumerate(args) if arg.startswith("@"))
        args = args[:index] + file_args + args[index + 1:]
    positions = [index for index, arg in enumerate(args) if arg == "--gameDir"]
    if len(positions) != 1 or positions[0] + 1 >= len(args):
        raise LabError("selected process must have exactly one --gameDir argument")
    value = args[positions[0] + 1]
    if value.startswith("-") or not Path(value).is_absolute():
        raise LabError("selected process has an invalid --gameDir value")
    try:
        return str(Path(value).resolve(strict=True)).replace("/", "\\").casefold()
    except OSError as exc:
        raise LabError("selected process command line does not identify declared game_dir") from exc


def check_derivative(identity):
    path = Path(identity["bridge_jar"])
    if not path.is_file() or not path.is_absolute():
        raise LabError("bridge_jar must be an existing absolute path")
    for key in ("upstream_sha256", "derivative_sha256"):
        if not re.fullmatch(r"[0-9a-fA-F]{64}", identity[key]):
            raise LabError(key + " must be a SHA-256 hex digest")
    if identity["upstream_sha256"].lower() != UPSTREAM_SHA256:
        raise LabError("upstream JAR hash does not match pinned release asset")
    actual = sha256(path)
    if identity["upstream_sha256"].lower() == identity["derivative_sha256"].lower():
        raise LabError("unmodified upstream JAR is prohibited")
    if actual != identity["derivative_sha256"].lower():
        raise LabError("bridge JAR hash does not match pinned derivative")
    return actual


def listening_socket(pid, port):
    if platform.system() != "Windows":
        raise LabError("live socket ownership check is implemented for Windows only")
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        raise LabError("PowerShell is required to inspect the bridge listener")
    command = (f"@(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue | "
               "Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json -Compress")
    result = subprocess.run([shell, "-NoProfile", "-Command", command], capture_output=True,
                            text=True, timeout=10, check=False)
    if result.returncode != 0:
        raise LabError("could not inspect listening socket")
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise LabError("socket inspection returned invalid data") from exc
    if isinstance(rows, dict):
        rows = [rows]
    if len(rows) != 1 or rows[0].get("LocalAddress") != "127.0.0.1" or rows[0].get("OwningProcess") != pid:
        raise LabError("bridge must have one 127.0.0.1 listener owned by the selected PID")
    return True


def process_mb(pid):
    if platform.system() == "Windows":
        kernel = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi

        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        handle = kernel.OpenProcess(0x1000 | 0x0010, False, pid)
        if not handle:
            raise LabError("tracked process is unavailable")
        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                raise LabError("cannot read tracked process memory")
            return counters.WorkingSetSize / 1048576
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    if platform.system() == "Linux":
        try:
            statm = Path(f"/proc/{pid}/statm").read_text().split()
            return int(statm[1]) * os.sysconf("SC_PAGE_SIZE") / 1048576
        except (OSError, ValueError, IndexError) as exc:
            raise LabError("tracked process is unavailable") from exc
    raise LabError("memory tracking is unsupported on this platform")


def group_mb(identity):
    used = sum(process_mb(pid) for pid in set(identity["tracked_pids"]))
    if used > identity["max_group_mb"]:
        raise LabError("tracked process memory exceeds declared budget", "fail")
    return round(used, 1)


def combined_telemetry_mb(identity):
    pids = set(identity["tracked_pids"]) | set(identity.get("informational_pids", []))
    try:
        return round(sum(process_mb(pid) for pid in pids), 1)
    except LabError:
        return None


def available_mb():
    if platform.system() == "Windows":
        class Memory(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        state = Memory()
        state.dwLength = ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            return round(state.ullAvailPhys / 1048576, 1)
    elif platform.system() == "Linux":
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return round(int(line.split()[1]) / 1024, 1)
    raise LabError("available memory cannot be measured")


def http_json(port, endpoint, payload=None):
    token = os.environ.get("MC_MOD_LAB_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise LabError("MC_MOD_LAB_TOKEN must be a 32+ character per-session secret")
    url = f"http://127.0.0.1:{port}{endpoint}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json",
                                               "Authorization": "Bearer " + token})
    try:
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                raise LabError("bridge returned non-200 status", "fail")
            return json.load(response)
    except (OSError, ValueError) as exc:
        raise LabError("bridge request failed", "fail") from exc


def verify_security(identity):
    token = os.environ.get("MC_MOD_LAB_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise LabError("MC_MOD_LAB_TOKEN must be a 32+ character per-session secret")
    url = f"http://127.0.0.1:{identity['port']}/api/status"
    probes = ({}, {"Authorization": "Bearer " + token, "Origin": "https://example.invalid"})
    for headers in probes:
        try:
            with urlopen(Request(url, headers=headers), timeout=8) as response:
                if response.status == 200:
                    raise LabError("bridge accepted an unauthenticated or Origin-bearing request")
                raise LabError("bridge security probe returned unexpected status")
        except HTTPError as exc:
            if exc.code not in (401, 403):
                raise LabError("bridge security probe returned unexpected status") from exc
        except OSError as exc:
            raise LabError("bridge security probe failed") from exc


def command(identity, name, params=None):
    allowed = {"get_world_info", "get_player_info", "get_screen_buttons", "click", "press_key",
               "click_button_index", "use_item", "enter_control_mode", "exit_control_mode"}
    if name not in allowed:
        raise LabError("command is outside the bounded workflow")
    listening_socket(identity["pid"], identity["port"])
    result = http_json(identity["port"], "/api/cmd", {"cmd": name, "params": params or {}})
    if name == "get_screen_buttons" and result == {"error": "no screen"}:
        return {"screen": None, "buttons": []}
    if isinstance(result, dict) and "error" in result:
        raise LabError("bridge " + name + " returned an error", "fail")
    if name == "click" and (not isinstance(result, dict) or result.get("clicked") is not True):
        raise LabError("bridge click did not activate the target", "fail")
    if isinstance(result, dict) and isinstance(result.get("result"), str):
        value = result["result"].lower()
        if value.startswith(("error", "unknown", "no ", "missing")):
            raise LabError("bridge " + name + " was unsuccessful", "fail")
    return result


def status_check(identity):
    listening_socket(identity["pid"], identity["port"])
    verify_security(identity)
    status = http_json(identity["port"], "/api/status")
    if not isinstance(status, dict):
        raise LabError("bridge status is invalid")
    if (status.get("type") != "minecraft-mod" or status.get("pid") != identity["pid"]
            or status.get("port") != identity["port"]):
        raise LabError("bridge status does not match selected PID and port")
    if status.get("loader") not in ("fabric", "unknown"):
        raise LabError("bridge loader does not match identity")
    return status


def world_check(identity):
    world = command(identity, "get_world_info")
    if not isinstance(world, dict) or world.get("world_name") != identity["world_name"]:
        raise LabError("client world name is absent or does not match identity")
    world_path = world.get("world_path")
    if (not isinstance(world_path, str) or not Path(world_path).is_absolute()
            or Path(world_path).resolve() != Path(identity["world_path"]).resolve()):
        raise LabError("client world path is absent or does not match disposable fixture")
    if str(world.get("gametype", "")).lower() != identity["expected_gamemode"]:
        raise LabError("client world game mode is absent or does not match fixture")
    result = {key: world.get(key) for key in ("world_name", "difficulty", "gametype", "time", "weather")}
    result["gametype"] = str(result["gametype"]).lower()
    return result


def player_check(identity):
    player = command(identity, "get_player_info")
    if (not isinstance(player, dict) or not isinstance(player.get("name"), str)
            or not player["name"].strip()):
        raise LabError("client player name is empty or unavailable")
    if str(player.get("gamemode", "")).lower() != identity["expected_gamemode"]:
        raise LabError("client player game mode is absent or does not match fixture")
    result = {key: player.get(key) for key in ("pos", "dimension", "gamemode")}
    result["gamemode"] = str(result["gamemode"]).lower()
    return result


def screenshot(identity, destination):
    listening_socket(identity["pid"], identity["port"])
    data = http_json(identity["port"], "/api/screenshot")
    uri = data.get("original", "") if isinstance(data, dict) else ""
    if not uri.startswith("data:image/png;base64,"):
        raise LabError("screenshot is absent", "fail")
    try:
        png = base64.b64decode(uri.split(",", 1)[1], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise LabError("screenshot base64 is invalid", "fail") from exc
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise LabError("screenshot is not PNG", "fail")
    width, height = struct.unpack(">II", png[16:24])
    if not width or not height:
        raise LabError("screenshot dimensions are invalid", "fail")
    destination.write_bytes(png)
    if data.get("width") not in (None, width) or data.get("height") not in (None, height):
        raise LabError("screenshot metadata disagrees with PNG dimensions", "fail")
    if (width < identity["min_capture_width"] or height < identity["min_capture_height"]):
        raise LabError("screenshot is smaller than declared minimum; possible cropped framebuffer", "fail")
    return {"file": destination.name, "width": width, "height": height, "sha256": sha256(destination)}


def snapshot(identity, out, label):
    group = group_mb(identity)
    combined = combined_telemetry_mb(identity)
    status_check(identity)
    world = world_check(identity)
    player = player_check(identity)
    buttons = command(identity, "get_screen_buttons")
    shot = screenshot(identity, out / f"{label}.png")
    group_mb(identity)
    button_count = len(buttons) if isinstance(buttons, list) else None
    if isinstance(buttons, dict) and isinstance(buttons.get("buttons"), list):
        widgets = buttons["buttons"]
        button_count = len(widgets)
    else:
        widgets = buttons if isinstance(buttons, list) else []
    signatures = [json.dumps(widget, sort_keys=True) for widget in widgets]
    blank_labels = sum(1 for widget in widgets if isinstance(widget, dict)
                       and not str(widget.get("label") or "").strip())
    return {"world": world,
            "player": player,
            "screen_class": buttons.get("screen") if isinstance(buttons, dict) else None,
            "screen_button_count": button_count,
            "blank_button_labels": blank_labels,
            "duplicate_widgets": len(signatures) - len(set(signatures)),
            "screenshot": shot, "tool_group_working_set_mb": group,
            "combined_telemetry_mb": combined}


def validate_scenario(scenario):
    if scenario.get("schema_version") != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", scenario.get("id", "")):
        raise LabError("scenario id or schema is invalid")
    action = scenario.get("action", {})
    params = action.get("params", {})
    expected_screen = scenario.get("expect", {}).get("after_screen")
    if not isinstance(expected_screen, str) or not expected_screen.strip():
        raise LabError("scenario must declare a nonempty after_screen class")
    if action.get("tool") == "click":
        if set(params) != {"x", "y"} or any(not isinstance(params[k], int) or params[k] < 0 for k in params):
            raise LabError("click requires nonnegative integer x and y")
    elif action.get("tool") == "press_key":
        if set(params) != {"key"} or params["key"] not in {"Enter", "Escape", "E", "Tab"}:
            raise LabError("press_key is outside the allowed key set")
    elif action.get("tool") == "click_button_index":
        if set(params) != {"index"} or not isinstance(params["index"], int) or not 0 <= params["index"] <= 20:
            raise LabError("click_button_index requires index 0 through 20")
    elif action.get("tool") == "use_item":
        if params != {}:
            raise LabError("use_item takes no parameters")
    else:
        raise LabError("only one bounded GUI action is supported")
    return action


def write_report(out, report):
    out.mkdir(parents=True, exist_ok=True)
    report["artifacts"] = [{"file": path.name, "sha256": sha256(path)}
                           for path in (out / "before.png", out / "after.png") if path.is_file()]
    write_json(out / "report.json", report)
    lines = ["# Minecraft Mod Lab capture", "", f"Status: **{report['status']}**", "",
             "Evidence kind: " + report.get("evidence_kind", "unspecified_legacy"), "",
             f"Scenario: `{report.get('scenario', 'unknown')}`", "",
             f"Reason: {report.get('reason', 'none')}", "",
             "Client check: " + report.get("client_check", "not_run"),
             "Visual check: " + report.get("visual_check", "not_reviewed"), ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")


def capture(identity_path, scenario_path, out):
    if out.exists():
        raise LabError("capture output already exists; choose a fresh directory")
    report = {"schema_version": 1, "created_at": now(), "status": "unsupported",
              "evidence_kind": "live",
              "client_check": "not_run", "visual_check": "not_reviewed",
              "bridge": "Minecraft Mod MCP v0.3.0 hardened derivative"}
    try:
        out.mkdir(parents=True, exist_ok=True)
        identity = read_json(identity_path)
        scenario = read_json(scenario_path)
        report["scenario"] = scenario.get("id", "unknown")
        validate_identity(identity)
        action = validate_scenario(scenario)
        report["expect"] = scenario["expect"]
        report["instance"] = {"minecraft_version_claim": identity["minecraft_version"],
                              "loader_claim": identity["loader"], "pid": identity["pid"],
                              "world_name": identity["world_name"], "fixture_id": identity["fixture_id"]}
        report["derivative_sha256"] = check_derivative(identity)
        report["upstream_sha256"] = identity["upstream_sha256"].lower()
        report["available_memory_mb"] = available_mb()
        report["memory_guard"] = {"tool_group_limit_mb": identity["max_group_mb"],
                                  "tool_group_pid_count": len(set(identity["tracked_pids"])),
                                  "informational_pid_count": len(set(identity.get("informational_pids", [])))}
        report["launch_evidence"] = launch_check(identity)
        group_mb(identity)
        status_check(identity)
        report["before"] = snapshot(identity, out, "before")
        if action["tool"] == "click":
            size = report["before"]["screenshot"]
            if action["params"]["x"] >= size["width"] or action["params"]["y"] >= size["height"]:
                raise LabError("click is outside screenshot bounds", "fail")
        report["action"] = {"tool": action["tool"], "params": action["params"]}
        group_mb(identity)
        control = command(identity, "enter_control_mode")
        if not isinstance(control, dict) or control.get("control_mode") is not True:
            raise LabError("bridge did not enter control mode", "fail")
        try:
            command(identity, action["tool"], action["params"])
            expected_screen = scenario.get("expect", {}).get("after_screen")
            if expected_screen:
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    group_mb(identity)
                    screen = command(identity, "get_screen_buttons")
                    if isinstance(screen, dict) and screen.get("screen") == expected_screen:
                        break
                    time.sleep(0.1)
            else:
                time.sleep(0.2)
            report["after"] = snapshot(identity, out, "after")
        finally:
            try:
                command(identity, "exit_control_mode")
                report["control_mode_exit"] = "acknowledged"
            except LabError:
                report["control_mode_exit"] = "failed"
        if report["control_mode_exit"] != "acknowledged":
            raise LabError("bridge did not restore manual control", "fail")
        assert_after(scenario, identity["world_name"], report["after"])
        report["status"] = "captured"
        report["client_check"] = "action_acknowledged_unverified"
        report["reason"] = "GUI semantics, screenshot content, and game-version claim require independent review"
    except LabError as exc:
        report["status"] = exc.status
        report["reason"] = str(exc)
        report["client_check"] = "failed" if exc.status == "fail" else "not_run"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        report["status"] = "unsupported"
        report["reason"] = "input or artifact could not be read"
    write_report(out, report)
    return report


def assert_after(scenario, world_name, after):
    expected = scenario["expect"]
    if after["world"]["world_name"] != expected.get("world_name", world_name):
        raise LabError("after world name does not match expectation", "fail")
    if after["screen_class"] != expected["after_screen"]:
        raise LabError("after screen class does not match expectation", "fail")


def fixture_create(seed, root, fixture_id, world_name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", fixture_id):
        raise LabError("fixture id must be lowercase hyphenated")
    if not seed.is_dir() or seed.is_symlink():
        raise LabError("seed must be a real directory")
    if (root.resolve() == seed.resolve() or root.resolve() in seed.resolve().parents
            or seed.resolve() in root.resolve().parents or root.is_symlink()):
        raise LabError("fixture root and seed must be separate real directories")
    for current, dirs, files in os.walk(seed):
        if any((Path(current) / name).is_symlink() for name in dirs + files):
            raise LabError("seed contains symlinks")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{fixture_id}-{uuid4().hex[:8]}"
    shutil.copytree(seed, destination)
    write_json(destination / MARKER, {"schema_version": 1, "fixture_id": fixture_id,
                                     "world_name": world_name, "created_at": now()})
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description="Minecraft Mod Lab")
    commands = parser.add_subparsers(dest="command", required=True)
    fixture = commands.add_parser("fixture", help="create a fresh disposable world copy")
    fixture.add_argument("create", choices=["create"])
    fixture.add_argument("--seed", type=Path, required=True)
    fixture.add_argument("--root", type=Path, required=True)
    fixture.add_argument("--id", required=True)
    fixture.add_argument("--world-name", required=True)
    doctor = commands.add_parser("doctor", help="check the pinned derivative and selected instance")
    doctor.add_argument("--identity", type=Path, required=True)
    run = commands.add_parser("capture", help="capture one bounded GUI interaction")
    run.add_argument("--identity", type=Path, required=True)
    run.add_argument("--scenario", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    validate = commands.add_parser("validate", help="validate evidence contracts and artifact hashes")
    validate.add_argument("kind", choices=["parity", "report"])
    validate.add_argument("path", type=Path)
    validate.add_argument("--portable", action="store_true")
    replay = commands.add_parser("replay", help="run the synthetic failing/corrected example without Minecraft")
    replay.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "validate":
        from contracts import ContractError, validate_file
        try:
            print(json.dumps(validate_file(args.path, args.kind, args.portable)))
            return 0
        except ContractError as exc:
            print(json.dumps({"status": "invalid", "reason": str(exc)}))
            return 2
        except (OSError, ValueError, KeyError, TypeError):
            print(json.dumps({"status": "invalid", "reason": "evidence contract or artifact validation failed"}))
            return 2
    if args.command == "replay":
        from example_replay import replay_example
        try:
            print(json.dumps(replay_example(args.out)))
            return 0
        except (LabError, OSError, ValueError):
            print(json.dumps({"status": "unsupported", "reason": "replay requires a fresh writable output directory"}))
            return 2
    if args.command == "fixture":
        try:
            print(fixture_create(args.seed, args.root, args.id, args.world_name))
            return 0
        except LabError as exc:
            print(f"unsupported: {exc}", file=sys.stderr)
            return 2
    if args.command == "capture":
        try:
            result = capture(args.identity, args.scenario, args.out)
        except (LabError, OSError):
            print(json.dumps({"status": "unsupported", "reason": "capture requires a fresh writable output directory"}))
            return 2
        print(json.dumps({"status": result["status"], "reason": result.get("reason")}))
        return 0 if result["status"] == "captured" else 2
    try:
        identity = read_json(args.identity)
        validate_identity(identity)
        digest = check_derivative(identity)
        launch = launch_check(identity)
        memory = group_mb(identity)
        status = status_check(identity)
        world = world_check(identity)
        player_check(identity)
        print(json.dumps({"status": "ready", "bridge_version": BRIDGE_VERSION,
                          "derivative_sha256": digest, "pid": identity["pid"],
                          "port": identity["port"], "world_name": world["world_name"],
                          "working_set_mb": memory,
                          "combined_telemetry_mb": combined_telemetry_mb(identity),
                          "tool_group_limit_mb": identity["max_group_mb"],
                          "available_memory_mb": available_mb(),
                          "minecraft_version": launch["minecraft_version"],
                          "fabric_loader_version": launch["fabric_loader_version"],
                          "jdk_version": launch["jdk_version"],
                          "jdk_version_source": "selected_executable_release_file",
                          "fixture_id": identity["fixture_id"], "world_path_verified": True,
                          "capabilities": {"identity": "verified", "authenticated_loopback": "verified",
                                           "capture": "not_exercised_by_doctor", "visual_review": "manual",
                                           "production_runtime": "unsupported"},
                          "bridge_status_version": status.get("version")}, indent=2))
        return 0
    except (LabError, OSError, ValueError, KeyError, TypeError) as exc:
        reason = str(exc) if isinstance(exc, LabError) else "identity or runtime evidence could not be read"
        print(json.dumps({"status": "unsupported", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
