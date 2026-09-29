"""Trusted broker for a sandboxed pixel/action transport child."""

import base64
import hashlib
import http.client
import json
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time

import survival_input


MAX_LINE = 12 * 1024 * 1024
ACTOR_PATH = Path(__file__).parent / "scripts" / "isolated_survival_actor.py"
PROMPT = ("Play this Minecraft Survival world using only the screenshot. Start with ordinary "
          "resources; if you naturally obtain the in-game guide, open and read it while working "
          "toward a first Aura circuit. "
          "Return one JSON object with an action: {\"type\":\"look\",\"yaw_delta\":integer,"
          "\"pitch_delta\":integer}, {\"type\":\"pulse\",\"key\":key,\"milliseconds\":integer}, "
          "{\"type\":\"press\",\"key\":key}, {\"type\":\"click\",\"x\":integer,\"y\":integer}, "
          "or {\"type\":\"cancel\"}. Use cancel when finished or unable to progress. "
          "Do not request commands, world data, coordinates, files, or tools. "
          "Movement pulses are 50-500 ms, attack 50-5000 ms, use 50-500 ms; "
          "look deltas are -15..15; press keys are E, Escape, Q, or 1..9.")


class ActorError(Exception):
    pass


def actor_source_hash():
    return hashlib.sha256(ACTOR_PATH.read_bytes()).hexdigest()


