import json
import unittest
from pathlib import Path

from scripts import build_private_chunk_overlay as overlay


ROOT = Path(__file__).resolve().parents[1]


class PrivateChunkOverlayTests(unittest.TestCase):
    def test_only_one_existing_authenticated_route_is_patched(self):
        source = ("class Server {\n" + overlay.ANCHOR
                  + overlay.PATTERN_MATCH + "\n"
                  + "                    r = inputHandler.inspectMiningTarget();\n}\n")
        result = overlay.patched_http(source)
        self.assertIn(overlay.ROUTE_LINE + overlay.ANCHOR, result)
        self.assertIn(overlay.JAVA8_CHECK, result)
        self.assertIn(overlay.JAVA8_CAST, result)
        self.assertNotIn(overlay.PATTERN_MATCH, result)
        with self.assertRaises(ValueError):
            overlay.patched_http(source + overlay.ANCHOR)
        with self.assertRaises(ValueError):
            overlay.patched_http("class Server {}")
        with self.assertRaises(ValueError):
            overlay.patched_http(result)

    def test_handler_is_strict_read_only_and_private_package_excluded(self):
        handler = (ROOT / "private-qa/ChunkPresenceHandler.java").read_text(encoding="utf-8")
        self.assertIn("reader.setLenient(false)", handler)
        self.assertIn("!fields.add(field)", handler)
        self.assertIn("reader.peek() != JsonToken.NUMBER", handler)
        self.assertIn("server.execute(() ->", handler)
        self.assertIn("ReflectionHelper.isMcpControlMode()", handler)
        self.assertIn("level.method_22340(pos)", handler)
        self.assertIn("level.method_37118(pos)", handler)
        for forbidden in ("getChunk(", "getBlockState(", "getBlockEntity(",
                          "execute_command", "getOrCreate", "forceLoad"):
            self.assertNotIn(forbidden, handler)
        packaged = json.loads((ROOT / "package-files.json").read_text(encoding="utf-8"))
        self.assertFalse(any(name.startswith("private-qa/") or
                             name == "scripts/build_private_chunk_overlay.py" for name in packaged))


if __name__ == "__main__":
    unittest.main()
