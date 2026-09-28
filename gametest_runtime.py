"""Isolated, local-only Fabric 1.21.1 headless GameTest workload.

The supplied runtime and Java installation are trusted executable inputs, not a
sandbox. Only JARs are copied, never a user's world/configuration/credentials.
"""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import time
import zipfile

import lab
import contracts

AURA_SHA = "2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8"
GAMETEST_SHA = "949085c2c813c00f3a6ccb4b5db0faf6daf690b7f67f08fa8166444352738d88"
PROFILE = Path(__file__).parent / "examples/gametest-runtime-1.21.1.json"


def reject_links(path):
    for part in (path.absolute(), *path.absolute().parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise lab.LabError("Executable/profile symlink or reparse point is unsupported")


def prepare(args):
    reject_links(args.out)
    if args.out.exists():
        raise lab.LabError("GameTest profile must be fresh")
    reject_links(args.java)
    if not args.java.is_file() or args.java.name.lower() not in {"java", "java.exe"}:
        raise lab.LabError("Java executable is missing or not a Java launcher")
    version = lab.jdk_release_version(str(args.java))
    if not (version == "21" or version.startswith("21.")):
        raise lab.LabError("GameTest requires Java 21")
    profile = contracts.load(PROFILE)
    mods = {"mods/aura.jar": args.aura, "mods/fabric-api.jar": args.fabric_api,
            "mods/patchouli.jar": args.patchouli, "mods/fabric-gametest.jar": args.gametest,
            "mods/lab-gametest.jar": args.adapter}
    inventory = profile["artifacts"] + [{"file": "mods/lab-gametest.jar", "sha256": args.adapter_sha256}]
    sources = []
    for entry in inventory:
        source = mods.get(entry["file"], args.runtime / entry["file"])
        reject_links(source)
        if not source.is_file() or lab.sha256(source) != entry["sha256"]:
            raise lab.LabError("Executable input differs from reviewed GameTest profile")
        sources.append(source)
    launcher = args.runtime / "fabric-server-launch.jar"
    with zipfile.ZipFile(launcher) as archive:
        manifest = archive.read("META-INF/MANIFEST.MF").decode().replace("\r\n ", "")
    if "Main-Class: net.fabricmc.loader.impl.launch.server.FabricServerLauncher" not in manifest:
        raise lab.LabError("Expected installed Fabric server launcher, not a downloading installer")
    classpath = next((line[len("Class-Path: "):] for line in manifest.splitlines()
                      if line.startswith("Class-Path: ")), "").split()
    if not classpath:
        raise lab.LabError("Launcher classpath is absent")
    for relative in classpath:
        if (not relative.startswith("libraries/") or ".." in relative.split("/")
                or ":" in relative or "\\" in relative or not (args.runtime / relative).is_file()):
            raise lab.LabError("Launcher requires unavailable local library")
    if not set(classpath).issubset({entry["file"] for entry in inventory}):
        raise lab.LabError("Launcher classpath includes unreviewed libraries")
    args.out.mkdir(parents=True)
    for source, entry in zip(sources, inventory):
        destination = args.out / entry["file"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if lab.sha256(destination) != entry["sha256"]:
            raise lab.LabError("Executable input changed during staging")
    (args.out / "fabric-server-launcher.properties").write_text("serverJar=server.jar\n")
    (args.out / "server.properties").write_text("server-ip=127.0.0.1\nserver-port=0\nonline-mode=false\n")
    lab.write_json(args.out / "runtime-inputs.json", {"schema_version": 1,
                   "profile_sha256": lab.sha256(PROFILE), "artifacts": inventory})


def run(args):
    prepare(args)
    permitted = ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE",
                 "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMSPEC", "HOME")
    env = {key: os.environ[key] for key in permitted if key in os.environ}
    command = [str(args.java.resolve()), "-Xms256m", "-Xmx1536m", "-Djava.awt.headless=true",
               "-Dfabric-api.gametest", "-Dfabric-api.gametest.report-file=evidence/gametest.xml",
               "-Dmc-mod-lab.gametest.blocked=" + str(args.blocked).lower(),
               "-jar", "fabric-server-launch.jar", "nogui"]
    report = {"schema_version": 1, "kind": "fabric-gametest", "artifact_sha256": AURA_SHA,
              "blocked": args.blocked, "status": "incomplete", "exit_code": None,
              "forced_cleanup": False, "memory_limit_mib": 3800,
              "wall_limit_seconds": 180,
              "peak_private_mib": 0, "peak_working_set_mib": 0, "memory_samples": 0,
              "client_check": "not_run", "visual_check": "not_run"}
    process = None
    started = time.monotonic()
    try:
        with (args.out / "stdout.log").open("w") as stdout, (args.out / "stderr.log").open("w") as stderr:
            process = subprocess.Popen(command, cwd=args.out, env=env, stdin=subprocess.PIPE,
                                       stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
            while process.poll() is None:
                try:
                    pids = (process.pid, os.getpid())
                    private = sum(lab.process_private_mb(pid) for pid in pids)
                    working = sum(lab.process_mb(pid) for pid in pids)
                except lab.LabError:
                    if process.poll() is not None:
                        break
                    raise
                report["peak_private_mib"] = round(max(report["peak_private_mib"], private), 1)
                report["peak_working_set_mib"] = round(max(report["peak_working_set_mib"], working), 1)
                report["memory_samples"] += 1
                if max(private, working) > 3800:
                    raise lab.LabError("GameTest workload exceeded memory guard")
                if time.monotonic() - started > 180:
                    raise lab.LabError("GameTest workload timed out")
                time.sleep(.5)
            report["exit_code"] = process.wait(timeout=5)
            report["status"] = "completed"  # XML import, not process exit, establishes test outcomes.
    except (OSError, subprocess.SubprocessError, lab.LabError):
        report["status"] = "incomplete"
    finally:
        if process is not None and process.poll() is None:
            try:
                process.stdin.write(b"stop\n")
                process.stdin.flush()
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                report["forced_cleanup"] = True
                process.kill()
                process.wait(timeout=10)
        if process is not None:
            report["exit_code"] = process.poll()
            process.stdin.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["artifacts"] = [{"file": name, "sha256": lab.sha256(args.out / name)}
                               for name in ("runtime-inputs.json", "evidence/gametest.xml", "gametest-observations.json")
                               if (args.out / name).is_file()]
        lab.write_json(args.out / "lifecycle.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "java", "aura", "fabric-api", "patchouli", "gametest", "adapter", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--blocked", action="store_true")
    parser.add_argument("--adapter-sha256", required=True)
    print(json.dumps(run(parser.parse_args())))
