package xyz.langyo.minecraft.mcp.common;

import com.google.gson.JsonObject;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import java.io.IOException;
import java.io.StringReader;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import net.minecraft.class_1132;
import net.minecraft.class_1937;
import net.minecraft.class_2338;
import net.minecraft.class_310;
import net.minecraft.class_3218;
import net.minecraft.class_3222;
import net.minecraft.class_5321;

/** Private QA-only, read-only probe for the two exact server chunk predicates. */
public final class ChunkPresenceHandler implements HttpHandler {
    private static final int MAX_BODY_BYTES = 512;

    @Override
    public void handle(HttpExchange exchange) throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            send(exchange, 405, error("method_not_allowed"));
            return;
        }
        Request request;
        try {
            byte[] body = exchange.getRequestBody().readNBytes(MAX_BODY_BYTES + 1);
            if (body.length > MAX_BODY_BYTES) throw new IllegalArgumentException();
            request = parse(new String(body, StandardCharsets.UTF_8));
        } catch (IOException | RuntimeException invalid) {
            send(exchange, 400, error("invalid_request"));
            return;
        }
        Object instance = ReflectionHelper.getMinecraftInstance();
        if (!(instance instanceof class_310 client)) {
            send(exchange, 422, error("client_unavailable"));
            return;
        }
        AtomicReference<Result> result = new AtomicReference<>();
        AtomicBoolean expired = new AtomicBoolean(false);
        CountDownLatch done = new CountDownLatch(1);
        try {
            client.execute(() -> {
                if (expired.get()) { done.countDown(); return; }
                try {
                    if (!client.method_18854() || !ReflectionHelper.isMcpControlMode()
                            || client.field_1687 == null || client.field_1724 == null) {
                        result.set(new Result(422, error("capability_unavailable")));
                        done.countDown();
                        return;
                    }
                    class_1132 server = client.method_1576();
                    if (server == null) {
                        result.set(new Result(422, error("integrated_server_required")));
                        done.countDown();
                        return;
                    }
                    class_5321<class_1937> dimension = client.field_1687.method_27983();
                    UUID playerId = client.field_1724.method_5667();
                    server.execute(() -> {
                        try {
                            if (!expired.get()) result.set(observe(server, dimension, playerId, request));
                        } catch (RuntimeException | LinkageError unavailable) {
                            result.set(new Result(422, error("capability_unavailable")));
                        } finally {
                            done.countDown();
                        }
                    });
                } catch (RuntimeException | LinkageError unavailable) {
                    result.set(new Result(422, error("capability_unavailable")));
                    done.countDown();
                }
            });
            if (!done.await(3, TimeUnit.SECONDS)) {
                expired.set(true);
                send(exchange, 503, error("server_thread_timeout"));
                return;
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            expired.set(true);
            send(exchange, 503, error("interrupted"));
            return;
        } catch (RuntimeException unavailable) {
            send(exchange, 503, error("client_thread_unavailable"));
            return;
        }
        Result observed = result.get();
        if (observed == null) {
            send(exchange, 503, error("observation_unavailable"));
        } else {
            send(exchange, observed.code(), observed.body());
        }
    }

    private static Result observe(class_1132 server, class_5321<class_1937> dimension,
            UUID playerId, Request request) {
        if (!server.method_18854()) return new Result(422, error("server_thread_required"));
        class_3218 level = server.method_3847(dimension);
        class_3222 player = server.method_3760().method_14602(playerId);
        if (level == null || player == null || player.method_51469() != level)
            return new Result(422, error("player_dimension_changed"));
        long tick = server.method_3780();
        class_2338 pos = new class_2338(request.x(), request.y(), request.z());
        JsonObject value = new JsonObject();
        value.addProperty("serverTick", tick);
        value.addProperty("stateSource", "integrated_server_chunk_presence");
        value.addProperty("serverAuthoritative", true);
        value.addProperty("dimension", level.method_27983().method_29177().toString());
        value.addProperty("x", request.x());
        value.addProperty("y", request.y());
        value.addProperty("z", request.z());
        value.addProperty("hasChunkAt", level.method_22340(pos));
        value.addProperty("entityTicking", level.method_37118(pos));
        JsonObject response = new JsonObject();
        response.addProperty("schema_version", 2);
        response.addProperty("kind", "observe");
        response.addProperty("name", "chunk_presence");
        response.addProperty("status", "ok");
        response.addProperty("server_tick_before", tick);
        response.addProperty("server_tick_after", server.method_3780());
        response.addProperty("observation_source", "integrated_server_chunk_presence");
        response.add("result", value);
        return new Result(200, response);
    }

    private static Request parse(String body) throws IOException {
        JsonReader reader = new JsonReader(new StringReader(body));
        reader.setLenient(false);
        reader.beginObject();
        Set<String> fields = new HashSet<>();
        int version = -1;
        String kind = null;
        String name = null;
        Request request = null;
        while (reader.hasNext()) {
            String field = reader.nextName();
            if (!fields.add(field)) throw new IllegalArgumentException("duplicate field");
            switch (field) {
                case "schema_version" -> version = integer(reader, 2, 2);
                case "kind" -> kind = string(reader);
                case "name" -> name = string(reader);
                case "params" -> request = parameters(reader);
                default -> throw new IllegalArgumentException("unknown field");
            }
        }
        reader.endObject();
        if (reader.peek() != JsonToken.END_DOCUMENT || fields.size() != 4 || version != 2
                || !"observe".equals(kind) || !"chunk_presence".equals(name) || request == null)
            throw new IllegalArgumentException("invalid envelope");
        return request;
    }

    private static Request parameters(JsonReader reader) throws IOException {
        reader.beginObject();
        Set<String> fields = new HashSet<>();
        Integer x = null, y = null, z = null;
        while (reader.hasNext()) {
            String field = reader.nextName();
            if (!fields.add(field)) throw new IllegalArgumentException("duplicate coordinate");
            switch (field) {
                case "x" -> x = integer(reader, -30000000, 30000000);
                case "y" -> y = integer(reader, -64, 319);
                case "z" -> z = integer(reader, -30000000, 30000000);
                default -> throw new IllegalArgumentException("unknown coordinate");
            }
        }
        reader.endObject();
        if (fields.size() != 3 || x == null || y == null || z == null)
            throw new IllegalArgumentException("missing coordinate");
        return new Request(x, y, z);
    }

    private static int integer(JsonReader reader, int minimum, int maximum) throws IOException {
        if (reader.peek() != JsonToken.NUMBER) throw new IllegalArgumentException("integer required");
        String raw = reader.nextString();
        if (!raw.matches("-?[0-9]{1,8}")) throw new IllegalArgumentException("integer required");
        int value = Integer.parseInt(raw);
        if (value < minimum || value > maximum) throw new IllegalArgumentException("integer out of range");
        return value;
    }

    private static String string(JsonReader reader) throws IOException {
        if (reader.peek() != JsonToken.STRING) throw new IllegalArgumentException("string required");
        return reader.nextString();
    }

    private static JsonObject error(String code) {
        JsonObject result = new JsonObject();
        result.addProperty("status", "unsupported");
        result.addProperty("error", code);
        return result;
    }

    private static void send(HttpExchange exchange, int code, JsonObject value) throws IOException {
        byte[] body = value.toString().getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(code, body.length);
        try (var output = exchange.getResponseBody()) { output.write(body); }
    }

    private record Request(int x, int y, int z) { }
    private record Result(int code, JsonObject body) { }
}