def _http_json(method, path, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=30)
    try:
        connection.request(method, path, body=data,
                           headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(256 * 1024 + 1)
        status = response.status
    finally:
        connection.close()
    if status != 200 or len(raw) > 256 * 1024:
        raise ActorError("local model response unavailable")
    return json.loads(raw)


class OllamaVisionModel:
    """Explicitly selected, already-installed local model; never starts or pulls one."""

    def __init__(self, name):
        if not isinstance(name, str) or not name or any(c in name for c in "\r\n\x00"):
            raise ActorError("model name unavailable")
        self.name = name
        self.first_png = None
        try:
            tags = _http_json("GET", "/api/tags")
            names = {entry.get("name") for entry in tags["models"] if isinstance(entry, dict)}
            if name not in names:
                raise ActorError("selected local model is not installed")
            details = _http_json("POST", "/api/show", {"model": name})
            if "vision" not in details.get("capabilities", []):
                raise ActorError("selected local model has no vision capability")
        except (OSError, http.client.HTTPException, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ActorError("local vision model preflight unavailable") from exc

    def choose(self, png, history, frame_size):
        if self.first_png is None:
            self.first_png = png
        images = [base64.b64encode(self.first_png).decode("ascii")]
        if png != self.first_png:
            images.append(base64.b64encode(png).decode("ascii"))
        message = {"role": "user", "content": PROMPT + "\nRecent actions: " +
                   json.dumps(history[-12:], separators=(",", ":")),
                   "images": images}
        try:
            response = _http_json("POST", "/api/chat", {
                "model": self.name, "messages": [message], "format": "json", "stream": False,
                "options": {"temperature": 0}})
            if response["message"].get("tool_calls"):
                raise ValueError("model tools unavailable")
            action = json.loads(response["message"]["content"])
            if type(action) is not dict:
                raise ValueError("invalid action")
            if action.get("type") != "cancel":
                survival_input._validate_input(action, frame_size)
            elif set(action) != {"type"}:
                raise ValueError("invalid cancel")
            return action
        except (OSError, http.client.HTTPException, AttributeError, KeyError, TypeError, ValueError,
                survival_input.PolicyError) as exc:
            raise ActorError("local vision action unavailable") from exc


class ActorBroker:
    """The only holder of the selected identity, token, model and input lease."""

    def __init__(self, session, model, first_frame=None, stopped=None, trace_out=None,
                 guide_capture=None):
        self.session = session
        self.model = model
        self.png = None
        self.pending = None
        self.history = []
        self.trace = trace_out if trace_out is not None else []
        self.terminal = False
        self.actions = 0
        self.first_frame = first_frame
        self.guide_capture = guide_capture
        self.guide_probe_pending = False
        self.stopped = stopped or (lambda: False)

    def handle(self, request):
        if self.stopped():
            raise ActorError("actor deadline or client guard reached")
        if type(request) is not dict or self.terminal:
            return {"accepted": False}
        if request == {"op": "frame"} and self.pending is None:
            if self.guide_probe_pending and self.guide_capture is not None:
                self.png = self.guide_capture(self.session.frame)
            else:
                self.png = self.session.frame()
            self.guide_probe_pending = False
            if self.first_frame is not None:
                self.first_frame(self.png)
                self.first_frame = None
            return {"png": base64.b64encode(self.png).decode("ascii")}
        if request == {"op": "vision"} and self.png is not None and self.pending is None:
            self.pending = self.model.choose(self.png, self.history, self.session._expected_frame)
            try:
                if self.pending.get("type") == "cancel":
                    if self.pending != {"type": "cancel"}:
                        raise survival_input.PolicyError("invalid cancel")
                else:
                    survival_input._validate_input(self.pending, self.session._expected_frame)
            except (AttributeError, survival_input.PolicyError) as exc:
                self.pending = None
                raise ActorError("model action unavailable") from exc
            return {"action": self.pending}
        if self.pending is None or "type" in request:
            return {"accepted": False}
        action = {"type": request.get("op"), **{key: value for key, value in request.items()
                                                  if key != "op"}}
        if (action != self.pending
                or set(request) != (set(self.pending) - {"type"}) | {"op"}):
            return {"accepted": False}
        if self.stopped():
            raise ActorError("actor deadline or client guard reached")
        if action["type"] == "cancel":
            self.session.cancel()
            self.terminal = True
        else:
            self.session.input(action)
        self.actions += 1
        self.history.append(action)
        self.trace.append({"at_utc": time.time(), "action": action})
        if (action["type"] == "click" or action["type"] == "press"
                or (action["type"] == "pulse" and action["key"] == "use")):
            self.guide_probe_pending = True
        self.png = None
        self.pending = None
        return {"accepted": True}


def sandbox_command(mode, files=(), port=None):
    if mode not in {"probe", "broker-probe", "act"}:
        raise ActorError("actor mode unavailable")
    source = ACTOR_PATH.resolve()
    if not source.is_file():
        raise ActorError("isolated actor source unavailable")
    translated = _wslpath(source)
    if not translated.startswith("/mnt/") or "\n" in translated:
        raise ActorError("isolated actor path unavailable")
    command = ["wsl", "-d", "Ubuntu", "-u", "root", "--", "bwrap", "--unshare-all",
               "--die-with-parent", "--new-session", "--cap-drop", "ALL", "--clearenv",
               "--ro-bind", "/usr", "/usr",
               "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
               "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
               "--ro-bind", translated, "/actor.py", "--chdir", "/tmp",
               "/usr/bin/python3", "-I", "-S", "/actor.py", "--mode", mode]
    if mode == "probe":
        if not files or type(port) is not int or not 1 <= port <= 65535:
            raise ActorError("isolation probe arguments unavailable")
        for path in files:
            command.extend(["--file", _wslpath(path)])
        command.extend(["--port", str(port)])
    elif files or port is not None:
        raise ActorError("actor cannot receive probe arguments")
    return command


def _wslpath(path):
    translated = subprocess.run(["wsl", "-d", "Ubuntu", "--", "wslpath", "-a",
                                 Path(path).resolve().as_posix()],
                                capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    if not translated.startswith("/mnt/") or "\n" in translated:
        raise ActorError("isolated actor path unavailable")
    return translated


def isolation_probe(files, port):
    try:
        for path in files:
            with Path(path).open("rb") as source:
                source.read(1)
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
        source_hash = actor_source_hash()
        version = subprocess.run(["wsl", "-d", "Ubuntu", "-u", "root", "--", "bwrap", "--version"],
                                 capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        if not version.startswith("bubblewrap ") or len(version) > 80:
            raise ActorError("sandbox version unavailable")
        completed = subprocess.run(sandbox_command("probe", files, port), capture_output=True,
                                   text=True, timeout=20, check=False)
        result = json.loads(completed.stdout)
        if (completed.returncode != 0 or result.get("files_readable") != [False] * len(files)
                or result.get("token_present") is not False
                or result.get("bridge_reachable") is not False):
            raise ActorError("actor isolation negative probe failed")
        if actor_source_hash() != source_hash:
            raise ActorError("actor source changed during isolation probe")
        return {"status": "pass", "actor_source_sha256": source_hash,
                "sandbox_version": version,
                "checks": ["source_save_denied", "token_absent", "bridge_denied"]}
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ActorError("actor isolation negative probe unavailable") from exc


def _lines(stream, inbox):
    while True:
        line = stream.readline(MAX_LINE + 1)
        inbox.put(line)
        if not line or len(line) > MAX_LINE:
            return


def broker_probe(session, model, expected_source_hash=None):
    broker = ActorBroker(session, model)
    process = None
    inbox = queue.Queue(maxsize=4)
    try:
        if expected_source_hash is not None and actor_source_hash() != expected_source_hash:
            raise ActorError("actor source changed before broker probe")
        process = subprocess.Popen(sandbox_command("broker-probe"), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=_lines, args=(process.stdout, inbox), daemon=True).start()
        for _ in range(3):
            try:
                line = inbox.get(timeout=5)
            except queue.Empty as exc:
                raise ActorError("actor broker negative probe timed out") from exc
            if not line or len(line) > 4096:
                raise ActorError("actor broker negative probe failed")
            request = json.loads(line)
            reply = broker.handle(request)
            if reply != {"accepted": False}:
                raise ActorError("actor broker exposed a forbidden capability")
            process.stdin.write(b'{"accepted":false}\n')
            process.stdin.flush()
        if process.wait(timeout=5) != 0:
            raise ActorError("actor broker negative probe failed")
        if expected_source_hash is not None and actor_source_hash() != expected_source_hash:
            raise ActorError("actor source changed during broker probe")
        return {"status": "pass", "checks": ["typed_observer_denied", "command_denied",
                                              "malformed_input_denied"]}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise ActorError("actor broker negative probe unavailable") from exc
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdin.close()
            process.stdout.close()


def run_actor(session, model, cancel, wall_seconds=600, first_frame=None,
              expected_source_hash=None, trace_out=None, guide_capture=None):
    deadline = time.monotonic() + wall_seconds
    broker = ActorBroker(session, model, first_frame,
                         stopped=lambda: cancel.is_set() or time.monotonic() >= deadline,
                         trace_out=trace_out, guide_capture=guide_capture)
    inbox = queue.Queue(maxsize=2)
    timer = threading.Timer(wall_seconds, cancel.set)
    process = None
    try:
        if expected_source_hash is not None and actor_source_hash() != expected_source_hash:
            raise ActorError("actor source changed before trial")
        timer.start()
        process = subprocess.Popen(sandbox_command("act"), stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=_lines, args=(process.stdout, inbox), daemon=True).start()
        while not broker.terminal:
            if cancel.is_set() or time.monotonic() >= deadline:
                raise ActorError("actor wall deadline or client guard reached")
            try:
                line = inbox.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                if process.poll() is not None:
                    raise ActorError("actor exited before cancellation")
                continue
            if not line or len(line) > MAX_LINE:
                raise ActorError("actor protocol ended")
            try:
                request = json.loads(line)
                reply = broker.handle(request)
            except (ValueError, KeyError, TypeError):
                reply = {"accepted": False}
            process.stdin.write((json.dumps(reply, separators=(",", ":")) + "\n").encode("ascii"))
            process.stdin.flush()
        if process.wait(timeout=5) != 0:
            raise ActorError("actor did not exit cleanly")
        if expected_source_hash is not None and actor_source_hash() != expected_source_hash:
            raise ActorError("actor source changed during trial")
        return {"status": "inconclusive", "actor_actions": broker.actions,
                "actions": broker.history, "action_trace": broker.trace,
                "reason": "pixel-only actor stopped; evaluator and independent review required"}
    finally:
        timer.cancel()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process is not None:
            process.stdin.close()
            process.stdout.close()
        if not session.close():
            raise ActorError("neutral input release failed")
