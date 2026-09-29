package xyz.langyo.minecraft.mcp.common;

import net.minecraft.class_1268;
import net.minecraft.class_1661;
import net.minecraft.class_2680;
import net.minecraft.class_1792;
import net.minecraft.class_1799;
import net.minecraft.class_1937;
import net.minecraft.class_2248;
import net.minecraft.class_2338;
import net.minecraft.class_239;
import net.minecraft.class_2868;
import net.minecraft.class_2960;
import net.minecraft.class_304;
import net.minecraft.class_3965;
import net.minecraft.class_4970;
import net.minecraft.class_634;
import net.minecraft.class_636;
import net.minecraft.class_746;
import net.minecraft.class_7923;
import net.minecraft.class_310;
import net.minecraft.class_3675;
import net.minecraft.class_1041;

/**
 * Narrow real-client actions for the Minecraft 1.21.1 intermediary runtime.
 *
 * The intermediary class/member names were checked against the pinned
 * mappings.tiny (official/intermediary/named) fixture. Calls must be made on
 * the Minecraft client thread. An INPUT_DISPATCHED result reports only that
 * the client input path was invoked; it is not evidence of a server-side world
 * transition. The scenario observer must verify any requested transition.
 */
public final class ScenarioActions {
    private static final int HOTBAR_SIZE = 9;
    private static final int MAX_DROP_COUNT = 64;
    private static final int MAX_REGISTRY_ID_LENGTH = 255;
    private static final long MAX_VISIBLE_ATTACK_HOLD_NANOS = 6_000_000_000L;
    private static volatile class_1041 labeledCaptureWindow;
    private static volatile long visibleAttackUntilNanos;
    private static volatile boolean visibleAttackRequested;
    private static class_304 visiblePulseBinding;
    private static long visiblePulseUntilNanos;

    private ScenarioActions() {
    }

    /**
     * Selects a hotbar slot only when its current stack matches the requested
     * canonical registry ID. The normal selected-slot packet is sent when the
     * local selection changes.
     */
    public static ActionAck selectHotbar(class_310 client, int slot, String verifiedItemId) {
        ActionAck unavailable = requireClient(client, "select_hotbar", true);
        if (unavailable != null) {
            return unavailable;
        }
        if (slot < 0 || slot >= HOTBAR_SIZE) {
            return rejected("select_hotbar", "slot must be in the hotbar range 0..8");
        }

        class_2960 itemId = parseRegistryId(verifiedItemId);
        if (itemId == null) {
            return rejected("select_hotbar", "item ID must be a canonical registry ID");
        }
        class_1792 expectedItem = class_7923.field_41178.method_17966(itemId).orElse(null);
        if (expectedItem == null) {
            return rejected("select_hotbar", "item ID is not registered in this client");
        }

        class_1661 inventory = client.field_1724.method_31548();
        class_1799 stack = inventory.field_7547.get(slot);
        boolean verifiedEmpty = "minecraft:air".equals(verifiedItemId) && stack != null && stack.method_7960();
        if (!verifiedEmpty && (stack == null || stack.method_7960() || stack.method_7909() != expectedItem)) {
            return rejected("select_hotbar", "requested item is not in the requested hotbar slot");
        }

        if (inventory.field_7545 == slot) {
            return alreadySatisfied("select_hotbar", "verified item is already selected");
        }

        inventory.field_7545 = slot;
        class_634 connection = client.field_1724.field_3944;
        connection.method_52787(new class_2868(slot));
        return dispatched("select_hotbar", 1,
                "local slot changed and the vanilla selected-slot packet was sent");
    }

