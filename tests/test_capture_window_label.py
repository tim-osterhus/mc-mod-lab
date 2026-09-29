import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CaptureWindowLabelTests(unittest.TestCase):
    def test_explicit_opt_in_retains_only_selected_window_pid_title(self):
        source = (ROOT / "bridge-src/ScenarioActions.java").read_text(encoding="utf-8")
        action = source.split("public static ActionAck captureWindowLabel", 1)[1].split(
            "public static void releaseHeldInputs", 1)[0]
        self.assertIn('requireClient(client, "capture_window_label", false)', action)
        self.assertIn('"MC Mod Lab Minecraft PID " + ProcessHandle.current().pid()', action)
        self.assertLess(action.index("window.method_24286(title);"),
                        action.index("labeledCaptureWindow = window;"))
        self.assertIn("window == labeledCaptureWindow", action)
        self.assertIn(": requested;", action)
        self.assertNotIn("labeledCaptureWindow = null", source)

    def test_client_mixin_intercepts_window_title_and_is_packaged(self):
        config = json.loads((ROOT / "bridge-src/mc-mod-lab-hud.mixins.json").read_text(
            encoding="utf-8"))
        self.assertIn("CaptureWindowLabelMixin", config["client"])
        source = (ROOT / "bridge-src/xyz/langyo/minecraft/mcp/common/hudmixin/"
                  "CaptureWindowLabelMixin.java").read_text(encoding="utf-8")
        self.assertIn("@Mixin(value = class_1041.class, remap = false)", source)
        self.assertIn('@ModifyVariable(method = "method_24286", at = @At("HEAD"), '
                      'argsOnly = true, remap = false)', source)
        self.assertIn("ScenarioActions.retainedCaptureWindowTitle", source)
        builder = (ROOT / "scripts/build_packaged_bridge.py").read_text(encoding="utf-8")
        self.assertEqual(builder.count('"hudmixin/CaptureWindowLabelMixin"'), 1)
        self.assertEqual(builder.count('"hudmixin/CaptureWindowLabelMixin.java"'), 1)
        files = json.loads((ROOT / "package-files.json").read_text(encoding="utf-8"))
        self.assertIn("bridge-src/xyz/langyo/minecraft/mcp/common/hudmixin/"
                      "CaptureWindowLabelMixin.java", files)


if __name__ == "__main__":
    unittest.main()
