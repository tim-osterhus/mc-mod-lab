package xyz.langyo.minecraft.mcp.common;

import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicBoolean;
import net.minecraft.class_310;

/** Fixed, typed scenario surface. Authentication is supplied by McpHttpServer. */
public final class ScenarioEndpoint implements HttpHandler {
    private static final Gson GSON = new Gson();
    private static final int MAX_BODY_BYTES = 4096;
    private static final AtomicBoolean ACTION_OUTCOME_UNCERTAIN = new AtomicBoolean(false);
    private static final Set<String> OBSERVATIONS = new HashSet<String>(
            Arrays.asList("server_tick", "player_inventory", "aura_block", "aura_block_server", "aura_pump_pair", "aura_storage_fixture", "ground_entities", "hud_batch", "hud_keyframe"));
    private static final Set<String> ACTIONS = new HashSet<String>(
            Arrays.asList("select_hotbar", "drop_selected", "aim_at_block", "use_item_at_block", "set_crouch", "hud_start", "hud_stop"));

    @Override
    public void handle(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            send(exchange, 405, error("method_not_allowed"));
            return;
        }
        Request request;
        try {
            request = parse(readBody(exchange));
        } catch (IllegalArgumentException exception) {
            send(exchange, 400, error("invalid_request"));
            return;
        }
        if ("hud_keyframe".equals(request.name)) {
            try {
                byte[] png = HudTraceRecorder.keyframe(request.traceId, request.sequence);
                exchange.getResponseHeaders().set("Content-Type", "image/png");
                exchange.getResponseHeaders().set("Cache-Control", "no-store");
                exchange.sendResponseHeaders(200, png.length);
                try (java.io.OutputStream output = exchange.getResponseBody()) { output.write(png); }
            } catch (IllegalArgumentException unavailable) {
                send(exchange, 422, error("keyframe_unavailable"));
            }
            return;
        }
        Object instance = ReflectionHelper.getMinecraftInstance();
        if (!(instance instanceof class_310)) {
            send(exchange, 503, error("client_unavailable"));
            return;
        }
        class_310 client = (class_310) instance;
        if ("action".equals(request.kind) && ACTION_OUTCOME_UNCERTAIN.get()) {
            send(exchange, 503, error("action_outcome_uncertain"));
            return;
        }
        AtomicReference<JsonObject> response = new AtomicReference<JsonObject>();
        AtomicBoolean expired = new AtomicBoolean(false);
        CountDownLatch done = new CountDownLatch(1);
        try {
            client.execute(new Runnable() {
                @Override
                public void run() {
                    boolean deferred = false;
                    try {
                        if (!expired.get()) {
                            if ("aura_block_server".equals(request.name)
                                    || "ground_entities".equals(request.name)
                                    || "aura_storage_fixture".equals(request.name)
                                    || "aura_pump_pair".equals(request.name)
                                    || "player_inventory".equals(request.name)) {
                                net.minecraft.class_1132 server = client.method_1576();
                                if (server == null || client.field_1687 == null || client.field_1724 == null) {
                                    response.set(unsupported(request));
                                } else {
                                    final net.minecraft.class_5321<net.minecraft.class_1937> dimension =
                                            client.field_1687.method_27983();
                                    final java.util.UUID playerId = client.field_1724.method_5667();
                                    server.execute(() -> {
                                        try {
                                            if (!expired.get()) {
                                                response.set(serverObservation(server, dimension, playerId, request));
                                            }
                                        } catch (RuntimeException | LinkageError failure) {
                                            response.set(error("capability_unavailable"));
                                        } finally {
                                            done.countDown();
                                        }
                                    });
                                    deferred = true;
                                }
                            } else {
                                response.set(dispatch(client, request));
                            }
                        }
                    } catch (RuntimeException | LinkageError failure) {
                        response.set(error("capability_unavailable"));
                    } finally {
                        if (!deferred) done.countDown();
                    }
                }
            });
        } catch (RuntimeException rejected) {
            send(exchange, 503, error("client_thread_unavailable"));
            return;
        }
        try {
            if (!done.await(3, TimeUnit.SECONDS)) {
                expired.set(true);
                if ("action".equals(request.kind)) ACTION_OUTCOME_UNCERTAIN.set(true);
                send(exchange, 504, error("client_thread_timeout"));
                return;
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            expired.set(true);
            if ("action".equals(request.kind)) ACTION_OUTCOME_UNCERTAIN.set(true);
            send(exchange, 503, error("interrupted"));
            return;
        }
        JsonObject result = response.get();
        send(exchange, "ok".equals(result.get("status").getAsString()) ? 200 : 422, result);
    }