    /**
     * Drops the requested number of individual items from the currently
     * selected stack through the local player's vanilla drop input path.
     */
    public static ActionAck dropSelected(class_310 client, int count) {
        ActionAck unavailable = requireClient(client, "drop_selected", true);
        if (unavailable != null) {
            return unavailable;
        }
        if (count < 1 || count > MAX_DROP_COUNT) {
            return rejected("drop_selected", "count must be in the range 1..64");
        }

        class_1799 selected = client.field_1724.method_31548().method_7391();
        if (selected == null || selected.method_7960()) {
            return rejected("drop_selected", "selected hotbar stack is empty");
        }
        if (selected.method_7947() < count) {
            return rejected("drop_selected", "selected stack has fewer items than requested");
        }

        class_746 player = client.field_1724;
        for (int i = 0; i < count; i++) {
            // false is the normal single-item drop path (Q), not drop-all.
            // Its boolean return reports whether the client stack remains
            // non-empty, so it is intentionally not treated as an ACK signal.
            player.method_7290(false);
        }
        return dispatched("drop_selected", count,
                "vanilla single-item drop input was invoked; observe the ground and inventory separately");
    }

    public static ActionAck useSelectedItem(class_310 client, String verifiedItemId) {
        ActionAck unavailable = requireClient(client, "use_selected_item", true);
        if (unavailable != null) return unavailable;
        class_2960 itemId = parseRegistryId(verifiedItemId);
        class_1799 held = client.field_1724.method_31548().method_7391();
        if (itemId == null || held == null || held.method_7960()
                || held.method_7909() != class_7923.field_41178.method_17966(itemId).orElse(null)) {
            return rejected("use_selected_item", "verified item is not held in the main hand");
        }
        client.field_1761.method_2919(client.field_1724, class_1268.field_5808);
        return dispatched("use_selected_item", 1,
                "vanilla main-hand item-use invoked; observe server consumption and effects after normal ticks");
    }

    public static ActionAck setCrouch(class_310 client, boolean pressed) {
        ActionAck unavailable = requireClient(client, "set_crouch", true);
        if (unavailable != null) return unavailable;
        client.field_1690.field_1832.method_23481(pressed);
        return dispatched("set_crouch", 1, "vanilla crouch key state changed; observe server state after normal ticks");
    }

    public static ActionAck setForward(class_310 client, boolean down) {
        ActionAck unavailable = requireClient(client, "set_forward", true);
        if (unavailable != null) return unavailable;
        client.field_1690.field_1894.method_23481(down);
        return dispatched("set_forward", 1,
                "vanilla forward key state changed; observe server state after normal ticks");
    }

    public static ActionAck visibleKey(class_310 client, String key, boolean pressed) {
        ActionAck unavailable = requireClient(client, "visible_key", true);
        if (unavailable != null) return unavailable;
        if (pressed && client.field_1755 != null)
            return rejected("visible_key", "world input requires no open screen");
        class_304 binding = switch (key) {
            case "forward" -> client.field_1690.field_1894;
            case "back" -> client.field_1690.field_1881;
            case "left" -> client.field_1690.field_1913;
            case "right" -> client.field_1690.field_1849;
            case "jump" -> client.field_1690.field_1903;
            case "sneak" -> client.field_1690.field_1832;
            case "attack" -> client.field_1690.field_1886;
            case "use" -> client.field_1690.field_1904;
            default -> null;
        };
        if (binding == null) return rejected("visible_key", "key is not in the ordinary-input set");
        if (pressed && "attack".equals(key) && binding.method_1415())
            return rejected("visible_key", "attack key is unbound");
        boolean attackEdge = false;
        if ("attack".equals(key)) {
            expireVisibleAttack(client);
            if (pressed) {
                if (visibleAttackRequested && visibleAttackUntilNanos == 0)
                    return rejected("visible_key", "attack hold expired; release before pressing again");
                attackEdge = !visibleAttackRequested;
                visibleAttackRequested = true;
            } else {
                visibleAttackRequested = false;
                visibleAttackUntilNanos = 0;
            }
        }
        binding.method_23481(pressed);
        if (attackEdge) {
            visibleAttackUntilNanos = System.nanoTime() + MAX_VISIBLE_ATTACK_HOLD_NANOS;
            class_304.method_1420(class_3675.method_15981(binding.method_1428()));
        }
        if (!pressed && "attack".equals(key))
            while (binding.method_1436()) { }
        return dispatched("visible_key", 1, "bounded vanilla key state dispatched");
    }

