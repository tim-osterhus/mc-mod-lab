package xyz.langyo.minecraft.mcp.common;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.Set;
import net.minecraft.class_2479;
import net.minecraft.class_2487;
import net.minecraft.class_2491;
import net.minecraft.class_2495;
import net.minecraft.class_2499;
import net.minecraft.class_2501;
import net.minecraft.class_2514;
import net.minecraft.class_2519;
import net.minecraft.class_2520;
import net.minecraft.class_9279;

import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.class_1661;
import net.minecraft.class_1799;
import net.minecraft.class_310;
import net.minecraft.class_746;
import net.minecraft.class_7923;
import net.minecraft.class_9323;
import net.minecraft.class_9331;

/**
 * Read-only typed observations for the pinned Minecraft 1.21.1 intermediary
 * client. Call client observations on the Minecraft client thread. This class
 * does not schedule work or mutate game state.
 */
public final class ScenarioObservers {
    public static final int MAX_INVENTORY_STACKS = 41;
    public static final int MAX_COMPONENTS_PER_STACK = 24;
    public static final int MAX_COMPONENT_ID_CHARS = 128;
    public static final int MAX_COMPONENT_VALUE_CHARS = 128;
    static final int MAX_CUSTOM_DATA_CANONICAL_BYTES = 16 * 1024;
    static final int MAX_CUSTOM_DATA_CANONICAL_ENTRIES = 2048;
    static final int MAX_CUSTOM_DATA_DEPTH = 32;

    private ScenarioObservers() {
    }

    /**
     * Returns the integrated singleplayer server tick counter (ticks since
     * that server started). Remote multiplayer clients do not expose their
     * server object, so they return empty. This reads one value and never waits
     * for a tick.
     */
    public static OptionalLong serverGameTick(class_310 client) {
        if (client == null) {
            return OptionalLong.empty();
        }
        net.minecraft.class_1132 server = client.method_1576();
        if (server == null) {
            return OptionalLong.empty();
        }
        return OptionalLong.of(server.method_3780());
    }

    /** Returns occupied main, armor, and offhand stacks; empty slots are omitted. */
    public static Optional<InventorySnapshot> playerInventory(class_310 client) {
        if (client == null || client.field_1724 == null) {
            return Optional.empty();
        }

        class_746 player = client.field_1724;
        return inventorySnapshot(player.method_31548(), null, player.method_5715());
    }

    public static Optional<InventorySnapshot> playerInventoryServer(
            net.minecraft.class_1132 server, java.util.UUID playerId) {
        if (server == null || !server.method_18854() || playerId == null) return Optional.empty();
        net.minecraft.class_3222 player = server.method_3760().method_14602(playerId);
        if (player == null) return Optional.empty();
        return inventorySnapshot(player.method_31548(), (long) server.method_3780(), player.method_5715());
    }

    private static Optional<InventorySnapshot> inventorySnapshot(class_1661 inventory, Long tick, boolean crouching) {
        ArrayList<ItemSnapshot> stacks = new ArrayList<ItemSnapshot>(MAX_INVENTORY_STACKS);
        boolean truncated = appendStacks(stacks, inventory.field_7547, "main");
        if (!truncated) {
            truncated = appendStacks(stacks, inventory.field_7548, "armor");
        }
        if (!truncated) {
            truncated = appendStacks(stacks, inventory.field_7544, "offhand");
        }
        return Optional.of(new InventorySnapshot(stacks, truncated, tick, crouching));
    }

    /**
     * Aura support is optional. The Aura-linked adapter class is reached only
     * after Fabric confirms the exact Aura mod id is loaded.
     */
    public static Optional<AuraSnapshot> auraAt(class_310 client, int x, int y, int z) {
        if (client == null || !FabricLoader.getInstance().isModLoaded("aura")) {
            return Optional.empty();
        }
        try {
            return AuraScenarioObservers.auraAt(client, x, y, z);
        } catch (NoClassDefFoundError | NoSuchMethodError incompatibleAura) {
            return Optional.empty();
        }
    }

