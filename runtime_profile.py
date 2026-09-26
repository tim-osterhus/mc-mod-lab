"""Prepare a fresh, exact-artifact packaged client profile without launching it."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

import contracts
import lab


def _source_file(value):
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise lab.LabError("runtime source must be a local absolute regular file")
    return path.resolve(strict=True)


def _mod_metadata(path):
    try:
        with zipfile.ZipFile(path) as archive:
            value = json.loads(archive.read("fabric.mod.json"))
    except (OSError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise lab.LabError("runtime mod lacks readable Fabric metadata") from exc
    return value.get("id"), value.get("version")


def _replace_unique(args, flag, value):
    positions = [index for index, item in enumerate(args) if item == flag]
    if len(positions) != 1 or positions[0] + 1 >= len(args):
        raise lab.LabError("launcher template must contain one " + flag)
    args[positions[0] + 1] = str(value)


def _launcher_args(template, game_dir, world_name, quickplay):
    try:
        lines = template.read_text(encoding="utf-8").splitlines()
        if not lines or len(lines) > 512 or template.stat().st_size > 256 * 1024:
            raise ValueError("launcher template is empty or oversized")
        args = [json.loads(line) for line in lines]
        if any(not isinstance(item, str) or "\n" in item or "\r" in item for item in args):
            raise ValueError("launcher template has invalid argument")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise lab.LabError("launcher argument template is unsupported") from exc
    if args.count("net.fabricmc.loader.impl.launch.knot.KnotClient") != 1:
        raise lab.LabError("launcher template must use one packaged Fabric KnotClient")
    switches = [index for index, value in enumerate(args) if value in ("-cp", "-classpath", "--class-path")]
    if len(switches) != 1 or switches[0] + 2 >= len(args):
        raise lab.LabError("launcher template must declare one packaged classpath")
    entries = args[switches[0] + 1].split(os.pathsep)
    if (not entries or len(entries) > 256 or
            any(not Path(entry).is_absolute() or Path(entry).suffix.lower() != ".jar"
                for entry in entries) or
            not any(Path(entry).name.startswith("fabric-loader-") for entry in entries)):
        raise lab.LabError("launcher classpath is not a packaged Fabric JAR classpath")
    forbidden = ("/build/classes/", "/build/resources/", "/run/mods/", "/src/", "/test/")
    if any(any(part in entry.replace("\\", "/").lower() for part in forbidden) for entry in entries):
        raise lab.LabError("launcher classpath contains a development output path")
    if any(arg.startswith(("-Dfabric.development=", "-Dfabric.remapClasspathFile=",
                           "-Dmixin.env.remapRefMap=")) for arg in args):
        raise lab.LabError("launcher template enables a development runtime")
    args = [arg for arg in args if not arg.startswith("-Daura.qa.observer.dir=")]
    _replace_unique(args, "--gameDir", game_dir)
    _replace_unique(args, "--quickPlayPath", quickplay)
    _replace_unique(args, "--quickPlaySingleplayer", world_name)
    if any(arg.startswith("@") for arg in args):
        raise lab.LabError("nested Java argument files are unsupported")
    return "\n".join(json.dumps(arg, ensure_ascii=True) for arg in args) + "\n"


def _fixture_hash(world):
    digest = hashlib.sha256()
    for path in sorted(world.rglob("*")):
        if path.is_dir() or path.name == lab.MARKER:
            continue
        relative = path.relative_to(world).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(lab.sha256(path).encode("ascii") + b"\n")
    return digest.hexdigest()


def prepare(manifest_path, out):
    manifest = contracts.load(manifest_path)
    contracts.schema_check(manifest, "runtime-profile")
    out = Path(out)
    if not out.is_absolute() or out.exists() or out.is_symlink():
        raise lab.LabError("runtime output must be a fresh absolute directory")
    java = _source_file(manifest["java_exe"])
    if java.name.lower() not in {"java.exe", "java"}:
        raise lab.LabError("runtime executable must be a Java launcher")
    jdk = lab.jdk_release_version(str(java))
    if not (jdk == "21" or jdk.startswith("21.")):
        raise lab.LabError("runtime requires a Java 21 installation")
    template = _source_file(manifest["launcher_args"])
    if lab.sha256(template) != manifest["launcher_args_sha256"]:
        raise lab.LabError("launcher template hash differs from manifest")
    seed = Path(manifest["seed_save"])
    if not seed.is_absolute() or not seed.is_dir() or seed.is_symlink() or not (seed / "level.dat").is_file():
        raise lab.LabError("runtime seed must be a closed local Minecraft save")
    if out.resolve() == seed.resolve() or out.resolve().is_relative_to(seed.resolve()):
        raise lab.LabError("runtime output cannot be inside seed save")
    roles = [item["role"] for item in manifest["mods"]]
    if roles.count("target") != 1 or roles.count("bridge") != 1:
        raise lab.LabError("runtime needs exactly one target and one bridge mod")
    ids = [item["mod_id"] for item in manifest["mods"]]
    names = [Path(item["path"]).name for item in manifest["mods"]]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        raise lab.LabError("runtime mods contain duplicate IDs or filenames")
    sources = []
    for item in manifest["mods"]:
        path = _source_file(item["path"])
        if path.suffix.lower() != ".jar" or lab.sha256(path) != item["sha256"]:
            raise lab.LabError("runtime mod JAR hash differs from manifest")
        if _mod_metadata(path) != (item["mod_id"], item["mod_version"]):
            raise lab.LabError("runtime mod metadata differs from manifest")
        sources.append((item, path))
    _launcher_args(template, out / "game", "fixture-preflight", out / "quickPlay.json")
    game = out / "game"
    world = lab.fixture_create(seed, game / "saves", manifest["fixture_id"], manifest["world_name"])
    mods = game / "mods"
    mods.mkdir()
    for item, source in sources:
        destination = mods / source.name
        shutil.copy2(source, destination)
        if lab.sha256(destination) != item["sha256"]:
            raise lab.LabError("copied runtime mod hash mismatch", "fail")
    (game / "options.txt").write_text(
        "onboardAccessibility:false\nrenderDistance:4\nsimulationDistance:5\n"
        "maxFps:30\nenableVsync:false\n", encoding="utf-8")
    args = _launcher_args(template, game, world.name, out / "quickPlay.json")
    (out / "java.args").write_text(args, encoding="utf-8")
    result = {"schema_version": 1, "status": "prepared_not_launched", "created_at": lab.now(),
              "fixture_id": manifest["fixture_id"], "world_name": manifest["world_name"],
              "expected_gamemode": manifest["expected_gamemode"],
              "bridge_classification": manifest["bridge_classification"],
              "world_directory": world.name, "fixture_sha256": _fixture_hash(world),
              "java_version": jdk, "java_sha256": lab.sha256(java),
              "launcher_template_sha256": manifest["launcher_args_sha256"],
              "prepared_args_sha256": lab.sha256(out / "java.args"),
              "mods": [{"role": item["role"], "file": source.name, "mod_id": item["mod_id"],
                        "mod_version": item["mod_version"], "sha256": item["sha256"]}
                       for item, source in sources]}
    lab.write_json(out / "profile.json", result)
    return result
