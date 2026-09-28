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
import net.minecraft.class_3965;
import net.minecraft.class_4970;
import net.minecraft.class_634;
import net.minecraft.class_636;
import net.minecraft.class_746;
import net.minecraft.class_7923;
import net.minecraft.class_310;

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
        if (stack == null || stack.method_7960() || stack.method_7909() != expectedItem) {
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