    public static Optional<AuraSnapshot> auraAtServer(net.minecraft.class_3218 level,
            int x, int y, int z) {
        if (level == null || !level.method_8503().method_18854()
                || !FabricLoader.getInstance().isModLoaded("aura")) {
            return Optional.empty();
        }
        try {
            return AuraScenarioObservers.atWorld(level, x, y, z,
                    (long) level.method_8503().method_3780());
        } catch (NoClassDefFoundError | NoSuchMethodError incompatibleAura) {
            return Optional.empty();
        }
    }

    static com.google.gson.JsonObject storageFixture(net.minecraft.class_1132 server,
            net.minecraft.class_3218 level, java.util.UUID playerId, int x, int y, int z) {
        if (!FabricLoader.getInstance().isModLoaded("aura")) return null;
        try {
            return AuraScenarioObservers.storageFixture(server, level, playerId, x, y, z);
        } catch (NoClassDefFoundError | NoSuchMethodError incompatibleAura) {
            return null;
        }
    }

    private static boolean appendStacks(List<ItemSnapshot> output, List<class_1799> stacks, String section) {
        for (int slot = 0; slot < stacks.size(); slot++) {
            class_1799 stack = stacks.get(slot);
            int count = stack.method_7947();
            if (count <= 0) {
                continue;
            }
            if (output.size() >= MAX_INVENTORY_STACKS) {
                return true;
            }
            output.add(snapshotItem(stack, section, slot, count));
        }
        return false;
    }

    static ItemSnapshot storageEntry(class_1799 stack, int slot, int count) {
        return snapshotItem(stack, "storage", slot, Math.max(0, count));
    }

    static ItemSnapshot entityItem(class_1799 stack, int index) {
        return snapshotItem(stack, "ground", index, stack.method_7947());
    }

    static String itemId(class_1799 stack) {
        Object registeredItemId = class_7923.field_41178.method_10221(stack.method_7909());
        String rawItemId = registeredItemId == null ? null : String.valueOf(registeredItemId);
        return rawItemId == null ? "unknown" : clip(rawItemId, MAX_COMPONENT_ID_CHARS);
    }

    private static ItemSnapshot snapshotItem(class_1799 stack, String section, int slot, int count) {
        Object registeredItemId = class_7923.field_41178.method_10221(stack.method_7909());
        String rawItemId = registeredItemId == null ? null : String.valueOf(registeredItemId);
        String itemId = rawItemId == null ? "unknown" : clip(rawItemId, MAX_COMPONENT_ID_CHARS);
        ComponentList componentList = components(stack);
        return new ItemSnapshot(section, slot, itemId, count, rawItemId == null
                || rawItemId.length() > MAX_COMPONENT_ID_CHARS, componentList);
    }

