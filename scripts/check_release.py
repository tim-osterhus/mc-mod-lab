"""Audit tracked source and the explicit distributable package without live tools."""

import json
from pathlib import Path
import subprocess
import sys

from package_plugin import ROOT, audit_text, package_files

sys.path.insert(0, str(ROOT))
import contracts
import lab


def check_release():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    tracked = [name for name in tracked if name]
    allowed = package_files()
    if set(allowed) - set(tracked):
        raise ValueError("package contains files not staged or tracked")
    forbidden = {".jar", ".mp4", ".mov", ".mkv", ".pem", ".key", ".privatekey", ".p12", ".pfx", ".log"}
    for name in tracked:
        path = Path(name)
        if path.suffix.lower() in forbidden or path.name in {"identity.json", "session-token.txt", ".env"}:
            raise ValueError("forbidden runtime/secret file is tracked")
        if path.name.startswith(".env.") and not path.name.endswith(".example"):
            raise ValueError("non-example environment file is tracked")
        if any(part in {"reports", ".lab-fixtures", "worlds", "saves", "dist", ".venv"} for part in path.parts):
            raise ValueError("generated runtime directory is tracked")
        audit_text((ROOT / path).read_text(encoding="utf-8"), portable=not name.startswith("tests/"))
    manifest = contracts.load(ROOT / ".codex-plugin/plugin.json")
    if manifest["name"] != "mc-mod-lab" or manifest["skills"] != "./skills/" or not manifest["version"]:
        raise ValueError("plugin manifest identity is invalid")
    if "mcpServers" in manifest or "apps" in manifest:
        raise ValueError("alpha package must not advertise an unconfigured transport")
    skill = (ROOT / "skills/mc-mod-lab/SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\nname: mc-mod-lab\n") or "description:" not in skill:
        raise ValueError("skill front matter is invalid")
    template = contracts.load(ROOT / "examples/identity.example.json")
    if set(lab.IDENTITY_REQUIRED) - set(template):
        raise ValueError("identity template lacks required fields")
    for scenario in ("examples/scenario.json", "examples/inventory-scenario.json", "examples/vanilla-book/scenario.json"):
        lab.validate_scenario(contracts.load(ROOT / scenario))
    contracts.validate_file(ROOT / "examples/parity.json", "parity", portable=True)
    from jsonschema import Draft202012Validator
    for schema in (ROOT / "schemas").glob("*.json"):
        Draft202012Validator.check_schema(contracts.load(schema))
    return {"status": "passed", "tracked_files": len(tracked), "package_files": len(allowed),
            "checks": ["schemas", "manifest", "skill", "examples", "secret_patterns", "portable_paths", "file_allowlist"]}


if __name__ == "__main__":
    print(json.dumps(check_release()))
