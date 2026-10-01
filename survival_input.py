"""Pixel-only, bounded real-client input for an externally isolated actor."""

import base64
import binascii
from io import BytesIO
import http.client
import json
import os
import time

from PIL import Image

import lab
import scenario_v2


MAX_WALL_SECONDS = 600
MAX_TRIAL_WALL_SECONDS = 1800
MAX_INPUTS = 1200
MAX_FRAMES = 600
MAX_PNG_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
PULSE_KEYS = frozenset({"forward", "back", "left", "right", "jump", "sneak", "attack", "use"})
PRESS_KEYS = frozenset({"E", "Escape", "Q", *(str(index) for index in range(1, 10))})


class PolicyError(Exception):
    """An actor-safe refusal with no bridge or fixture detail."""


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _request_png(identity):
    lab.listening_socket(identity["pid"], identity["port"])
    token = os.environ.get("MC_MOD_LAB_TOKEN", "")
    if len(token) < 32 or "\n" in token or "\r" in token:
        raise lab.LabError("frame token unavailable")
    connection = http.client.HTTPConnection("127.0.0.1", identity["port"], timeout=8)
    try:
        connection.request("GET", "/api/screenshot", headers={"Authorization": "Bearer " + token})
        response = connection.getresponse()
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if response.status != 200 or len(raw) > MAX_RESPONSE_BYTES:
            raise lab.LabError("bounded framebuffer unavailable")
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("original"), str):
            raise lab.LabError("framebuffer response unavailable")
        prefix = "data:image/png;base64,"
        if not data["original"].startswith(prefix):
            raise lab.LabError("framebuffer PNG unavailable")
        png = base64.b64decode(data["original"][len(prefix):], validate=True)
        return png, data.get("width"), data.get("height")
    except (OSError, http.client.HTTPException, UnicodeError, ValueError, binascii.Error) as exc:
        raise lab.LabError("bounded framebuffer unavailable") from exc
    finally:
        connection.close()


def _pixels(png, declared_width, declared_height):
    if not isinstance(png, bytes) or not 24 <= len(png) <= MAX_PNG_BYTES:
        raise PolicyError("frame unavailable")
    try:
        with Image.open(BytesIO(png)) as image:
            if image.format != "PNG" or not (640 <= image.width <= 1920 and 360 <= image.height <= 1080):
                raise PolicyError("frame unavailable")
            image.load()
            size = image.size
    except (OSError, ValueError):
        raise PolicyError("frame unavailable") from None
    if (declared_width is not None and (type(declared_width) is not int or declared_width != size[0])
            or declared_height is not None and (type(declared_height) is not int or declared_height != size[1])):
        raise PolicyError("frame unavailable")
    return size


def _validate_input(request, frame_size):
    if not isinstance(request, dict) or not isinstance(request.get("type"), str):
        raise PolicyError("input unavailable")
    kind = request["type"]
    if kind == "look" and set(request) == {"type", "yaw_delta", "pitch_delta"}:
        yaw, pitch = request["yaw_delta"], request["pitch_delta"]
        if _integer(yaw, -15, 15) and _integer(pitch, -15, 15) and (yaw or pitch):
            return kind
    elif kind == "pulse" and set(request) == {"type", "key", "milliseconds"}:
        if (type(request["key"]) is str and request["key"] in PULSE_KEYS
                and _integer(request["milliseconds"], 50, 5000 if request["key"] == "attack" else 500)):
            return kind
    elif kind == "press" and set(request) == {"type", "key"}:
        if type(request["key"]) is str and request["key"] in PRESS_KEYS:
            return kind
    elif kind == "click" and set(request) == {"type", "x", "y"} and frame_size is not None:
        if _integer(request["x"], 0, frame_size[0] - 1) and _integer(request["y"], 0, frame_size[1] - 1):
            return kind
    raise PolicyError("input unavailable")


