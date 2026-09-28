package xyz.langyo.minecraft.mcp.common;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import net.minecraft.class_1132;
import net.minecraft.class_1297;
import net.minecraft.class_1309;
import net.minecraft.class_1542;
import net.minecraft.class_238;
import net.minecraft.class_243;
import net.minecraft.class_2960;
import net.minecraft.class_3218;
import net.minecraft.class_3222;
import net.minecraft.class_5321;
import net.minecraft.class_5575;
import net.minecraft.class_7923;

/** Bounded, read-only observations from the integrated server thread. */
public final class GroundEntityObservers {
    public static final int MAX_ENTITIES = 64;
    public static final double MIN_RADIUS = 1.0;
    public static final double MAX_RADIUS = 16.0;
    private static final int MAX_REGISTRY_ID_CHARS = 128;

    private GroundEntityObservers() {
    }

    /**
     * Observes entity centers within a 3D radius of the server player. The
     * horizontal chunk columns intersecting the query box must already be
     * loaded; this method never requests chunks. It returns empty off-thread,
     * for invalid input or identity, incomplete loaded-region coverage, or
     * more than {@link #MAX_ENTITIES} matching entities.
     * Exact item claims require each item's componentDigestStatus to be
     * COMPLETE, componentsTruncated to be false, and componentSetSha256 non-null.
     */
    public static Optional<Snapshot> observe(class_1132 server, UUID playerId, double radius) {
        if (server == null || playerId == null || !Double.isFinite(radius)
                || radius < MIN_RADIUS || radius > MAX_RADIUS || !server.method_18854()) {
            return Optional.empty();
        }

        class_3222 player = server.method_3760().method_14602(playerId);
        if (player == null) {
            return Optional.empty();
        }
        class_3218 level = player.method_51469();
        class_243 playerPosition = player.method_19538();
        if (level == null || player.method_37908() != level || !finite(playerPosition)) {
            return Optional.empty();
        }
        class_5321<?> dimensionKey = level.method_27983();
        class_2960 dimensionLocation = dimensionKey == null ? null : dimensionKey.method_29177();
        String dimensionId = dimensionLocation == null ? null : String.valueOf(dimensionLocation);
        if (dimensionId == null || dimensionId.length() > MAX_REGISTRY_ID_CHARS) {
            return Optional.empty();
        }

        double x = playerPosition.field_1352;
        double y = playerPosition.field_1351;
        double z = playerPosition.field_1350;
        double minX = x - radius;
        double minY = y - radius;
        double minZ = z - radius;
        double maxX = x + radius;
        double maxY = y + radius;
        double maxZ = z + radius;
        if (!finite(minX, minY, minZ) || !finite(maxX, maxY, maxZ)
                || minX < Integer.MIN_VALUE || minY < Integer.MIN_VALUE || minZ < Integer.MIN_VALUE
                || maxX > Integer.MAX_VALUE || maxY > Integer.MAX_VALUE || maxZ > Integer.MAX_VALUE) {
            return Optional.empty();
        }

        int minChunkX = ((int) Math.floor(minX)) >> 4;
        int maxChunkX = ((int) Math.floor(maxX)) >> 4;
        int minChunkZ = ((int) Math.floor(minZ)) >> 4;
        int maxChunkZ = ((int) Math.floor(maxZ)) >> 4;
        for (int chunkX = minChunkX; chunkX <= maxChunkX; chunkX++) {
            for (int chunkZ = minChunkZ; chunkZ <= maxChunkZ; chunkZ++) {
                if (!level.method_8393(chunkX, chunkZ)) {
                    return Optional.empty();
                }
            }
        }

        class_238 bounds = new class_238(minX, minY, minZ, maxX, maxY, maxZ);
        ArrayList<class_1297> nearby = new ArrayList<class_1297>(MAX_ENTITIES + 1);
        double radiusSquared = radius * radius;
        level.method_47575(class_5575.method_31795(class_1297.class), bounds, entity -> {
            double dx = entity.method_23317() - x;
            double dy = entity.method_23318() - y;
            double dz = entity.method_23321() - z;
            return dx * dx + dy * dy + dz * dz <= radiusSquared;
        }, nearby, MAX_ENTITIES + 1);
        if (nearby.size() > MAX_ENTITIES) {
            return Optional.empty();
        }

        ArrayList<EntitySnapshot> snapshots = new ArrayList<EntitySnapshot>(nearby.size());
        int itemIndex = 0;
        for (class_1297 entity : nearby) {
            Object registeredId = class_7923.field_41177.method_10221(entity.method_5864());
            String entityId = registeredId == null ? null : String.valueOf(registeredId);
            class_243 position = entity.method_19538();
            class_243 velocity = entity.method_18798();
            if (entityId == null || entityId.length() > MAX_REGISTRY_ID_CHARS
                    || !finite(position) || !finite(velocity)) {
                return Optional.empty();
            }

            Float health = null;
            if (entity instanceof class_1309) {
                health = Float.valueOf(((class_1309) entity).method_6032());
                if (!Float.isFinite(health.floatValue())) {
                    return Optional.empty();
                }
            }

            ScenarioObservers.ItemSnapshot item = null;
            if (entity instanceof class_1542) {
                item = ScenarioObservers.entityItem(((class_1542) entity).method_6983(), itemIndex++);
            }
            UUID entityUuid = entity.method_5667();
            if (entityUuid == null) {
                return Optional.empty();
            }
            snapshots.add(new EntitySnapshot(entityId, entityUuid, entity.method_5805(),
                    new VectorSnapshot(position), new VectorSnapshot(velocity), health, item));
        }

        return Optional.of(new Snapshot(playerId, dimensionId, radius,
                new VectorSnapshot(playerPosition), server.method_3780(), snapshots));
    }