    private static JsonObject unsupported(Request request) {
        JsonObject result = new JsonObject();
        result.addProperty("schema_version", 2);
        result.addProperty("kind", request.kind);
        result.addProperty("name", request.name);
        result.addProperty("status", "unsupported");
        return result;
    }

    private static JsonObject serverObservation(net.minecraft.class_1132 server,
            net.minecraft.class_5321<net.minecraft.class_1937> dimension,
            java.util.UUID playerId, Request request) {
        JsonObject result = unsupported(request);
        result.addProperty("server_tick_before", server.method_3780());
        net.minecraft.class_3218 level = server.method_3847(dimension);
        boolean inventory = "player_inventory".equals(request.name);
        Object payload = inventory ? ScenarioObservers.playerInventoryServer(server, playerId).orElse(null)
                : "ground_entities".equals(request.name)
                ? GroundEntityObservers.observe(server, playerId, request.radius).orElse(null)
                : "aura_storage_fixture".equals(request.name)
                ? ScenarioObservers.storageFixture(server, level, playerId, request.x, request.y, request.z)
                : "aura_pump_pair".equals(request.name)
                ? pumpPair(server, level, playerId, request)
                : ScenarioObservers.auraAtServer(level, request.x, request.y, request.z).orElse(null);
        result.addProperty("server_tick_after", server.method_3780());
        result.addProperty("observation_source", inventory ? "integrated_server_inventory"
                : "integrated_server_block_entity");
        if (payload != null) {
            result.addProperty("status", "ok");
            result.add("result", GSON.toJsonTree(payload));
        }
        return result;
    }

    private static JsonObject pumpPair(net.minecraft.class_1132 server, net.minecraft.class_3218 level,
            java.util.UUID playerId, Request request) {
        if (level == null || !server.method_18854()) return null;
        ScenarioObservers.AuraSnapshot pump = ScenarioObservers.auraAtServer(
                level, request.x, request.y, request.z).orElse(null);
        ScenarioObservers.AuraSnapshot target = ScenarioObservers.auraAtServer(
                level, request.x, request.targetY, request.z).orElse(null);
        if (pump == null || target == null || pump.kind != ScenarioObservers.AuraKind.PUMP
                || target.kind != ScenarioObservers.AuraKind.NODE) return null;
        ScenarioObservers.InventorySnapshot inventory = ScenarioObservers.playerInventoryServer(server, playerId).orElse(null);
        if (inventory == null) return null;
        boolean blocked = false;
        for (int y = request.y + 1; y < request.targetY; y++) {
            net.minecraft.class_2338 pos = new net.minecraft.class_2338(request.x, y, request.z);
            if (!level.method_22340(pos)) return null;
            if (level.method_8321(pos) != null) return null; // Intermediate consumers make pair accounting ambiguous.
            blocked |= level.method_8320(pos).method_26225();
        }
        java.util.List<net.minecraft.class_1542> items = level.method_18467(net.minecraft.class_1542.class,
                new net.minecraft.class_238(request.x - 3, request.y - 3, request.z - 3,
                        request.x + 4, request.y + 4, request.z + 4));
        if (items.size() > 64) return null;
        int coal = 0;
        for (net.minecraft.class_1542 item : items) {
            net.minecraft.class_1799 stack = item.method_6983();
            if ("minecraft:coal".equals(ScenarioObservers.itemId(stack))) coal += stack.method_7947();
        }
        JsonObject result = new JsonObject();
        result.addProperty("serverAuthoritative", true);
        result.addProperty("stateSource", "integrated_server_pump_pair");
        result.addProperty("serverTick", server.method_3780());
        result.addProperty("worldGameTime", level.method_8510());
        result.addProperty("routeBlocked", blocked);
        result.addProperty("nearbyCoalCount", coal);
        result.add("pump", GSON.toJsonTree(pump));
        result.add("target", GSON.toJsonTree(target));
        result.add("inventory", GSON.toJsonTree(inventory));
        return result;
    }