    private static ComponentList components(class_1799 stack) {
        // Item ID plus this patch uniquely identifies components against the pinned registry defaults.
        Set<Map.Entry<class_9331<?>, Optional<?>>> types = stack.method_57380().method_57846();
        ArrayList<ComponentSnapshot> values = new ArrayList<ComponentSnapshot>(
                Math.min(types.size(), MAX_COMPONENTS_PER_STACK));
        ArrayList<String> canonicalEntries = new ArrayList<String>(
                Math.min(types.size(), MAX_COMPONENTS_PER_STACK));
        ArrayList<String> unsupportedIds = new ArrayList<String>();
        int seen = 0;
        boolean valueTruncated = false;
        for (Map.Entry<class_9331<?>, Optional<?>> entry : types) {
            if (seen++ >= MAX_COMPONENTS_PER_STACK) {
                break;
            }
            class_9331<?> type = entry.getKey();
            Object registeredTypeId = class_7923.field_49658.method_10221(type);
            String rawId = registeredTypeId == null ? null : String.valueOf(registeredTypeId);
            String id = rawId == null ? "unknown" : clip(rawId, MAX_COMPONENT_ID_CHARS);
            boolean idTruncated = rawId == null || rawId.length() > MAX_COMPONENT_ID_CHARS;
            ComponentSnapshot value = entry.getValue().isPresent()
                    ? componentSnapshot(id, idTruncated, entry.getValue().get())
                    : new ComponentSnapshot(id, "removed", null, false, idTruncated,
                            idTruncated ? ComponentDigestStatus.UNSUPPORTED : ComponentDigestStatus.COMPLETE,
                            idTruncated ? null : sha256("minecraft-component-removal-v1\n" + id));
            valueTruncated |= value.digestStatus == ComponentDigestStatus.TRUNCATED;
            values.add(value);
            if (value.canonicalSha256 == null) {
                unsupportedIds.add(id);
            } else {
                canonicalEntries.add(id + "\u0000" + value.valueKind + "\u0000" + value.canonicalSha256);
            }
        }

        boolean truncated = types.size() > MAX_COMPONENTS_PER_STACK || valueTruncated;
        ComponentDigestStatus status = truncated ? ComponentDigestStatus.TRUNCATED
                : unsupportedIds.isEmpty() ? ComponentDigestStatus.COMPLETE : ComponentDigestStatus.UNSUPPORTED;
        String componentSetSha256 = status == ComponentDigestStatus.COMPLETE
                ? componentSetDigest(canonicalEntries) : null;
        return new ComponentList(values, unsupportedIds, types.size(), truncated, status, componentSetSha256);
    }

    private static ComponentSnapshot componentSnapshot(String id, boolean idTruncated, Object value) {
        if ("minecraft:custom_data".equals(id)) {
            if (idTruncated || !(value instanceof class_9279)) {
                return new ComponentSnapshot(id, "nbt_compound", null, false, idTruncated,
                        ComponentDigestStatus.UNSUPPORTED, null);
            }
            NbtDigestResult customData = customDataDigest((class_9279) value);
            return new ComponentSnapshot(id, "nbt_compound", null, false, false,
                    customData.status, customData.sha256);
        }

        String kind;
        String canonicalValue;
        String displayValue;
        boolean displayTruncated = false;
        if (value instanceof Integer) {
            kind = "integer";
            canonicalValue = String.valueOf(value);
            displayValue = canonicalValue;
        } else if (value instanceof Boolean) {
            kind = "boolean";
            canonicalValue = String.valueOf(value);
            displayValue = canonicalValue;
        } else if (value instanceof Long) {
            kind = "long";
            canonicalValue = String.valueOf(value);
            displayValue = canonicalValue;
        } else if (value instanceof Short) {
            kind = "short";
            canonicalValue = String.valueOf(value);
            displayValue = canonicalValue;
        } else if (value instanceof Byte) {
            kind = "byte";
            canonicalValue = String.valueOf(value);
            displayValue = canonicalValue;
        } else if (value instanceof Float) {
            kind = "float";
            canonicalValue = Integer.toHexString(Float.floatToIntBits(((Float) value).floatValue()));
            displayValue = String.valueOf(value);
        } else if (value instanceof Double) {
            kind = "double";
            canonicalValue = Long.toHexString(Double.doubleToLongBits(((Double) value).doubleValue()));
            displayValue = String.valueOf(value);
        } else if (value instanceof String) {
            kind = "string";
            canonicalValue = null;
            displayValue = (String) value;
        } else if (value instanceof Enum<?>) {
            kind = "enum";
            canonicalValue = ((Enum<?>) value).name();
            displayValue = canonicalValue;
        } else {
            kind = "structured";
            canonicalValue = null;
            displayValue = null;
        }
        if (displayValue != null && displayValue.length() > MAX_COMPONENT_VALUE_CHARS) {
            displayValue = clip(displayValue, MAX_COMPONENT_VALUE_CHARS);
            displayTruncated = true;
        }

        boolean supported = !idTruncated && isSupportedComponent(id, value);
        String componentSha256 = supported
                ? sha256("minecraft-item-component-v1\n" + id + "\n" + kind + "\n" + canonicalValue + "\n")
                : null;
        return new ComponentSnapshot(id, kind, displayValue, displayTruncated,
                idTruncated, supported ? ComponentDigestStatus.COMPLETE : ComponentDigestStatus.UNSUPPORTED,
                componentSha256);
    }