    public static ActionAck visiblePulse(class_310 client, String key, int milliseconds) {
        ActionAck unavailable = requireClient(client, "visible_pulse", true);
        if (unavailable != null) return unavailable;
        if (client.field_1755 != null) return rejected("visible_pulse", "movement requires no open screen");
        if (milliseconds < 50 || milliseconds > 500)
            return rejected("visible_pulse", "movement duration is outside 50..500 ms");
        if (key == null) return rejected("visible_pulse", "key is not a movement input");
        class_304 binding = switch (key) {
            case "forward" -> client.field_1690.field_1894;
            case "back" -> client.field_1690.field_1881;
            case "left" -> client.field_1690.field_1913;
            case "right" -> client.field_1690.field_1849;
            case "jump" -> client.field_1690.field_1903;
            case "sneak" -> client.field_1690.field_1832;
            default -> null;
        };
        if (binding == null) return rejected("visible_pulse", "key is not a movement input");
        expireVisiblePulse(client);
        if (visiblePulseBinding != null || binding.method_1434())
            return rejected("visible_pulse", "movement input is already held");
        visiblePulseBinding = binding;
        visiblePulseUntilNanos = System.nanoTime() + milliseconds * 1_000_000L;
        binding.method_23481(true);
        return dispatched("visible_pulse", 1, "client-tick bounded movement pulse dispatched");
    }

    public static ActionAck visibleLook(class_310 client, int yawDelta, int pitchDelta) {
        ActionAck unavailable = requireClient(client, "visible_look", true);
        if (unavailable != null) return unavailable;
        if (client.field_1755 != null) return rejected("visible_look", "look requires no open screen");
        if (yawDelta < -15 || yawDelta > 15 || pitchDelta < -15 || pitchDelta > 15
                || yawDelta == 0 && pitchDelta == 0)
            return rejected("visible_look", "look delta is outside the bounded range");
        class_746 player = client.field_1724;
        player.method_36456(player.method_36454() + yawDelta);
        player.method_36457(Math.max(-90.0f, Math.min(90.0f, player.method_36455() + pitchDelta)));
        return dispatched("visible_look", 1, "relative local look input dispatched");
    }

    public static ActionAck captureWindowLabel(class_310 client) {
        ActionAck unavailable = requireClient(client, "capture_window_label", false);
        if (unavailable != null) return unavailable;
        String title = "MC Mod Lab Minecraft PID " + ProcessHandle.current().pid();
        class_1041 window = client.method_22683();
        window.method_24286(title);
        labeledCaptureWindow = window;
        return dispatched("capture_window_label", 1, title);
    }

    public static String retainedCaptureWindowTitle(class_1041 window, String requested) {
        return window == labeledCaptureWindow
                ? "MC Mod Lab Minecraft PID " + ProcessHandle.current().pid() : requested;
    }

    public static boolean permitsHeldAttackWithoutGrab(class_310 client) {
        if (client != null && client.method_18854()) expireVisibleAttack(client);
        return client != null && client.method_18854() && ReflectionHelper.isMcpControlMode()
                && visibleAttackRequested && visibleAttackUntilNanos != 0
                && client.field_1724 != null && client.field_1687 != null
                && client.field_1761 != null && client.field_1755 == null
                && client.field_1690.field_1886.method_1434();
    }

    public static void expireVisibleAttack(class_310 client) {
        if (visibleAttackRequested && visibleAttackUntilNanos != 0
                && System.nanoTime() >= visibleAttackUntilNanos) {
            visibleAttackUntilNanos = 0;
            class_304 attack = client.field_1690.field_1886;
            attack.method_23481(false);
            while (attack.method_1436()) { }
        }
    }