    private static boolean finite(class_243 vector) {
        return vector != null && finite(vector.field_1352, vector.field_1351, vector.field_1350);
    }

    private static boolean finite(double x, double y, double z) {
        return Double.isFinite(x) && Double.isFinite(y) && Double.isFinite(z);
    }

    public static final class Snapshot {
        public final boolean serverAuthoritative = true;
        public final String stateSource = "integrated_server_ground_entities";
        public final UUID playerId;
        public final String dimensionId;
        public final double radius;
        public final VectorSnapshot playerPosition;
        public final long serverTick;
        public final List<EntitySnapshot> entities;

        private Snapshot(UUID playerId, String dimensionId, double radius,
                VectorSnapshot playerPosition, long serverTick, List<EntitySnapshot> entities) {
            this.playerId = playerId;
            this.dimensionId = dimensionId;
            this.radius = radius;
            this.playerPosition = playerPosition;
            this.serverTick = serverTick;
            this.entities = Collections.unmodifiableList(new ArrayList<EntitySnapshot>(entities));
        }
    }

    public static final class EntitySnapshot {
        public final String entityId;
        public final UUID uuid;
        public final boolean alive;
        public final VectorSnapshot position;
        public final VectorSnapshot velocity;
        /** Null for non-living entities. */
        public final Float health;
        /** Present only for dropped item entities. */
        public final ScenarioObservers.ItemSnapshot item;

        private EntitySnapshot(String entityId, UUID uuid, boolean alive,
                VectorSnapshot position, VectorSnapshot velocity, Float health,
                ScenarioObservers.ItemSnapshot item) {
            this.entityId = entityId;
            this.uuid = uuid;
            this.alive = alive;
            this.position = position;
            this.velocity = velocity;
            this.health = health;
            this.item = item;
        }
    }

    public static final class VectorSnapshot {
        public final double x;
        public final double y;
        public final double z;

        private VectorSnapshot(class_243 vector) {
            this(vector.field_1352, vector.field_1351, vector.field_1350);
        }

        private VectorSnapshot(double x, double y, double z) {
            this.x = x;
            this.y = y;
            this.z = z;
        }
    }
}