    /** Only these pinned vanilla scalar types receive canonical payload digests. */
    private static boolean isSupportedComponent(String id, Object value) {
        if ("minecraft:damage".equals(id) || "minecraft:max_damage".equals(id)
                || "minecraft:max_stack_size".equals(id) || "minecraft:repair_cost".equals(id)) {
            return value instanceof Integer;
        }
        return "minecraft:enchantment_glint_override".equals(id) && value instanceof Boolean;
    }

    private static String componentSetDigest(List<String> entries) {
        Collections.sort(entries);
        StringBuilder canonical = new StringBuilder("minecraft-item-component-patch-v1\n");
        canonical.append(entries.size()).append('\n');
        for (String entry : entries) {
            canonical.append(entry.length()).append(':').append(entry).append('\n');
        }
        return sha256(canonical.toString());
    }

    private static NbtDigestResult customDataDigest(class_9279 customData) {
        try {
            MessageDigest digest = newSha256();
            NbtBudget budget = new NbtBudget();
            budget.writeUtf8(digest, "minecraft-item-custom-data-v1\n");
            budget.writeUtf8(digest, "minecraft:custom_data\n");
            class_2487 root = customData.method_57463();
            if (root == null) {
                throw new UnsupportedNbtValue();
            }
            writeNbtTag(digest, root, 0, budget);
            return new NbtDigestResult(ComponentDigestStatus.COMPLETE, hexDigest(digest.digest()));
        } catch (TruncatedNbtValue tooLarge) {
            return new NbtDigestResult(ComponentDigestStatus.TRUNCATED, null);
        } catch (UnsupportedNbtValue unsupported) {
            return new NbtDigestResult(ComponentDigestStatus.UNSUPPORTED, null);
        }
    }

    /** Streams a typed canonical representation; no NBT text or raw payload is returned. */
    private static void writeNbtTag(MessageDigest digest, class_2520 tag, int depth, NbtBudget budget) {
        if (tag == null) {
            throw new UnsupportedNbtValue();
        }
        if (depth > MAX_CUSTOM_DATA_DEPTH) {
            throw new TruncatedNbtValue();
        }

        int tagId = tag.method_10711() & 0xff;
        budget.writeByte(digest, tagId);
        switch (tagId) {
            case 0:
                if (!(tag instanceof class_2491)) {
                    throw new UnsupportedNbtValue();
                }
                return;
            case 1:
            case 2:
            case 3:
            case 4:
            case 5:
            case 6:
                if (!(tag instanceof class_2514)) {
                    throw new UnsupportedNbtValue();
                }
                writeNbtNumber(digest, tagId, (class_2514) tag, budget);
                return;
            case 7:
                if (!(tag instanceof class_2479)) {
                    throw new UnsupportedNbtValue();
                }
                writeNbtByteArray(digest, (class_2479) tag, budget);
                return;
            case 8:
                if (!(tag instanceof class_2519)) {
                    throw new UnsupportedNbtValue();
                }
                budget.writeUtf8(digest, tag.method_10714());
                return;
            case 9:
                if (!(tag instanceof class_2499)) {
                    throw new UnsupportedNbtValue();
                }
                writeNbtList(digest, (class_2499) tag, depth, budget);
                return;
            case 10:
                if (!(tag instanceof class_2487)) {
                    throw new UnsupportedNbtValue();
                }
                writeNbtCompound(digest, (class_2487) tag, depth, budget);
                return;
            case 11:
                if (!(tag instanceof class_2495)) {
                    throw new UnsupportedNbtValue();
                }
                writeNbtIntArray(digest, (class_2495) tag, budget);
                return;
            case 12:
                if (!(tag instanceof class_2501)) {
                    throw new UnsupportedNbtValue();
                }
                writeNbtLongArray(digest, (class_2501) tag, budget);
                return;
            default:
                throw new UnsupportedNbtValue();
        }
    }

