import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VisibleHeldAttackTests(unittest.TestCase):
    def test_attack_grant_is_one_shot_per_press_edge(self):
        source = (ROOT / "bridge-src/ScenarioActions.java").read_text(encoding="utf-8")
        visible = source.split("public static ActionAck visibleKey", 1)[1].split(
            "public static ActionAck visibleLook", 1)[0]
        self.assertIn('attackEdge = !visibleAttackRequested;', visible)
        self.assertIn('visibleAttackRequested = true;', visible)
        self.assertIn('visibleAttackRequested = false;', visible)
        self.assertIn('if (visibleAttackRequested && visibleAttackUntilNanos == 0)', visible)
        self.assertIn('binding.method_23481(pressed);\n        if (attackEdge) {\n'
                      '            visibleAttackUntilNanos = System.nanoTime() '
                      '+ MAX_VISIBLE_ATTACK_HOLD_NANOS;', visible)
        self.assertEqual(visible.count('visibleAttackUntilNanos = System.nanoTime()'), 1)
        self.assertIn('if (attackEdge) {\n            visibleAttackUntilNanos', visible)
        self.assertIn('class_304.method_1420(class_3675.method_15981(binding.method_1428()));', visible)

    def test_redirect_preserves_vanilla_unless_bounded_visible_hold_is_active(self):
        source = (ROOT / "bridge-src/ScenarioActions.java").read_text(encoding="utf-8")
        mixin = (ROOT / "bridge-src/xyz/langyo/minecraft/mcp/common/hudmixin/"
                 "VisibleHeldAttackMixin.java").read_text(encoding="utf-8")
        method = source.split("public static boolean permitsHeldAttackWithoutGrab", 1)[1].split(
            "public static void releaseHeldInputs", 1)[0]
        self.assertIn("MAX_VISIBLE_ATTACK_HOLD_NANOS = 6_000_000_000L", source)
        self.assertIn("visibleAttackRequested && visibleAttackUntilNanos != 0", method)
        for check in ("ReflectionHelper.isMcpControlMode()", "client.field_1724 != null",
                      "client.field_1687 != null", "client.field_1761 != null",
                      "client.field_1755 == null", "client.field_1690.field_1886.method_1434()"):
            self.assertIn(check, method)
        self.assertIn("visibleAttackRequested = false;\n            visibleAttackUntilNanos = 0;", source)
        expiry = source.split("public static void expireVisibleAttack", 1)[1].split(
            "public static void releaseHeldInputs", 1)[0]
        self.assertIn("System.nanoTime() >= visibleAttackUntilNanos", expiry)
        self.assertIn("attack.method_23481(false);", expiry)
        self.assertIn("while (attack.method_1436()) { }", expiry)
        self.assertIn('method = "method_1574", at = @At("HEAD")', mixin)
        self.assertIn("ScenarioActions.expireVisibleAttack", mixin)
        self.assertIn('target = "Lnet/minecraft/class_312;method_1613()Z"', mixin)
        self.assertIn("ScenarioActions.permitsHeldAttackWithoutGrab", mixin)
        self.assertIn("|| mouse.method_1613()", mixin)
        config = json.loads((ROOT / "bridge-src/mc-mod-lab-hud.mixins.json").read_text(
            encoding="utf-8"))
        self.assertIn("VisibleHeldAttackMixin", config["client"])


if __name__ == "__main__":
    unittest.main()
