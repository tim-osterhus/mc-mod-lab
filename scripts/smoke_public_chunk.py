"""Owned-client, read-only public chunk-presence gate; no OBS or actor access."""

import argparse
import http.client
import json
import os
from pathlib import Path
import time

import lab
import runtime_launch
import scenario_v2


BRIDGE_SHA256 = "fa97fbee19beb09c1a1becde8f5a91a7b40d77ae5eb2923dfe6fa6f37f3fa177"
LOCAL = {"type": "chunk_presence", "x": 1, "y": 161, "z": 2}
FAR = {"type": "chunk_presence", "x": 1000000, "y": 64, "z": 1000000}


def raw_status(identity, method, payload, authorization, origin=False):
    lab.listening_socket(identity["pid"], identity["port"])
    token = os.environ.get("MC_MOD_LAB_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise lab.LabError("bounded chunk probe token unavailable", "fail")
    headers = {"Content-Type": "application/json"}
    if authorization == "valid":
        headers["Authorization"] = "Bearer " + token
    elif authorization == "wrong":
        headers["Authorization"] = "Bearer " + token + "x"
    elif authorization != "missing":
        raise lab.LabError("invalid security control", "fail")
    if origin:
        headers["Origin"] = "https://example.invalid"
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", identity["port"], timeout=8)
    try:
        connection.request(method, "/api/scenario/v2", body=body, headers=headers)
        response = connection.getresponse()
        response.read(8192)
        return response.status
    finally:
        connection.close()


def run_probe(identity, _artifact, run, cancel):
    report = {"status": "fail", "kind": "public_chunk_presence_technical_gate",
              "client_pid": identity["pid"], "observations": [], "negative_controls": []}
    try:
        if identity.get("expected_gamemode") != "survival" or lab.check_derivative(identity) != BRIDGE_SHA256:
            raise lab.LabError("public chunk probe artifact differs", "fail")
        dimension = None
        for label, spec in (("local_before", LOCAL), ("far_before", FAR),
                            ("local_after", LOCAL), ("far_after", FAR)):
            if cancel.is_set():
                raise lab.LabError("runtime memory guard cancelled chunk probe", "fail")
            if label == "local_after":
                time.sleep(1)
            envelope, value = scenario_v2._scenario_observation(identity, spec)
            report["observations"].append({"label": label, "request": spec,
                                           "envelope": envelope, "validated": value})
            if dimension is None:
                dimension = value["dimension"]
            if value["dimension"] != dimension:
                raise lab.LabError("chunk probe dimension changed", "fail")
            if value["hasChunkAt"] is not label.startswith("local"):
                raise lab.LabError("chunk presence local/far control failed", "fail")
        valid = {"schema_version": 2, "kind": "observe", "name": "chunk_presence",
                 "params": {key: FAR[key] for key in ("x", "y", "z")}}
        controls = (("missing_token", "POST", valid, "missing", False, {401, 403}),
                    ("wrong_token", "POST", valid, "wrong", False, {401, 403}),
                    ("origin", "POST", valid, "valid", True, {401, 403}),
                    ("get_method", "GET", None, "valid", False, {405}),
                    ("boolean_x", "POST", {**valid, "params": {**valid["params"], "x": True}},
                     "valid", False, {400}),
                    ("float_x", "POST", {**valid, "params": {**valid["params"], "x": 1.0}},
                     "valid", False, {400}),
                    ("extra_field", "POST", {**valid, "params": {**valid["params"], "extra": 1}},
                     "valid", False, {400}),
                    ("out_of_range", "POST", {**valid, "params": {**valid["params"], "x": 30000001}},
                     "valid", False, {400}))
        for name, method, payload, authorization, origin, expected in controls:
            if cancel.is_set():
                raise lab.LabError("runtime memory guard cancelled chunk probe", "fail")
            status = raw_status(identity, method, payload, authorization, origin)
            report["negative_controls"].append({"name": name, "http_status": status})
            if status not in expected:
                raise lab.LabError("public chunk security or parser control failed", "fail")
        _, final = scenario_v2._scenario_observation(identity, FAR)
        report["far_final"] = final
        if final["dimension"] != dimension or final["hasChunkAt"] is not False:
            raise lab.LabError("far chunk changed after read-only controls", "fail")
        report["entity_ticking_positive_observed"] = any(
            row["validated"]["entityTicking"] is True for row in report["observations"])
        report["status"] = "inconclusive"
        report["reason"] = "raw passive predicates and security controls require independent review"
    except (lab.LabError, OSError, ValueError, KeyError, TypeError) as exc:
        report["reason"] = str(exc)[:180]
    finally:
        lab.write_json(run / "public-chunk-presence-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description="Owned public chunk-presence technical gate")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = runtime_launch.launch(args.manifest, args.profile, args.scenario,
                                       technical_smoke=run_probe)
        print(json.dumps(report))
        return 0 if report["status"] == "inconclusive" else 2
    except (lab.LabError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "fail", "reason": str(exc)[:180]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