    private static void writeNbtNumber(MessageDigest digest, int tagId, class_2514 number, NbtBudget budget) {
        switch (tagId) {
            case 1:
                budget.writeByte(digest, number.method_10698());
                return;
            case 2:
                budget.writeShort(digest, number.method_10696());
                return;
            case 3:
                budget.writeInt(digest, number.method_10701());
                return;
            case 4:
                budget.writeLong(digest, number.method_10699());
                return;
            case 5:
                budget.writeInt(digest, Float.floatToRawIntBits(number.method_10700()));
                return;
            case 6:
                budget.writeLong(digest, Double.doubleToRawLongBits(number.method_10697()));
                return;
            default:
                throw new UnsupportedNbtValue();
        }
    }

    private static void writeNbtByteArray(MessageDigest digest, class_2479 array, NbtBudget budget) {
        byte[] values = array.method_10521();
        budget.consumeEntries(values.length);
        budget.writeInt(digest, values.length);
        budget.writeBytes(digest, values, 0, values.length);
    }

    private static void writeNbtIntArray(MessageDigest digest, class_2495 array, NbtBudget budget) {
        int[] values = array.method_10588();
        budget.consumeEntries(values.length);
        budget.writeInt(digest, values.length);
        for (int value : values) {
            budget.writeInt(digest, value);
        }
    }

    private static void writeNbtLongArray(MessageDigest digest, class_2501 array, NbtBudget budget) {
        long[] values = array.method_10615();
        budget.consumeEntries(values.length);
        budget.writeInt(digest, values.length);
        for (long value : values) {
            budget.writeLong(digest, value);
        }
    }

    private static void writeNbtList(MessageDigest digest, class_2499 list, int depth, NbtBudget budget) {
        int size = list.size();
        budget.consumeEntries(size);
        budget.writeInt(digest, size);
        for (int index = 0; index < size; index++) {
            writeNbtTag(digest, list.method_10534(index), depth + 1, budget);
        }
    }

    private static void writeNbtCompound(MessageDigest digest, class_2487 compound, int depth, NbtBudget budget) {
        int size = compound.method_10546();
        budget.consumeEntries(size);
        budget.writeInt(digest, size);
        ArrayList<String> keys = new ArrayList<String>(compound.method_10541());
        if (keys.size() != size) {
            throw new UnsupportedNbtValue();
        }
        Collections.sort(keys);
        for (String key : keys) {
            budget.writeUtf8(digest, key);
            writeNbtTag(digest, compound.method_10580(key), depth + 1, budget);
        }
    }

