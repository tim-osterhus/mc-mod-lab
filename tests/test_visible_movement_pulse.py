import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VisibleMovementPulseTests(unittest.TestCase):
    def test_typed_endpoint_limits_duration_and_movement_keys(self):
        source = (ROOT / "bridge-src/xyz/langyo/minecraft/mcp/common/ScenarioEndpoint.java").read_text(
            encoding="utf-8")
        parser = source.split('} else if ("visible_pulse".equals(name)) {', 1)[1].split(
            '} else if ("visible_look".equals(name)) {', 1)[0]
        self.assertIn('fields(params, "key", "milliseconds");', parser)
        self.assertIn('Set.of("forward", "back", "left", "right", "jump", "sneak")', parser)
        self.assertIn('integer(params, "milliseconds", 50, 500)', parser)
        self.assertNotIn('"attack"', parser)
        self.assertNotIn('"use"', parser)

    def test_pulse_has_one_deadline_and_tick_release(self):
        source = (ROOT / "bridge-src/ScenarioActions.java").read_text(encoding="utf-8")
        pulse = source.split("public static ActionAck visiblePulse", 1)[1].split(
            "public static ActionAck visibleLook", 1)[0]
        expiry = source.split("public static void expireVisiblePulse", 1)[1].split(
            "public static void releaseHeldInputs", 1)[0]
        self.assertIn("if (key == null)", pulse)
        self.assertIn("if (visiblePulseBinding != null || binding.method_1434())", pulse)
        self.assertEqual(pulse.count("visiblePulseUntilNanos = System.nanoTime()"), 1)
        self.assertIn("System.nanoTime() >= visiblePulseUntilNanos", expiry)
        self.assertIn("!ReflectionHelper.isMcpControlMode()", expiry)
        self.assertIn("client.field_1755 != null", expiry)
        self.assertIn("visiblePulseBinding.method_23481(false);", expiry)
        self.assertIn("visiblePulseBinding = null;", expiry)
        self.assertIn("visiblePulseUntilNanos = 0;", expiry)
        release = source.split("public static void releaseHeldInputs", 1)[1]
        self.assertIn("visiblePulseBinding = null;", release)
        self.assertIn("visiblePulseUntilNanos = 0;", release)
        mixin = (ROOT / "bridge-src/xyz/langyo/minecraft/mcp/common/hudmixin/"
                 "VisibleHeldAttackMixin.java").read_text(encoding="utf-8")
        self.assertIn('method = "method_1574", at = @At("HEAD")', mixin)
        self.assertIn("ScenarioActions.expireVisiblePulse", mixin)


if __name__ == "__main__":
    unittest.main()
