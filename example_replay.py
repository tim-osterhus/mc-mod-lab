"""An explicitly synthetic example exercising the live runner's assertion code."""

from pathlib import Path
import struct
import zlib

import lab


def synthetic_png(color):
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
    width, height = 320, 180
    pixels = (b"\0" + bytes(color) * width) * height
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def replay_example(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    scenario = lab.read_json(Path(__file__).parent / "examples" / "vanilla-book" / "scenario.json")
    lab.validate_scenario(scenario)
    results = {}
    for case, screen in (("baseline", None), ("corrected", "BookViewScreen")):
        folder = out / case
        folder.mkdir()
        report = {"schema_version": 1, "created_at": "2026-09-22T00:00:00+00:00",
                  "evidence_kind": "synthetic", "scenario": scenario["id"],
                  "action": scenario["action"], "expect": scenario["expect"],
                  "status": "captured", "client_check": "action_acknowledged_unverified",
                  "visual_check": "not_reviewed", "control_mode_exit": "acknowledged",
                  "reason": "Synthetic replay only; no client ran and these PNGs are generated test patterns."}
        for label, actual in (("before", None), ("after", screen)):
            path = folder / (label + ".png")
            path.write_bytes(synthetic_png((64, 64, 64) if actual is None else (40, 160, 120)))
            report[label] = {"world": {"world_name": "Synthetic Fixture"},
                             "player": {"gamemode": "creative"}, "screen_class": actual,
                             "screenshot": {"file": path.name, "sha256": lab.sha256(path), "width": 320, "height": 180}}
        try:
            lab.assert_after(scenario, "Synthetic Fixture", report["after"])
        except lab.LabError as error:
            report.update(status=error.status, client_check="failed", reason="Synthetic replay: " + str(error))
        lab.write_report(folder, report)
        results[case] = report["status"]
    if results != {"baseline": "fail", "corrected": "captured"}:
        raise ValueError("replay did not distinguish failure and correction")
    proof = out / "assertions.txt"
    proof.write_text("Synthetic replay: same screen assertion rejected baseline and accepted corrected input.\n", encoding="utf-8")
    manifest = lab.read_json(Path(__file__).parent / "examples" / "parity.json")
    manifest.update(feature="example.vanilla_written_book", requirement="Using the selected written book opens BookViewScreen.")
    manifest["reference"]["source"] = "bundle:synthetic-vanilla-book"
    manifest["implementation"] = {"status": "implemented", "revision": "synthetic-example"}
    manifest["deterministic_test"] = {"status": "pass", "checked_at": "2026-09-22T00:00:00Z", "reviewer": None,
                                       "artifact": {"file": proof.name, "sha256": lab.sha256(proof)}}
    lab.write_json(out / "parity.json", manifest)
    return {"status": "replayed", "evidence_kind": "synthetic", **results, "client_check": "not_run", "visual_check": "not_run"}
