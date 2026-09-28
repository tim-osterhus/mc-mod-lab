package xyz.langyo.minecraft.mcp.common;

import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import net.minecraft.class_1263;
import net.minecraft.class_1703;
import net.minecraft.class_1735;
import net.minecraft.class_1799;
import net.minecraft.class_2338;
import net.minecraft.class_2586;
import net.minecraft.class_310;
import net.minecraft.class_3222;
import net.minecraft.class_3218;
import net.minecraft.class_465;
import net.minecraft.class_7923;

/** Fixed developer-only inspection; neither result is a player-perception API. */
public final class DeveloperInspectors {
    private static final int MAX_SCREEN_SLOTS = 128;
    private static final int MAX_BLOCK_SLOTS = 64;
    private static final Field GUI_LEFT = screenField("field_2792");
    private static final Field GUI_TOP = screenField("field_2779");
    private static final Field HOVERED = screenField("field_2787");

    private DeveloperInspectors() { }

    private static Field screenField(String name) {
        try {
            Field field = class_465.class.getDeclaredField(name);
            field.setAccessible(true);
            return field;
        } catch (ReflectiveOperationException error) {
            throw new IllegalStateException("pinned screen field unavailable", error);
        }
    }

    public static ScreenSlots screenSlots(class_310 client) {
        if (client == null || !client.method_18854() || !(client.field_1755 instanceof class_465<?> screen))
            return null;
        try {
            class_1703 menu = screen.method_17577();
            if (menu == null || menu.field_7761.size() > MAX_SCREEN_SLOTS) return null;
            int left = GUI_LEFT.getInt(screen), top = GUI_TOP.getInt(screen);
            class_1735 hovered = (class_1735) HOVERED.get(screen);
            List<ScreenSlot> slots = new ArrayList<>(menu.field_7761.size());
            Integer hoverIndex = null;
            for (int index = 0; index < menu.field_7761.size(); index++) {
                class_1735 slot = menu.field_7761.get(index);
                if (slot == null) return null;
                int x = left + slot.field_7873, y = top + slot.field_7872;
                if (x < -256 || y < -256 || x > screen.field_22789 + 256
                        || y > screen.field_22790 + 256) return null;
                if (slot == hovered) hoverIndex = index;
                slots.add(new ScreenSlot(index, x, y, inspectItem(slot.method_7677(), "menu", index)));
            }
            if (hovered != null && hoverIndex == null) return null;
            return new ScreenSlots(screen.getClass().getName(), menu.field_7761.size(), hoverIndex, slots);
        } catch (ReflectiveOperationException | ClassCastException error) {
            return null;
        }
    }

    public static BlockEntityInventory blockEntityInventory(net.minecraft.class_1132 server,
            class_3218 level, UUID playerId, int x, int y, int z) {
        if (server == null || level == null || playerId == null || !server.method_18854()) return null;
        class_3222 player = server.method_3760().method_14602(playerId);
        if (player == null || player.method_51469() != level) return null;
        double dx = player.method_23317() - x - 0.5;
        double dy = player.method_23318() - y - 0.5;
        double dz = player.method_23321() - z - 0.5;
        if (dx * dx + dy * dy + dz * dz > 16 * 16) return null;
        class_2338 pos = new class_2338(x, y, z);
        if (!level.method_22340(pos)) return null;
        class_2586 entity = level.method_8321(pos);
        if (entity == null) return null;
        String blockId = String.valueOf(class_7923.field_41175.method_10221(
                level.method_8320(pos).method_26204()));
        String entityId = String.valueOf(class_7923.field_41181.method_10221(entity.method_11017()));
        if (blockId.length() > 128 || entityId.length() > 128) return null;
        if (!(entity instanceof class_1263 inventory))
            return new BlockEntityInventory(server.method_3780(),
                    level.method_27983().method_29177().toString(), x, y, z,
                    blockId, entityId, false, 0, List.of());
        int size = inventory.method_5439();
        if (size < 0 || size > MAX_BLOCK_SLOTS) return null;
        List<BlockSlot> slots = new ArrayList<>();
        for (int index = 0; index < size; index++) {
            InspectItem item = inspectItem(inventory.method_5438(index), "block_entity", index);
            if (item != null) slots.add(new BlockSlot(index, item));
        }
        return new BlockEntityInventory(server.method_3780(),
                level.method_27983().method_29177().toString(), x, y, z,
                blockId, entityId, true, size, slots);
    }

    private static InspectItem inspectItem(class_1799 stack, String section, int index) {
        if (stack == null || stack.method_7960()) return null;
        int count = stack.method_7947();
        if (count < 1 || count > 4096) throw new IllegalStateException("invalid inspected stack count");
        ScenarioObservers.ItemSnapshot item = ScenarioObservers.snapshotItem(stack, section, index, count);
        boolean complete = !item.itemIdTruncated && !item.componentsTruncated
                && item.componentDigestStatus == ScenarioObservers.ComponentDigestStatus.COMPLETE
                && item.componentSetSha256 != null;
        return new InspectItem(item.itemId, count, complete, complete ? item.componentSetSha256 : null);
    }

    public record InspectItem(String itemId, int count, boolean componentDigestComplete,
            String componentSha256) { }
    public record ScreenSlot(int index, int x, int y, InspectItem item) { }
    public record ScreenSlots(String screenClass, String stateSource, boolean serverAuthoritative,
            int slotCount, Integer hoveredIndex, List<ScreenSlot> slots) {
        ScreenSlots(String screenClass, int slotCount, Integer hoveredIndex, List<ScreenSlot> slots) {
            this(screenClass, "client_menu_cache", false, slotCount, hoveredIndex, List.copyOf(slots));
        }
    }
    public record BlockSlot(int index, InspectItem item) { }
    public record BlockEntityInventory(long serverTick, String stateSource, boolean serverAuthoritative,
            String dimension, int x, int y, int z, String blockId, String blockEntityId,
            boolean hasInventory, int slotCount, List<BlockSlot> slots) {
        BlockEntityInventory(long serverTick, String dimension, int x, int y, int z,
                String blockId, String blockEntityId, boolean hasInventory, int slotCount, List<BlockSlot> slots) {
            this(serverTick, "integrated_server_block_entity_inventory", true, dimension,
                    x, y, z, blockId, blockEntityId, hasInventory, slotCount, List.copyOf(slots));
        }
    }
}