class PolicySession:
    """Trusted broker half; never pass this object or its identity to the actor."""

    def __init__(self, identity, expected_frame, *, wall_seconds=MAX_WALL_SECONDS):
        if not _integer(wall_seconds, 1, MAX_TRIAL_WALL_SECONDS):
            raise PolicyError("reviewed session duration is required")
        if (not isinstance(expected_frame, tuple) or len(expected_frame) != 2
                or not _integer(expected_frame[0], 640, 1920)
                or not _integer(expected_frame[1], 360, 1080)):
            raise PolicyError("reviewed frame size is required")
        self._identity = identity
        self._expected_frame = expected_frame
        self._wall_seconds = wall_seconds
        self._lease = None
        self._deadline = None
        self._closed = False
        self._inputs = 0
        self._frames = 0
        self._last_input = float("-inf")
        self._last_frame = float("-inf")
        self._frame_size = None
        self.cleanup_status = "not_run"

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, _type, _value, _traceback):
        if not self.close():
            raise PolicyError("neutral input release failed; client must close")

    def start(self):
        if self._closed or self._lease is not None or self._identity.get("expected_gamemode") != "survival":
            raise PolicyError("Survival session unavailable")
        try:
            lab.status_check(self._identity)
            lab.world_check(self._identity)
            lab.player_check(self._identity)
            self._lease = scenario_v2.ControlLease(self._identity)
            self._lease.enter()
        except Exception:
            if not self.close():
                raise PolicyError("Survival session unavailable; client must close") from None
            raise PolicyError("Survival session unavailable") from None
        self._deadline = time.monotonic() + self._wall_seconds

    def _ready(self):
        if self._closed or self._lease is None or self._deadline is None:
            raise PolicyError("session is closed")
        if time.monotonic() >= self._deadline:
            if not self.close():
                raise PolicyError("neutral input release failed; client must close")
            raise PolicyError("session deadline reached")

    def frame(self):
        self._ready()
        now = time.monotonic()
        if self._frames >= MAX_FRAMES:
            if not self.close():
                raise PolicyError("neutral input release failed; client must close")
            raise PolicyError("frame budget exhausted")
        if now - self._last_frame < 0.5:
            raise PolicyError("frame budget unavailable")
        try:
            png, width, height = _request_png(self._identity)
            self._frame_size = _pixels(png, width, height)
            if self._frame_size != self._expected_frame:
                raise PolicyError("frame unavailable")
        except Exception:
            if not self.close():
                raise PolicyError("neutral input release failed; client must close") from None
            raise PolicyError("frame unavailable") from None
        self._last_frame = now
        self._frames += 1
        return png

    def input(self, request):
        self._ready()
        now = time.monotonic()
        if self._inputs >= MAX_INPUTS:
            if not self.close():
                raise PolicyError("neutral input release failed; client must close")
            raise PolicyError("input budget exhausted")
        if now - self._last_input < 0.1:
            raise PolicyError("input budget unavailable")
        self._inputs += 1
        self._last_input = now
        kind = _validate_input(request, self._frame_size)
        if kind == "click" and now - self._last_frame > 2.0:
            raise PolicyError("frame is stale")
        if kind == "pulse" and now + request["milliseconds"] / 1000 >= self._deadline:
            if not self.close():
                raise PolicyError("neutral input release failed; client must close")
            raise PolicyError("session deadline reached")
        try:
            if kind == "look":
                self._action("visible_look", {"yaw_delta": request["yaw_delta"],
                                              "pitch_delta": request["pitch_delta"]})
            elif kind == "pulse":
                if request["key"] in {"forward", "back", "left", "right", "jump", "sneak"}:
                    self._action("visible_pulse", {"key": request["key"],
                                                   "milliseconds": request["milliseconds"]})
                else:
                    self._action("visible_key", {"key": request["key"], "pressed": True})
                    try:
                        time.sleep(request["milliseconds"] / 1000)
                    finally:
                        self._action("visible_key", {"key": request["key"], "pressed": False})
            elif kind == "press":
                result = lab.command(self._identity, "press_key", {"key": request["key"]})
                if result is None:
                    raise lab.LabError("key acknowledgement absent", "fail")
            else:
                lab.command(self._identity, "click", {"x": request["x"], "y": request["y"]})
        except Exception:
            self.close()
            raise PolicyError("input unavailable; client must close") from None
        return {"accepted": True}

    def _action(self, name, params):
        scenario_v2.scenario_request(self._identity, "action", name, params)

    def close(self):
        if self._closed:
            return self.cleanup_status == "pass"
        self._closed = True
        if self._lease is None:
            self.cleanup_status = "pass"
        else:
            try:
                self.cleanup_status = self._lease.release()["status"]
            except Exception:
                self.cleanup_status = "fail"
        return self.cleanup_status == "pass"

    def cancel(self):
        if not self.close():
            raise PolicyError("neutral input release failed; client must close")
        return {"input_released": True}
