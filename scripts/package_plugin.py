"""Build a deterministic plugin ZIP from an explicit reviewed file list."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def audit_text(text, portable=True):
    patterns = [r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}",
                r"sk-[A-Za-z0-9_-]{24,}", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                r"Bearer [A-Za-z0-9._-]{32,}"]
    if portable:
        patterns += [r"(?i)[a-z]:[\\/](?:users|_curseforge)[\\/]", r"/(?:home|Users)/[a-zA-Z0-9_-]+/"]
    if any(re.search(pattern, text) for pattern in patterns):
        raise ValueError("publication guard found a secret or machine-local path")


def package_files(root=ROOT):
    root = Path(root).resolve()
    names = json.loads((root / "package-files.json").read_text(encoding="utf-8"))
    if not isinstance(names, list) or not names or len(names) != len(set(names)):
        raise ValueError("invalid package allowlist")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or str(path) != name:
            raise ValueError("package path is not portable")
        source = root / name
        if source.is_symlink() or not source.resolve().is_relative_to(root) or not source.is_file():
            raise ValueError("package file is missing or unsafe")
        audit_text(source.read_text(encoding="utf-8"))
    return sorted(names)


def build_package(out, root=ROOT):
    names = package_files(root)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            info = zipfile.ZipInfo("mc-mod-lab/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            data = (Path(root) / name).read_bytes().replace(b"\r\n", b"\n")
            archive.writestr(info, data)
    return {"status": "packaged", "files": len(names), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_package(args.out)))
