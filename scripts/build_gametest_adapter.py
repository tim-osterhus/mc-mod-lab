"""Compile the narrow 1.21.1 intermediary GameTest adapter from local inputs only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent
AURA_SHA = "2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8"
GAMETEST_SHA = "949085c2c813c00f3a6ccb4b5db0faf6daf690b7f67f08fa8166444352738d88"


def build(args):
    if hashlib.sha256(args.aura.read_bytes()).hexdigest() != AURA_SHA:
        raise ValueError("Expected exact released Aura 0.2.1 bytes")
    if args.work.exists() or args.output.exists():
        raise ValueError("Build destinations must be fresh")
    inputs = [args.minecraft, args.aura, args.gametest, args.fabric_loader, args.gson]
    if hashlib.sha256(args.gametest.read_bytes()).hexdigest() != GAMETEST_SHA:
        raise ValueError("GameTest API differs from reviewed local bytes")
    with zipfile.ZipFile(args.gametest) as archive:
        metadata = json.loads(archive.read("fabric.mod.json"))
    if metadata["id"] != "fabric-gametest-api-v1" or metadata["version"] != "2.0.5+6fc22b9919":
        raise ValueError("Expected reviewed Fabric GameTest API 2.0.5+6fc22b9919")
    args.work.mkdir(parents=True)
    source = ROOT / "gametest-src/lab/gametest/AuraTransferTests.java"
    subprocess.run([str(args.jdk_bin / "javac.exe" if os.name == "nt" else args.jdk_bin / "javac"),
                    "-J-Xmx512m", "--release", "21", "-proc:none", "-cp", os.pathsep.join(map(str, inputs)),
                    "-d", str(args.work), str(source)], check=True, timeout=60)
    metadata = {"schemaVersion": 1, "id": "mc-mod-lab-gametest", "version": "0.1.0",
                "name": "Minecraft Mod Lab GameTest Adapter", "environment": "server",
                "license": "MIT", "entrypoints": {"fabric-gametest": ["lab.gametest.AuraTransferTests"]},
                "depends": {"minecraft": "1.21.1", "java": ">=21", "aura": "*",
                            "fabric-gametest-api-v1": "2.0.5+6fc22b9919"}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", zipfile.ZIP_DEFLATED) as archive:
        def entry(name, data):
            info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
        entry("fabric.mod.json", json.dumps(metadata, sort_keys=True).encode())
        for file in sorted(args.work.rglob("*.class")):
            entry(file.relative_to(args.work).as_posix(), file.read_bytes())
    print(json.dumps({"status": "built", "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "inputs": [hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("jdk-bin", "minecraft", "aura", "gametest", "fabric-loader", "gson", "work", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    build(parser.parse_args())
