package xyz.langyo.minecraft.mcp.common;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import net.minecraft.class_1799;
import net.minecraft.class_2338;
import net.minecraft.class_2586;
import net.minecraft.class_310;
import net.minecraft.class_638;
import net.minecraft.class_7923;
import pixlepix.auracascade.aura.AuraInspectionState;
import pixlepix.auracascade.aura.AuraStorage;
import pixlepix.auracascade.block.entity.AuraNetworkBlockEntity;
import pixlepix.auracascade.block.entity.AuraNodeBlockEntity;
import pixlepix.auracascade.block.entity.AuraPumpBlockEntity;
import pixlepix.auracascade.block.entity.AuraPumpLogic;
import pixlepix.auracascade.block.entity.StorageBookshelfBlockEntity;
import pixlepix.auracascade.item.books.StorageBookData;
import pixlepix.auracascade.parity.AuraColor;

/** Optional, direct typed adapter for the pinned Aura Cascade 0.2.1 artifact. */
public final class AuraScenarioObservers {
    public static final int MAX_AURA_COORDINATE_XZ = 30_000_000;
    public static final int MIN_AURA_COORDINATE_Y = -2_048;
    public static final int MAX_AURA_COORDINATE_Y = 4_095;
    public static final int MAX_STORAGE_ENTRIES = 64;

    private AuraScenarioObservers() {
    }

    static Optional<ScenarioObservers.AuraSnapshot> auraAt(class_310 client, int x, int y, int z) {
        return atWorld(client.field_1687, x, y, z, null);
    }

    static Optional<ScenarioObservers.AuraSnapshot> atWorld(net.minecraft.class_1937 level,
            int x, int y, int z, Long serverTick) {
        if (Math.abs((long) x) > MAX_AURA_COORDINATE_XZ
                || Math.abs((long) z) > MAX_AURA_COORDINATE_XZ
                || y < MIN_AURA_COORDINATE_Y || y > MAX_AURA_COORDINATE_Y) {
            return Optional.empty();
        }
        if (level == null) {
            return Optional.empty();
        }

        class_2338 pos = new class_2338(x, y, z);
        if (!level.method_22340(pos)) {
            return Optional.empty();
        }
        class_2586 blockEntity = level.method_8321(pos);
        long clientWorldGameTime = level.method_8510();
        if (blockEntity instanceof AuraNodeBlockEntity) {
            AuraNodeBlockEntity node = (AuraNodeBlockEntity) blockEntity;
            AuraInspectionState inspection = node.inspectionState();
            ScenarioObservers.NodeState nodeState = new ScenarioObservers.NodeState(
                    networkState(inspection), node.isCapacitor(), node.capacitorThreshold());
            return Optional.of(new ScenarioObservers.AuraSnapshot(x, y, z, blockId(node),
                    ScenarioObservers.AuraKind.NODE, clientWorldGameTime, serverTick, nodeState, null, null));
        }
        if (blockEntity instanceof AuraPumpBlockEntity) {
            AuraPumpBlockEntity pump = (AuraPumpBlockEntity) blockEntity;
            AuraInspectionState inspection = pump.inspectionState();
            AuraPumpLogic.PumpState pumpState = pump.pumpState();
            ScenarioObservers.PumpState state = new ScenarioObservers.PumpState(
                    networkState(inspection), pumpState.power(), pumpState.speed(), pump.pumpInhibited());
            return Optional.of(new ScenarioObservers.AuraSnapshot(x, y, z, blockId(pump),
                    ScenarioObservers.AuraKind.PUMP, clientWorldGameTime, serverTick, null, state, null));
        }
        if (blockEntity instanceof StorageBookshelfBlockEntity) {
            StorageBookshelfBlockEntity shelf = (StorageBookshelfBlockEntity) blockEntity;
            ScenarioObservers.BookshelfState state = bookshelfState(shelf);
            return Optional.of(new ScenarioObservers.AuraSnapshot(x, y, z, blockId(shelf),
                    ScenarioObservers.AuraKind.STORAGE_BOOKSHELF, clientWorldGameTime, serverTick, null, null, state));
        }
        return Optional.empty();
    }

    private static ScenarioObservers.NetworkState networkState(AuraInspectionState inspection) {
        AuraStorage storage = inspection.storage();
        LinkedHashMap<String, Integer> amounts = new LinkedHashMap<String, Integer>();
        long total = 0L;
        for (AuraColor color : AuraColor.values()) {
            int amount = Math.max(0, storage.get(color));
            amounts.put(color.id(), amount);
            total += amount;
        }
        return new ScenarioObservers.NetworkState(Collections.unmodifiableMap(amounts), total,
                inspection.linkedNodeCount(), Math.max(0, inspection.storedPower()),
                inspection.hasScannedLinks());
    }

    private static ScenarioObservers.BookshelfState bookshelfState(StorageBookshelfBlockEntity shelf) {
        boolean hasBook = shelf.hasBook();
        String bookItemId = hasBook ? ScenarioObservers.itemId(shelf.storedBook()) : null;
        List<StorageBookData.Entry> storedEntries = shelf.storedEntries();
        int returnedEntries = Math.min(storedEntries.size(), MAX_STORAGE_ENTRIES);
        ArrayList<ScenarioObservers.ItemSnapshot> entries = new ArrayList<ScenarioObservers.ItemSnapshot>(returnedEntries);
        boolean unsupported = false;
        for (int slot = 0; slot < returnedEntries; slot++) {
            StorageBookData.Entry entry = storedEntries.get(slot);
            class_1799 stack = entry.stack();
            ScenarioObservers.ItemSnapshot snapshot = ScenarioObservers.storageEntry(stack, slot, entry.count());
            entries.add(snapshot);
            if (snapshot.itemIdTruncated
                    || snapshot.componentDigestStatus != ScenarioObservers.ComponentDigestStatus.COMPLETE) {
                unsupported = true;
            }
        }

        boolean truncated = storedEntries.size() > MAX_STORAGE_ENTRIES;
        int storedTypes = shelf.storedTypes();
        int storedItemCount = shelf.storedItemCount();
        if (storedTypes < 0 || storedItemCount < 0) {
            unsupported = true;
        }
        if (!truncated) {
            long capturedItemCount = 0L;
            for (StorageBookData.Entry entry : storedEntries) {
                if (entry.count() < 0) {
                    unsupported = true;
                }
                capturedItemCount += entry.count();
            }
            if (storedTypes != storedEntries.size() || storedItemCount != capturedItemCount) {
                unsupported = true;
            }
        }
        ScenarioObservers.EntryDigestStatus status = truncated
                ? ScenarioObservers.EntryDigestStatus.TRUNCATED
                : unsupported ? ScenarioObservers.EntryDigestStatus.UNSUPPORTED
                : ScenarioObservers.EntryDigestStatus.COMPLETE;
        String digest = status == ScenarioObservers.EntryDigestStatus.COMPLETE
                ? ScenarioObservers.storageEntrySetDigest(entries) : null;
        return new ScenarioObservers.BookshelfState(hasBook, bookItemId, storedTypes, storedItemCount,
                entries, truncated, status, digest);
    }

    private static String blockId(class_2586 blockEntity) {
        Object identifier = class_7923.field_41175.method_10221(
                blockEntity.method_11010().method_26204());
        if (identifier == null) {
            return "unknown";
        }
        String value = String.valueOf(identifier);
        return value.length() <= ScenarioObservers.MAX_COMPONENT_ID_CHARS
                ? value : value.substring(0, ScenarioObservers.MAX_COMPONENT_ID_CHARS);
    }
}