    public static void expireVisiblePulse(class_310 client) {
        if (visiblePulseBinding != null && (System.nanoTime() >= visiblePulseUntilNanos
                || !ReflectionHelper.isMcpControlMode() || client.field_1755 != null)) {
            visiblePulseBinding.method_23481(false);
            visiblePulseBinding = null;
            visiblePulseUntilNanos = 0;
        }
    }

    public static void releaseHeldInputs() {
        Object instance = ReflectionHelper.getMinecraftInstance();
        if (!(instance instanceof class_310 client)) {
            throw new IllegalStateException("client unavailable for input release");
        }
        Runnable release = () -> {
            visibleAttackRequested = false;
            visibleAttackUntilNanos = 0;
            visiblePulseBinding = null;
            visiblePulseUntilNanos = 0;
            class_304[] bindings = {
                client.field_1690.field_1894, client.field_1690.field_1881,
                client.field_1690.field_1913, client.field_1690.field_1849,
                client.field_1690.field_1903, client.field_1690.field_1832,
                client.field_1690.field_1886, client.field_1690.field_1904
            };
            for (class_304 binding : bindings) binding.method_23481(false);
            while (client.field_1690.field_1886.method_1436()) { }
            for (class_304 binding : bindings) {
                if (binding.method_1434())
                    throw new IllegalStateException("held input release was not confirmed");
            }
        };
        if (client.method_18854()) {
            release.run();
            return;
        }
        java.util.concurrent.CompletableFuture<Void> completed = new java.util.concurrent.CompletableFuture<>();
        client.execute(() -> {
            try {
                release.run();
                completed.complete(null);
            } catch (RuntimeException failure) {
                completed.completeExceptionally(failure);
            }
        });
        try {
            completed.get(2, java.util.concurrent.TimeUnit.SECONDS);
        } catch (InterruptedException failure) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("input release interrupted", failure);
        } catch (java.util.concurrent.ExecutionException | java.util.concurrent.TimeoutException failure) {
            throw new IllegalStateException("input release was not confirmed", failure);
        }
    }

    /**
     * Uses the main-hand item only against the real current block crosshair
     * hit, after matching its position and registered block ID to the fixture
     * target supplied by the caller.
     */
    public static ActionAck useItemAtBlock(
            class_310 client, int x, int y, int z, String expectedBlockId) {
        ActionAck unavailable = requireClient(client, "use_item_at_block", true);
        if (unavailable != null) {
            return unavailable;
        }

        class_2338 target = new class_2338(x, y, z);
        String targetError = verifyBlockTarget(client, target, expectedBlockId);
        if (targetError != null) {
            return rejected("use_item_at_block", targetError);
        }

        class_239 crosshair = client.field_1765;
        if (!(crosshair instanceof class_3965)) {
            return rejected("use_item_at_block", "client is not currently targeting a block");
        }
        class_3965 blockHit = (class_3965) crosshair;
        if (!target.equals(blockHit.method_17777())) {
            return rejected("use_item_at_block", "current block hit does not match the fixture coordinate");
        }
        if (!client.field_1724.method_56093(target, 0.0)) {
            return rejected("use_item_at_block", "fixture block is outside normal interaction reach");
        }

        client.field_1761.method_2896(client.field_1724, class_1268.field_5808, blockHit);
        return dispatched("use_item_at_block", 1,
                "vanilla main-hand block-use input was invoked; observe the requested transition separately");
    }

    /**
     * Aims the local player at the center of a verified, in-reach fixture
     * block. The caller must resolve coordinates from a reviewed fixture
     * marker; this method does not accept expressions or world commands.
     */
    public static ActionAck aimAtBlock(
            class_310 client, int x, int y, int z, String expectedBlockId) {
        ActionAck unavailable = requireClient(client, "aim_at_block", true);
        if (unavailable != null) {
            return unavailable;
        }

        class_2338 target = new class_2338(x, y, z);
        String targetError = verifyBlockTarget(client, target, expectedBlockId);
        if (targetError != null) {
            return rejected("aim_at_block", targetError);
        }
        class_746 player = client.field_1724;
        if (!player.method_56093(target, 0.0)) {
            return rejected("aim_at_block", "fixture block is outside normal interaction reach");
        }

        double dx = x + 0.5 - player.method_23317();
        double dy = y + 0.5 - player.method_23320();
        double dz = z + 0.5 - player.method_23321();
        double horizontalDistance = Math.sqrt(dx * dx + dz * dz);
        if (horizontalDistance < 1.0e-6 && Math.abs(dy) < 1.0e-6) {
            return rejected("aim_at_block", "player eye position coincides with the fixture target");
        }

        float yaw = (float) (Math.toDegrees(Math.atan2(dz, dx)) - 90.0);
        if (yaw < -180.0f) {
            yaw += 360.0f;
        } else if (yaw > 180.0f) {
            yaw -= 360.0f;
        }
        float pitch = (float) -Math.toDegrees(Math.atan2(dy, horizontalDistance));
        player.method_36456(yaw);
        player.method_36457(pitch);
        return dispatched("aim_at_block", 1,
                "local player look was set toward the verified fixture block; observe the crosshair separately");
    }

    private static String verifyBlockTarget(class_310 client, class_2338 target, String expectedBlockId) {
        class_2960 blockId = parseRegistryId(expectedBlockId);
        if (blockId == null) {
            return "block ID must be a canonical registry ID";
        }
        class_2248 expectedBlock = class_7923.field_41175.method_17966(blockId).orElse(null);
        if (expectedBlock == null) {
            return "block ID is not registered in this client";
        }

        class_1937 world = client.field_1687;
        class_2680 state = world.method_8320(target);
        if (state.method_26215()) {
            return "fixture coordinate resolves to air, not a target block";
        }
        if (state.method_26204() != expectedBlock) {
            return "block at fixture coordinate does not match the expected registry ID";
        }
        return null;
    }

    private static class_2960 parseRegistryId(String value) {
        if (value == null || value.length() < 3 || value.length() > MAX_REGISTRY_ID_LENGTH) {
            return null;
        }
        int separator = value.indexOf(':');
        if (separator < 1 || separator == value.length() - 1
                || value.indexOf(':', separator + 1) >= 0) {
            return null;
        }
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == ':') {
                continue;
            }
            boolean valid = c >= 'a' && c <= 'z'
                    || c >= '0' && c <= '9'
                    || c == '_' || c == '-' || c == '.'
                    || i > separator && c == '/';
            if (!valid) {
                return null;
            }
        }
        class_2960 parsed = class_2960.method_12829(value);
        return parsed != null && value.equals(parsed.toString()) ? parsed : null;
    }

    private static ActionAck requireClient(class_310 client, String action, boolean needsGameMode) {
        if (client == null || !client.method_18854()) {
            return rejected(action, "action must run on the Minecraft client thread");
        }
        if (!ReflectionHelper.isMcpControlMode()) {
            return rejected(action, "MCP control mode is required");
        }
        if (client.field_1724 == null || client.field_1687 == null
                || needsGameMode && client.field_1761 == null) {
            return rejected(action, "a live client player and world are required");
        }
        if (client.field_1724.field_3944 == null) {
            return rejected(action, "client player connection is unavailable");
        }
        return null;
    }

    private static ActionAck dispatched(String action, int calls, String detail) {
        return new ActionAck(action, "input_dispatched", calls, detail);
    }

    private static ActionAck alreadySatisfied(String action, String detail) {
        return new ActionAck(action, "already_satisfied", 0, detail);
    }

    private static ActionAck rejected(String action, String detail) {
        return new ActionAck(action, "rejected", 0, detail);
    }

    /** Acknowledges input handling only; it never asserts a world transition. */
    public static final class ActionAck {
        public final String action;
        public final String status;
        public final int inputCalls;
        public final String detail;

        private ActionAck(String action, String status, int inputCalls, String detail) {
            this.action = action;
            this.status = status;
            this.inputCalls = inputCalls;
            this.detail = detail;
        }
    }
}
