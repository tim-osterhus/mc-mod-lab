package xyz.langyo.minecraft.mcp.common;

import java.util.Optional;
import java.util.UUID;
import net.minecraft.class_1132;
import net.minecraft.class_1703;
import net.minecraft.class_1799;
import net.minecraft.class_3222;
import pixlepix.auracascade.compat.AuraAccessoryInventory;

/** Reads only the four Aura attachment slots and current menu cursor on the integrated server thread. */
public final class AuraAccessoryObservers {
    private AuraAccessoryObservers() {
    }

    /** Returns empty off-thread or when the requested server player is unavailable. */
    public static Optional<Snapshot> observe(class_1132 server, UUID playerId) {
        if (server == null || playerId == null || !server.method_18854()) {
            return Optional.empty();
        }

        net.minecraft.class_3324 players = server.method_3760();
        if (players == null) {
            return Optional.empty();
        }
        class_3222 player = players.method_14602(playerId);
        if (player == null) {
            return Optional.empty();
        }
        class_1703 menu = player.field_7512;
        if (menu == null) {
            return Optional.empty();
        }

        ItemSlotSnapshot amulet = accessorySlot("amulet", AuraAccessoryInventory.AMULET,
                AuraAccessoryInventory.get(player, AuraAccessoryInventory.AMULET));
        ItemSlotSnapshot ring1 = accessorySlot("ring1", AuraAccessoryInventory.FIRST_RING,
                AuraAccessoryInventory.get(player, AuraAccessoryInventory.FIRST_RING));
        ItemSlotSnapshot ring2 = accessorySlot("ring2", AuraAccessoryInventory.SECOND_RING,
                AuraAccessoryInventory.get(player, AuraAccessoryInventory.SECOND_RING));
        ItemSlotSnapshot belt = accessorySlot("belt", AuraAccessoryInventory.BELT,
                AuraAccessoryInventory.get(player, AuraAccessoryInventory.BELT));
        ItemSlotSnapshot cursor = itemSlot("cursor", -1, "menu_cursor", menu.method_34255());
        if (amulet == null || ring1 == null || ring2 == null || belt == null || cursor == null) {
            return Optional.empty();
        }

        return Optional.of(new Snapshot(server.method_3780(), playerId.toString(),
                amulet, ring1, ring2, belt, cursor));
    }

    private static ItemSlotSnapshot accessorySlot(String name, int index, class_1799 stack) {
        return itemSlot(name, index, "accessory", stack);
    }

    private static ItemSlotSnapshot itemSlot(String name, int index, String section, class_1799 stack) {
        if (stack == null) {
            return null;
        }
        if (stack.method_7960()) {
            return new ItemSlotSnapshot(name, index, true, null, false);
        }
        int count = stack.method_7947();
        if (count <= 0) {
            return null;
        }

        ScenarioObservers.ItemSnapshot item = ScenarioObservers.snapshotItem(stack, section, index, count);
        boolean exact = !item.itemIdTruncated
                && !item.componentsTruncated
                && item.componentDigestStatus == ScenarioObservers.ComponentDigestStatus.COMPLETE
                && item.componentSetSha256 != null;
        return new ItemSlotSnapshot(name, index, false, item, exact);
    }

    public static final class Snapshot {
        public final long serverTick;
        public final String stateSource = "integrated_server_aura_accessories";
        public final boolean serverAuthoritative = true;
        public final String playerUuid;
        public final ItemSlotSnapshot amulet;
        public final ItemSlotSnapshot ring1;
        public final ItemSlotSnapshot ring2;
        public final ItemSlotSnapshot belt;
        public final ItemSlotSnapshot cursor;

        private Snapshot(long serverTick, String playerUuid, ItemSlotSnapshot amulet,
                ItemSlotSnapshot ring1, ItemSlotSnapshot ring2, ItemSlotSnapshot belt,
                ItemSlotSnapshot cursor) {
            this.serverTick = serverTick;
            this.playerUuid = playerUuid;
            this.amulet = amulet;
            this.ring1 = ring1;
            this.ring2 = ring2;
            this.belt = belt;
            this.cursor = cursor;
        }
    }

    public static final class ItemSlotSnapshot {
        public final String slot;
        public final int index;
        public final boolean empty;
        /** True only for an untruncated item ID and a complete component digest. */
        public final boolean exactItem;
        /** Null only when this slot is explicitly empty. */
        public final ScenarioObservers.ItemSnapshot item;

        private ItemSlotSnapshot(String slot, int index, boolean empty,
                ScenarioObservers.ItemSnapshot item, boolean exactItem) {
            this.slot = slot;
            this.index = index;
            this.empty = empty;
            this.item = item;
            this.exactItem = exactItem;
        }
    }
}