    private static MessageDigest newSha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is required by the Java runtime", impossible);
        }
    }

    private static String hexDigest(byte[] digest) {
        char[] hex = new char[digest.length * 2];
        final char[] alphabet = "0123456789abcdef".toCharArray();
        for (int i = 0; i < digest.length; i++) {
            int value = digest[i] & 0xff;
            hex[i * 2] = alphabet[value >>> 4];
            hex[i * 2 + 1] = alphabet[value & 0x0f];
        }
        return new String(hex);
    }

    static String storageEntrySetDigest(List<ItemSnapshot> entries) {
        ArrayList<String> canonicalEntries = new ArrayList<String>(entries.size());
        for (ItemSnapshot entry : entries) {
            canonicalEntries.add(entry.itemId.length() + ":" + entry.itemId + ":" + entry.count + ":"
                    + entry.componentSetSha256);
        }
        Collections.sort(canonicalEntries);
        StringBuilder canonical = new StringBuilder("aura-storage-entry-set-v1\n");
        canonical.append(canonicalEntries.size()).append('\n');
        for (String entry : canonicalEntries) {
            canonical.append(entry.length()).append(':').append(entry).append('\n');
        }
        return sha256(canonical.toString());
    }

    private static String sha256(String canonical) {
        return hexDigest(newSha256().digest(canonical.getBytes(StandardCharsets.UTF_8)));
    }

    private static String clip(String value, int maximumLength) {
        return value.length() <= maximumLength ? value : value.substring(0, maximumLength);
    }

    public static final class InventorySnapshot {
        public final List<ItemSnapshot> stacks;
        public final boolean truncated;
        public final boolean serverAuthoritative;
        public final String stateSource;
        public final Long serverTick;
        public final boolean crouching;

        private InventorySnapshot(List<ItemSnapshot> stacks, boolean truncated, Long tick, boolean crouching) {
            this.stacks = Collections.unmodifiableList(new ArrayList<ItemSnapshot>(stacks));
            this.truncated = truncated;
            this.serverTick = tick;
            this.serverAuthoritative = tick != null;
            this.stateSource = tick == null ? "client_inventory_cache" : "integrated_server_inventory";
            this.crouching = crouching;
        }
    }

    public static final class ItemSnapshot {
        public final String componentBasis = "patch_against_pinned_registry_defaults";
        public final String section;
        public final int slot;
        public final String itemId;
        public final int count;
        public final boolean itemIdTruncated;
        public final List<ComponentSnapshot> components;
        public final int componentCount;
        public final boolean componentsTruncated;
        public final ComponentDigestStatus componentDigestStatus;
        /** Null unless every component was captured and canonicalized. */
        public final String componentSetSha256;
        public final List<String> unsupportedComponentIds;

        private ItemSnapshot(String section, int slot, String itemId, int count,
                boolean itemIdTruncated, ComponentList components) {
            this.section = section;
            this.slot = slot;
            this.itemId = itemId;
            this.count = count;
            this.itemIdTruncated = itemIdTruncated;
            this.components = components.values;
            this.componentCount = components.componentCount;
            this.componentsTruncated = components.truncated;
            this.componentDigestStatus = components.status;
            this.componentSetSha256 = components.componentSetSha256;
            this.unsupportedComponentIds = components.unsupportedIds;
        }
    }

    public static final class ComponentSnapshot {
        public final String id;
        public final String valueKind;
        /** Null for structured payloads whose contents are intentionally omitted. */
        public final String value;
        public final boolean valueTruncated;
        public final boolean idTruncated;
        public final ComponentDigestStatus digestStatus;
        /** Null for unsupported types or values. */
        public final String canonicalSha256;

        private ComponentSnapshot(String id, String valueKind, String value, boolean valueTruncated,
                boolean idTruncated, ComponentDigestStatus digestStatus, String canonicalSha256) {
            this.id = id;
            this.valueKind = valueKind;
            this.value = value;
            this.valueTruncated = valueTruncated;
            this.idTruncated = idTruncated;
            this.digestStatus = digestStatus;
            this.canonicalSha256 = canonicalSha256;
        }
    }

    public enum ComponentDigestStatus {
        COMPLETE,
        UNSUPPORTED,
        TRUNCATED
    }

    public static final class AuraSnapshot {
        public final int x;
        public final int y;
        public final int z;
        public final String blockId;
        public final AuraKind kind;
        public final Long clientWorldGameTime;
        public final Long serverWorldGameTime;
        public final Long serverTick;
        public final String stateSource;
        public final boolean serverAuthoritative;
        public final String perBlockSyncTick;
        public final NodeState node;
        public final PumpState pump;
        public final BookshelfState bookshelf;

        AuraSnapshot(int x, int y, int z, String blockId, AuraKind kind, long clientWorldGameTime,
                NodeState node, PumpState pump, BookshelfState bookshelf) {
            this(x, y, z, blockId, kind, clientWorldGameTime, null, node, pump, bookshelf);
        }

        AuraSnapshot(int x, int y, int z, String blockId, AuraKind kind, long worldGameTime,
                Long serverTick, NodeState node, PumpState pump, BookshelfState bookshelf) {
            this.x = x;
            this.y = y;
            this.z = z;
            this.blockId = blockId;
            this.kind = kind;
            this.clientWorldGameTime = serverTick == null ? worldGameTime : null;
            this.serverWorldGameTime = serverTick == null ? null : worldGameTime;
            this.serverTick = serverTick;
            this.stateSource = serverTick == null ? "client_world_block_entity_cache"
                    : "integrated_server_block_entity";
            this.serverAuthoritative = serverTick != null;
            this.perBlockSyncTick = "unavailable";
            this.node = node;
            this.pump = pump;
            this.bookshelf = bookshelf;
        }
    }

    public enum AuraKind {
        NODE,
        PUMP,
        STORAGE_BOOKSHELF
    }

    public static class NetworkState {
        public final Map<String, Integer> auraByColor;
        public final long totalAura;
        public final int linkedNodeCount;
        public final int storedPower;
        public final boolean hasScannedLinks;

        NetworkState(Map<String, Integer> auraByColor, long totalAura,
                int linkedNodeCount, int storedPower, boolean hasScannedLinks) {
            this.auraByColor = Collections.unmodifiableMap(auraByColor);
            this.totalAura = totalAura;
            this.linkedNodeCount = linkedNodeCount;
            this.storedPower = storedPower;
            this.hasScannedLinks = hasScannedLinks;
        }
    }

    public static final class NodeState extends NetworkState {
        public final boolean capacitor;
        public final int capacitorThreshold;

        NodeState(NetworkState network, boolean capacitor, int capacitorThreshold) {
            super(network.auraByColor, network.totalAura, network.linkedNodeCount,
                    network.storedPower, network.hasScannedLinks);
            this.capacitor = capacitor;
            this.capacitorThreshold = capacitorThreshold;
        }
    }

    public static final class PumpState extends NetworkState {
        public final int power;
        public final int speed;
        public final boolean inhibited;

        PumpState(NetworkState network, int power, int speed, boolean inhibited) {
            super(network.auraByColor, network.totalAura, network.linkedNodeCount,
                    network.storedPower, network.hasScannedLinks);
            this.power = Math.max(0, power);
            this.speed = Math.max(0, speed);
            this.inhibited = inhibited;
        }
    }

    public enum EntryDigestStatus {
        COMPLETE,
        UNSUPPORTED,
        TRUNCATED
    }

    public static final class BookshelfState {
        public final boolean hasBook;
        public final String bookItemId;
        public final int storedTypes;
        public final int storedItemCount;
        public final List<ItemSnapshot> entries;
        public final boolean entriesTruncated;
        public final EntryDigestStatus entryDigestStatus;
        /** Null unless every stored entry and component is fully supported. */
        public final String entrySetSha256;

        BookshelfState(boolean hasBook, String bookItemId, int storedTypes, int storedItemCount,
                List<ItemSnapshot> entries, boolean entriesTruncated,
                EntryDigestStatus entryDigestStatus, String entrySetSha256) {
            this.hasBook = hasBook;
            this.bookItemId = bookItemId;
            this.storedTypes = storedTypes;
            this.storedItemCount = storedItemCount;
            this.entries = Collections.unmodifiableList(new ArrayList<ItemSnapshot>(entries));
            this.entriesTruncated = entriesTruncated;
            this.entryDigestStatus = entryDigestStatus;
            this.entrySetSha256 = entrySetSha256;
        }
    }

    private static final class ComponentList {
        private final List<ComponentSnapshot> values;
        private final List<String> unsupportedIds;
        private final int componentCount;
        private final boolean truncated;
        private final ComponentDigestStatus status;
        private final String componentSetSha256;

        private ComponentList(List<ComponentSnapshot> values, List<String> unsupportedIds,
                int componentCount, boolean truncated, ComponentDigestStatus status, String componentSetSha256) {
            this.values = Collections.unmodifiableList(new ArrayList<ComponentSnapshot>(values));
            this.unsupportedIds = Collections.unmodifiableList(new ArrayList<String>(unsupportedIds));
            this.componentCount = componentCount;
            this.truncated = truncated;
            this.status = status;
            this.componentSetSha256 = componentSetSha256;
        }
    }

    private static final class NbtBudget {
        private int bytesWritten;
        private int entriesVisited;

        private void consumeEntries(int count) {
            if (count < 0 || count > MAX_CUSTOM_DATA_CANONICAL_ENTRIES - entriesVisited) {
                throw new TruncatedNbtValue();
            }
            entriesVisited += count;
        }

        private void writeByte(MessageDigest digest, int value) {
            ensureBytes(1);
            digest.update((byte) value);
            bytesWritten++;
        }

        private void writeShort(MessageDigest digest, short value) {
            ensureBytes(2);
            digest.update((byte) (value >>> 8));
            digest.update((byte) value);
            bytesWritten += 2;
        }

        private void writeInt(MessageDigest digest, int value) {
            ensureBytes(4);
            digest.update((byte) (value >>> 24));
            digest.update((byte) (value >>> 16));
            digest.update((byte) (value >>> 8));
            digest.update((byte) value);
            bytesWritten += 4;
        }

        private void writeLong(MessageDigest digest, long value) {
            ensureBytes(8);
            for (int shift = 56; shift >= 0; shift -= 8) {
                digest.update((byte) (value >>> shift));
            }
            bytesWritten += 8;
        }

        private void writeBytes(MessageDigest digest, byte[] values, int offset, int length) {
            ensureBytes(length);
            digest.update(values, offset, length);
            bytesWritten += length;
        }

        private void writeUtf8(MessageDigest digest, String value) {
            if (value == null) {
                throw new UnsupportedNbtValue();
            }
            int available = MAX_CUSTOM_DATA_CANONICAL_BYTES - bytesWritten - 4;
            if (available < 0 || value.length() > available) {
                throw new TruncatedNbtValue();
            }
            int encodedLength = utf8Length(value, available);
            writeInt(digest, encodedLength);
            byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
            if (encoded.length != encodedLength) {
                throw new UnsupportedNbtValue();
            }
            writeBytes(digest, encoded, 0, encoded.length);
        }

        private int utf8Length(String value, int limit) {
            int length = 0;
            for (int index = 0; index < value.length(); index++) {
                char current = value.charAt(index);
                if (current <= 0x7f) {
                    length++;
                } else if (current <= 0x7ff) {
                    length += 2;
                } else if (Character.isHighSurrogate(current)) {
                    if (index + 1 >= value.length() || !Character.isLowSurrogate(value.charAt(index + 1))) {
                        throw new UnsupportedNbtValue();
                    }
                    length += 4;
                    index++;
                } else if (Character.isLowSurrogate(current)) {
                    throw new UnsupportedNbtValue();
                } else {
                    length += 3;
                }
                if (length > limit) {
                    throw new TruncatedNbtValue();
                }
            }
            return length;
        }

        private void ensureBytes(int count) {
            if (count < 0 || count > MAX_CUSTOM_DATA_CANONICAL_BYTES - bytesWritten) {
                throw new TruncatedNbtValue();
            }
        }
    }

    private static final class NbtDigestResult {
        private final ComponentDigestStatus status;
        private final String sha256;

        private NbtDigestResult(ComponentDigestStatus status, String sha256) {
            this.status = status;
            this.sha256 = sha256;
        }
    }

    private static final class TruncatedNbtValue extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }

    private static final class UnsupportedNbtValue extends RuntimeException {
        private static final long serialVersionUID = 1L;
    }
}