    private static JsonObject dispatch(class_310 client, Request request) {
        JsonObject result = new JsonObject();
        result.addProperty("schema_version", 2);
        result.addProperty("kind", request.kind);
        result.addProperty("name", request.name);
        java.util.OptionalLong before = ScenarioObservers.serverGameTick(client);
        if (before.isPresent()) {
            result.addProperty("server_tick_before", before.getAsLong());
        }
        Object payload = null;
        if ("observe".equals(request.kind)) {
            if ("hud_batch".equals(request.name)) {
                payload = HudTraceRecorder.readBatch(request.traceId, request.sequence, request.limit);
            } else if ("server_tick".equals(request.name)) {
                if (before.isPresent()) {
                    payload = before.getAsLong();
                }
            } else if ("player_inventory".equals(request.name)) {
                payload = ScenarioObservers.playerInventory(client).orElse(null);
            } else if ("aura_block".equals(request.name)) {
                payload = ScenarioObservers.auraAt(client, request.x, request.y, request.z).orElse(null);
            }
            result.addProperty("observation_source", "client_or_integrated_server_pointer");
        } else if ("hud_start".equals(request.name) || "hud_stop".equals(request.name)) {
            if (!ReflectionHelper.isMcpControlMode()) throw new IllegalStateException("control required");
            String traceId = request.traceId;
            if ("hud_start".equals(request.name)) traceId = HudTraceRecorder.start(client);
            else HudTraceRecorder.stop(client, traceId);
            JsonObject ack = new JsonObject();
            ack.addProperty("action", request.name);
            ack.addProperty("status", "input_dispatched");
            ack.addProperty("inputCalls", 1);
            ack.addProperty("traceId", traceId);
            ack.addProperty("detail", "capture lifecycle only; rendered evidence requires independent validation");
            payload = ack;
        } else if ("set_crouch".equals(request.name)) {
            payload = ScenarioActions.setCrouch(client, request.pressed);
        } else if ("select_hotbar".equals(request.name)) {
            payload = ScenarioActions.selectHotbar(client, request.slot, request.itemId);
        } else if ("drop_selected".equals(request.name)) {
            payload = ScenarioActions.dropSelected(client, request.count);
        } else if ("aim_at_block".equals(request.name)) {
            payload = ScenarioActions.aimAtBlock(client, request.x, request.y, request.z, request.blockId);
        } else if ("use_item_at_block".equals(request.name)) {
            payload = ScenarioActions.useItemAtBlock(client, request.x, request.y, request.z, request.blockId);
        }
        java.util.OptionalLong after = ScenarioObservers.serverGameTick(client);
        if (after.isPresent()) {
            result.addProperty("server_tick_after", after.getAsLong());
        }
        if (payload == null) {
            result.addProperty("status", "unsupported");
        } else {
            result.addProperty("status", "ok");
            result.add("result", GSON.toJsonTree(payload));
        }
        return result;
    }

    private static Request parse(String body) {
        JsonObject value;
        try {
            JsonReader reader = new JsonReader(new StringReader(body));
            value = strictObject(reader, true);
            if (reader.peek() != JsonToken.END_DOCUMENT) {
                throw new IllegalArgumentException("trailing JSON");
            }
        } catch (IOException | RuntimeException invalid) {
            throw new IllegalArgumentException("invalid JSON", invalid);
        }
        fields(value, "schema_version", "kind", "name", "params");
        if (!value.has("schema_version") || !"2".equals(value.get("schema_version").toString())) {
            throw new IllegalArgumentException("schema version required");
        }
        String kind = string(value, "kind");
        String name = string(value, "name");
        if (!("observe".equals(kind) && OBSERVATIONS.contains(name)
                || "action".equals(kind) && ACTIONS.contains(name))) {
            throw new IllegalArgumentException("capability unavailable");
        }
        JsonObject params = value.has("params") && value.get("params").isJsonObject()
                ? value.getAsJsonObject("params") : null;
        if (params == null) {
            throw new IllegalArgumentException("params object required");
        }
        Request request = new Request(kind, name);
        if ("server_tick".equals(name) || "player_inventory".equals(name) || "hud_start".equals(name)) {
            fields(params);
        } else if ("hud_stop".equals(name) || "hud_batch".equals(name) || "hud_keyframe".equals(name)) {
            if ("hud_stop".equals(name)) fields(params, "trace_id");
            else if ("hud_batch".equals(name)) fields(params, "trace_id", "after_sequence", "limit");
            else fields(params, "trace_id", "sequence");
            request.traceId = string(params, "trace_id");
            if (!java.util.UUID.fromString(request.traceId).toString().equals(request.traceId))
                throw new IllegalArgumentException("canonical trace ID required");
            if ("hud_batch".equals(name)) {
                request.sequence = integer(params, "after_sequence", 0, Integer.MAX_VALUE);
                request.limit = integer(params, "limit", 1, 32);
            } else if ("hud_keyframe".equals(name)) {
                request.sequence = integer(params, "sequence", 1, Integer.MAX_VALUE);
            }
        } else if ("ground_entities".equals(name)) {
            fields(params, "radius");
            request.radius = integer(params, "radius", 1, 16);
        } else if ("set_crouch".equals(name)) {
            fields(params, "pressed");
            if (!params.get("pressed").isJsonPrimitive() || !params.get("pressed").getAsJsonPrimitive().isBoolean())
                throw new IllegalArgumentException("pressed must be boolean");
            request.pressed = params.get("pressed").getAsBoolean();
        } else if ("drop_selected".equals(name)) {
            fields(params, "count");
            request.count = integer(params, "count", 1, 64);
        } else if ("select_hotbar".equals(name)) {
            fields(params, "slot", "item_id");
            request.slot = integer(params, "slot", 0, 8);
            request.itemId = registryId(params, "item_id");
        } else {
            if ("aura_pump_pair".equals(name)) {
                fields(params, "x", "y", "z", "target_y");
                request.targetY = integer(params, "target_y", -64, 319);
            } else if ("aura_block".equals(name) || "aura_block_server".equals(name) || "aura_storage_fixture".equals(name)) {
                fields(params, "x", "y", "z");
            } else {
                fields(params, "x", "y", "z", "block_id");
            }
            request.x = integer(params, "x", -30000000, 30000000);
            request.y = integer(params, "y", -64, 319);
            request.z = integer(params, "z", -30000000, 30000000);
            if ("aura_pump_pair".equals(name)) {
                if (request.targetY <= request.y || request.targetY > request.y + 15)
                    throw new IllegalArgumentException("target must be within upward fixture range");
            } else if (!"aura_block".equals(name) && !"aura_block_server".equals(name) && !"aura_storage_fixture".equals(name)) {
                request.blockId = registryId(params, "block_id");
            }
        }
        return request;
    }

