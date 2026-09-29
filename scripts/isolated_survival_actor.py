"""Small no-network child for the bounded pixel/action actor protocol."""

import argparse
import base64
import binascii
import json
import os
import socket
import sys
import time


MAX_LINE = 12 * 1024 * 1024
MAX_STEPS = 1200
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def exchange(request):
    sys.stdout.write(json.dumps(request, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    line = sys.stdin.readline(MAX_LINE + 1)
    if not line or len(line) > MAX_LINE:
        raise ValueError("actor response unavailable")
    response = json.loads(line)
    if type(response) is not dict:
        raise ValueError("actor response invalid")
    return response


def probe(files, port):
    readable = []
    for path in files:
        try:
            with open(path, "rb") as source:
                source.read(1)
            readable.append(True)
        except OSError:
            readable.append(False)
    with socket.socket() as connection:
        connection.settimeout(1)
        bridge_reachable = connection.connect_ex(("127.0.0.1", port)) == 0
    result = {"files_readable": readable,
              "token_present": "MC_MOD_LAB_TOKEN" in os.environ,
              "bridge_reachable": bridge_reachable}
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0 if not any(readable) and not result["token_present"] and not bridge_reachable else 2


def broker_probe():
    for request in ({"op": "observe", "name": "chunk_presence", "x": 0, "y": 64, "z": 0},
                    {"op": "execute_command", "command": "say denied"},
                    {"op": "pulse", "key": "forward", "milliseconds": True}):
        if exchange(request) != {"accepted": False}:
            return 2
    return 0


def act():
    for _ in range(MAX_STEPS):
        frame = exchange({"op": "frame"})
        if set(frame) != {"png"} or type(frame["png"]) is not str:
            return 2
        try:
            png = base64.b64decode(frame["png"], validate=True)
        except (ValueError, binascii.Error):
            return 2
        if not png.startswith(PNG_SIGNATURE):
            return 2
        suggestion = exchange({"op": "vision"})
        if set(suggestion) != {"action"} or type(suggestion["action"]) is not dict:
            return 2
        action = suggestion["action"]
        if type(action.get("type")) is not str:
            return 2
        request = {"op": action["type"], **{key: value for key, value in action.items()
                                            if key != "type"}}
        if exchange(request) != {"accepted": True}:
            return 2
        if request["op"] == "cancel":
            return 0
        time.sleep(0.55)
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("probe", "broker-probe", "act"), required=True)
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    if args.mode == "probe":
        if not args.file or args.port is None or not 1 <= args.port <= 65535:
            return 2
        return probe(args.file, args.port)
    if args.file or args.port is not None:
        return 2
    return broker_probe() if args.mode == "broker-probe" else act()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BrokenPipeError, json.JSONDecodeError, ValueError):
        raise SystemExit(2) from None
