"""Build a private QA-only chunk observer on one exact command-capable a8 bridge."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BASE_SHA256 = "a8fad2ea5e6f68ebab0900a5bd67f268368cdaa72c7a7641320fd58ffd6be5b0"
HTTP_SOURCE_SHA256 = "b58a3ee6ed73ed81b8c692aafbb8aa7fa164033a35dc45693ad332abee358fb4"
HTTP_CLASS_SHA256 = "4f8bd8bf6d645b821ccdf1f63de63f8a702c169031b4fae09ee1162b5045c0a5"
HTTP_CLASS = "xyz/langyo/minecraft/mcp/common/McpHttpServer.class"
INPUT_CLASS = "xyz/langyo/minecraft/mcp/common/ReflectedInputHandler.class"
HANDLER_CLASS = "xyz/langyo/minecraft/mcp/common/ChunkPresenceHandler.class"
CMD_CLASS = "xyz/langyo/minecraft/mcp/common/McpHttpServer$CmdHandler.class"
PRIVATE_MARKER = "META-INF/mc-mod-lab-private-qa.json"
ROUTE_LINE = '        addAuthenticatedContext("/api/chunk_presence", new ChunkPresenceHandler());\n'
ANCHOR = '        addAuthenticatedContext("/api/screenshot", new ScreenshotHandler());\n'
PATTERN_MATCH = 'if (!(handler instanceof ReflectedInputHandler inputHandler)) {'
JAVA8_CHECK = 'if (!(handler instanceof ReflectedInputHandler)) {'
JAVA8_CAST = '                    ReflectedInputHandler inputHandler = (ReflectedInputHandler) handler;\n'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patched_http(source):
    if (source.count(ANCHOR) != 1 or source.count(PATTERN_MATCH) != 1
            or "ChunkPresenceHandler" in source):
        raise ValueError("private HTTP registration source changed")
    source = source.replace(PATTERN_MATCH, JAVA8_CHECK)
    source = source.replace('                    r = inputHandler.inspectMiningTarget();',
                            JAVA8_CAST + '                    r = inputHandler.inspectMiningTarget();')
    return source.replace(ANCHOR, ROUTE_LINE + ANCHOR)


def accessors(javap, jar_or_classes):
    output = subprocess.run([str(javap), "-c", "-s", "-p", "-classpath",
                             str(jar_or_classes),
                             "xyz.langyo.minecraft.mcp.common.McpHttpServer"],
                            capture_output=True, text=True, check=True).stdout
    methods = {}
    lines = output.splitlines()
    for index, line in enumerate(lines):
        match = re.search(r"\b(access\$[0-9]+)\(", line)
        if not match:
            continue
        descriptor = lines[index + 1].strip()
        if not descriptor.startswith("descriptor: "):
            raise ValueError("private synthetic accessor descriptor unavailable")
        code = []
        for instruction in lines[index + 2:]:
            if instruction.startswith("  }") or (instruction.startswith("  ")
                    and not instruction.startswith("    ") and ";" in instruction):
                break
            if re.match(r"\s+[0-9]+:\s", instruction):
                code.append(re.sub(r"^\s+[0-9]+:\s+", "", instruction).split("//", 1)[0].strip())
        methods[(match.group(1), descriptor)] = tuple(code)
    if not methods or any(not code for code in methods.values()):
        raise ValueError("private synthetic accessor bytecode unavailable")
    return methods


def retained_accessor_targets(javap, base, class_entries):
    targets = set()
    for entry in class_entries:
        class_name = entry.removesuffix(".class").replace("/", ".")
        output = subprocess.run([str(javap), "-c", "-p", "-classpath", str(base),
                                 class_name], capture_output=True, text=True,
                                check=True).stdout
        for name, descriptor in re.findall(r"McpHttpServer\.(access\$[0-9]+):(\S+)", output):
            targets.add((name, "descriptor: " + descriptor))
    if not targets or not any(name == "access$600" for name, _ in targets):
        raise ValueError("retained private handler call targets unavailable")
    return targets


def build(args):
    base = Path(args.private_jar).resolve(strict=True)
    source = Path(args.private_http_source).resolve(strict=True)
    output = Path(args.output).absolute()
    work = Path(args.work).absolute()
    if output.exists() or work.exists() or output.is_relative_to(work) or work.is_relative_to(output):
        raise ValueError("output and work must be fresh separate paths")
    if sha256(base.read_bytes()) != BASE_SHA256:
        raise ValueError("private a8 bridge hash mismatch")
    source_bytes = source.read_bytes()
    if sha256(source_bytes) != HTTP_SOURCE_SHA256:
        raise ValueError("private HTTP source hash mismatch")
    with zipfile.ZipFile(base) as archive:
        original_http = archive.read(HTTP_CLASS)
        if sha256(original_http) != HTTP_CLASS_SHA256:
            raise ValueError("private a8 HTTP class hash mismatch")
        original_input = archive.read(INPUT_CLASS)
        original_cmd = archive.read(CMD_CLASS)
        retained = {name: archive.read(name) for name in archive.namelist()
                    if name.endswith(".class") and name != HTTP_CLASS}
        if PRIVATE_MARKER in archive.namelist():
            raise ValueError("private QA marker already present")
    java_source = patched_http(source_bytes.decode("utf-8"))
    source_dir = work / "source"
    classes = work / "classes"
    source_dir.mkdir(parents=True)
    classes.mkdir()
    http_file = source_dir / "McpHttpServer.java"
    http_file.write_text(java_source, encoding="utf-8")
    handler_file = ROOT / "private-qa/ChunkPresenceHandler.java"
    probe_file = ROOT / "private-qa/ChunkPresenceParserProbe.java"
    classpath = ";".join(map(str, [base, Path(args.gson).resolve(strict=True),
                                   Path(args.minecraft).resolve(strict=True)]))
    jdk = Path(args.jdk_bin).resolve(strict=True)
    subprocess.run([str(jdk / "javac.exe"), "-J-Xmx512m", "--release", "21", "-proc:none",
                    "-cp", classpath, "-d", str(classes), str(handler_file),
                    str(probe_file)], check=True)
    subprocess.run([str(jdk / "javac.exe"), "-J-Xmx512m", "--release", "8", "-proc:none",
                    "-cp", str(classes) + ";" + classpath, "-d", str(classes),
                    str(http_file)], check=True)
    if not (classes / HTTP_CLASS).is_file() or not (classes / HANDLER_CLASS).is_file():
        raise ValueError("private overlay classes were not compiled")
    original_accessors = accessors(jdk / "javap.exe", base)
    replacement_accessors = accessors(jdk / "javap.exe", classes)
    targets = retained_accessor_targets(jdk / "javap.exe", base, retained)
    if original_accessors != replacement_accessors or not targets <= replacement_accessors.keys():
        raise ValueError("retained private handlers would call incompatible synthetic accessors")
    subprocess.run([str(jdk / "java.exe"), "-cp", str(classes) + ";" + classpath,
                    "xyz.langyo.minecraft.mcp.common.ChunkPresenceParserProbe"], check=True)
    marker = {"classification": "private_qa_only", "base_sha256": BASE_SHA256,
              "purpose": "nonloading_chunk_presence", "route": "/api/chunk_presence",
              "command_policy": "existing_private_control_bridge_preserved"}
    resources = work / "resources" / "META-INF"
    resources.mkdir(parents=True)
    (resources / "mc-mod-lab-private-qa.json").write_text(
        json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copy2(base, output)
    package = "xyz/langyo/minecraft/mcp/common/"
    generated = [HTTP_CLASS, HANDLER_CLASS,
                 package + "ChunkPresenceHandler$Request.class",
                 package + "ChunkPresenceHandler$Result.class"]
    if any(not (classes / name).is_file() for name in generated):
        raise ValueError("private overlay class set is incomplete")
    command = [str(jdk / "jar.exe"), "uf", str(output)]
    for name in generated:
        command.extend(["-C", str(classes), name])
    command.extend(["-C", str(work / "resources"), PRIVATE_MARKER])
    subprocess.run(command, check=True)
    with zipfile.ZipFile(output) as archive:
        if (archive.read(INPUT_CLASS) != original_input or archive.read(CMD_CLASS) != original_cmd
                or any(archive.read(name) != contents for name, contents in retained.items())
                or archive.read(HTTP_CLASS) == original_http):
            raise ValueError("private command handler changed unexpectedly")
        if json.loads(archive.read(PRIVATE_MARKER)) != marker or not archive.read(HANDLER_CLASS):
            raise ValueError("private overlay package check failed")
    return sha256(output.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("private-jar", "private-http-source", "gson", "minecraft",
                 "jdk-bin", "output", "work"):
        parser.add_argument("--" + name, required=True)
    try:
        print("Private QA-only overlay SHA-256: " + build(parser.parse_args()))
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        print("Private chunk overlay build failed: " + str(exc), file=sys.stderr)
        sys.exit(1)