    private static JsonObject strictObject(JsonReader reader, boolean allowNested)
            throws IOException {
        if (reader.peek() != JsonToken.BEGIN_OBJECT) {
            throw new IllegalArgumentException("object required");
        }
        JsonObject object = new JsonObject();
        reader.beginObject();
        while (reader.hasNext()) {
            String key = reader.nextName();
            if (object.has(key)) {
                throw new IllegalArgumentException("duplicate field");
            }
            JsonToken token = reader.peek();
            if (token == JsonToken.BEGIN_OBJECT && allowNested && "params".equals(key)) {
                object.add(key, strictObject(reader, false));
            } else if (token == JsonToken.STRING) {
                object.addProperty(key, reader.nextString());
            } else if (token == JsonToken.NUMBER) {
                object.addProperty(key, new java.math.BigDecimal(reader.nextString()));
            } else if (token == JsonToken.BOOLEAN) {
                object.addProperty(key, reader.nextBoolean());
            } else {
                throw new IllegalArgumentException("unsupported JSON value");
            }
        }
        reader.endObject();
        return object;
    }

    private static void fields(JsonObject object, String... allowed) {
        Set<String> names = new HashSet<String>(Arrays.asList(allowed));
        if (object.size() != names.size()) {
            throw new IllegalArgumentException("incorrect fields");
        }
        for (String name : object.keySet()) {
            if (!names.contains(name)) {
                throw new IllegalArgumentException("unknown field");
            }
        }
    }

    private static String string(JsonObject object, String name) {
        JsonElement value = object.get(name);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) {
            throw new IllegalArgumentException("string required");
        }
        return value.getAsString();
    }

    private static String registryId(JsonObject object, String name) {
        String value = string(object, name);
        if (value.length() > 128 || !value.matches("[a-z0-9_.-]+:[a-z0-9_./-]+")) {
            throw new IllegalArgumentException("invalid registry id");
        }
        return value;
    }

    private static int integer(JsonObject object, String name, int minimum, int maximum) {
        JsonElement value = object.get(name);
        if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()
                || !value.getAsString().matches("-?[0-9]{1,8}")) {
            throw new IllegalArgumentException("integer required");
        }
        int number = Integer.parseInt(value.getAsString());
        if (number < minimum || number > maximum) {
            throw new IllegalArgumentException("integer out of range");
        }
        return number;
    }

    private static String readBody(HttpExchange exchange) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        InputStream input = exchange.getRequestBody();
        byte[] buffer = new byte[1024];
        int count;
        while ((count = input.read(buffer)) >= 0) {
            if (output.size() + count > MAX_BODY_BYTES) {
                throw new IllegalArgumentException("request too large");
            }
            output.write(buffer, 0, count);
        }
        return new String(output.toByteArray(), StandardCharsets.UTF_8);
    }

    private static JsonObject error(String code) {
        JsonObject value = new JsonObject();
        value.addProperty("schema_version", 2);
        value.addProperty("status", "error");
        value.addProperty("error", code);
        return value;
    }

    private static void send(HttpExchange exchange, int code, JsonObject body) throws IOException {
        byte[] bytes = GSON.toJson(body).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(code, bytes.length);
        try (java.io.OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static final class Request {
        final String kind;
        final String name;
        int x;
        int y;
        int z;
        int targetY;
        int radius;
        int sequence;
        int limit;
        String traceId;
        int slot;
        int count;
        String itemId;
        String blockId;
        boolean pressed;

        Request(String kind, String name) {
            this.kind = kind;
            this.name = name;
        }
    }
}
