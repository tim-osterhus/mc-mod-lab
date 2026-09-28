package xyz.langyo.minecraft.mcp.common;

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import net.minecraft.class_1011;
import net.minecraft.class_2338;
import net.minecraft.class_239;
import net.minecraft.class_310;
import net.minecraft.class_318;
import net.minecraft.class_3965;
import net.minecraft.class_9779;

/** Bounded, read-only render evidence. Pixel candidates are NOT a visual verdict. */
public final class HudTraceRecorder {
    public static final int MAX_FRAMES = 1200;
    public static final int MAX_KEYFRAMES = 64;
    public static final int MAX_PNG_BYTES = 32 * 1024 * 1024;
    private static final long MAX_DURATION_NANOS = 30_000_000_000L;
    private static long renderSequence;
    private static Trace current;

    private HudTraceRecorder() { }

    public static synchronized String start(class_310 client) {
        requireClientThread(client);
        if (current != null && current.active) throw new IllegalStateException("trace already active");
        current = new Trace(renderSequence);
        return current.id;
    }

    public static synchronized void stop(class_310 client, String traceId) {
        requireClientThread(client);
        Trace trace = requireTrace(traceId);
        finish(trace, "stopped");
    }

    /** Cursor is the global render sequence, exclusive; zero reads the first batch. */
    public static synchronized Batch readBatch(String traceId, long afterSequence, int limit) {
        if (afterSequence < 0 || limit < 1 || limit > 32) throw new IllegalArgumentException("invalid batch bounds");
        Trace trace = requireTrace(traceId);
        List<Frame> result = trace.frames.stream().filter(f -> f.sequence > afterSequence).limit(limit).toList();
        return new Batch(trace.id, trace.active, trace.reason, trace.failure, trace.startSequence,
                (trace.active ? System.nanoTime() : trace.finishedNanos) - trace.startedNanos,
                trace.frames.size(), List.copyOf(trace.keyframes.keySet()), result);
    }

    public static synchronized byte[] keyframe(String traceId, long sequence) {
        byte[] png = requireTrace(traceId).keyframes.get(sequence);
        if (png == null) throw new IllegalArgumentException("keyframe unavailable");
        return png.clone();
    }

    public static synchronized void beginRender() {
        renderSequence++;
    }

    public static synchronized void endRender(class_310 client, class_9779 delta) {
        Trace trace = current;
        if (trace == null || !trace.active || renderSequence <= trace.startSequence) return;
        class_1011 pixels = null;
        try {
            long now = System.nanoTime();
            long expectedSequence = trace.previous == null ? trace.startSequence + 1 : trace.previous.sequence + 1;
            if (renderSequence != expectedSequence || now <= trace.lastNanos)
                throw new IllegalStateException("noncontiguous render evidence");
            var targetBuffer = client.method_1522();
            // Reject before screenshot allocation; two raw frames plus bounded PNGs are retained.
            if (targetBuffer.field_1482 < 1 || targetBuffer.field_1481 < 1
                    || targetBuffer.field_1482 > 1920 || targetBuffer.field_1481 > 1080)
                throw new IllegalStateException("framebuffer exceeds 1920x1080 capture budget");
            pixels = class_318.method_1663(targetBuffer);
            int width = pixels.method_4307(), height = pixels.method_4323();
            int guiWidth = client.method_22683().method_4486();
            int guiHeight = client.method_22683().method_4502();
            if (width < 1 || height < 1 || guiWidth < 1 || guiHeight < 1)
                throw new IllegalStateException("invalid framebuffer dimensions");
            Target target = target(client, delta);
            int valueX = 6 + client.field_1772.method_1727("White Aura: ");
            int valueY = 7 + client.field_1772.field_2000;
            Roi panel = measure(pixels, guiWidth, guiHeight, 0, 0, 320, 176);
            Roi value = measure(pixels, guiWidth, guiHeight, valueX, valueY, 96, client.field_1772.field_2000);
            Frame frame = new Frame(renderSequence, now - trace.startedNanos,
                    client.field_1687 == null ? null : client.field_1687.method_8510(),
                    width, height, guiWidth, guiHeight, client.field_1690.field_1883,
                    client.field_1755 != null, client.field_1690.field_1842,
                    client.method_53526().method_53536(), target, panel, value);
            boolean transition = trace.previous == null || !sameTarget(trace.previous.target, target)
                    || (trace.previous.target != null && target != null
                        && !java.util.Objects.equals(trace.previous.target.clientWhiteAura, target.clientWhiteAura))
                    || !trace.previous.valueRoi.rgbSha256.equals(value.rgbSha256)
                    || (trace.previous.valueRoi.whiteCandidatePixels == 0) != (value.whiteCandidatePixels == 0)
                    || trace.previous.screenOpen != frame.screenOpen || trace.previous.hideGui != frame.hideGui
                    || trace.previous.debugVisible != frame.debugVisible;
            trace.frames.add(frame);
            if (transition && trace.previous != null) retain(trace, trace.previous.sequence, trace.previousPixels);
            if (transition || now - trace.lastKeyframeNanos >= 1_000_000_000L) {
                retain(trace, frame.sequence, pixels);
                trace.lastKeyframeNanos = now;
            }
            if (trace.previousPixels != null) trace.previousPixels.close();
            trace.previousPixels = pixels;
            pixels = null;
            trace.previous = frame;
            trace.lastNanos = now;
            if (trace.frames.size() >= MAX_FRAMES) finish(trace, "frame_limit");
            else if (now - trace.startedNanos >= MAX_DURATION_NANOS) finish(trace, "duration_limit");
        } catch (Exception | LinkageError error) {
            trace.failure = "capture_failed:" + error.getClass().getSimpleName();
            finish(trace, "inconclusive");
        } finally {
            if (pixels != null) pixels.close();
        }
    }

    private static Target target(class_310 client, class_9779 delta) {
        if (client.field_1724 == null || client.field_1687 == null) return null;
        // Match Aura's block raycast, including its deliberate disregard for entity hits.
        class_239 hit = client.field_1724.method_5745(client.field_1724.method_55754(),
                delta.method_60637(true), false);
        if (!(hit instanceof class_3965 block) || hit.method_17783() != class_239.class_240.field_1332) return null;
        class_2338 pos = block.method_17777();
        var aura = ScenarioObservers.auraAt(client, pos.method_10263(), pos.method_10264(), pos.method_10260());
        Long white = null;
        boolean supported = false;
        String blockId = null;
        if (aura.isPresent()) {
            var snapshot = aura.get();
            blockId = snapshot.blockId;
            ScenarioObservers.NetworkState network = snapshot.node != null ? snapshot.node : snapshot.pump;
            if (network != null) {
                white = (long) network.auraByColor.getOrDefault("white", 0);
                supported = "en_us".equals(client.field_1690.field_1883)
                        && (snapshot.node == null || !snapshot.node.capacitor)
                        && network.auraByColor.entrySet().stream()
                            .noneMatch(e -> !"white".equals(e.getKey()) && e.getValue() > 0);
            }
        }
        return new Target(client.field_1687.method_27983().method_29177().toString(),
                pos.method_10263(), pos.method_10264(), pos.method_10260(), blockId, white, supported);
    }

    private static boolean sameTarget(Target a, Target b) {
        if (a == null || b == null) return a == b;
        return a.dimension.equals(b.dimension) && a.x == b.x && a.y == b.y && a.z == b.z
                && java.util.Objects.equals(a.blockId, b.blockId);
    }

    private static Roi measure(class_1011 image, int guiWidth, int guiHeight,
            int x, int y, int width, int height) throws Exception {
        int imageWidth = image.method_4307(), imageHeight = image.method_4323();
        int x0 = Math.min(imageWidth, Math.max(0, x * imageWidth / guiWidth));
        int y0 = Math.min(imageHeight, Math.max(0, y * imageHeight / guiHeight));
        int x1 = Math.min(imageWidth, (int) Math.ceil((x + width) * (double) imageWidth / guiWidth));
        int y1 = Math.min(imageHeight, (int) Math.ceil((y + height) * (double) imageHeight / guiHeight));
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        int candidates = 0;
        for (int py = y0; py < y1; py++) for (int px = x0; px < x1; px++) {
            int pixel = image.method_4315(px, py);
            int r = pixel & 255, g = pixel >>> 8 & 255, b = pixel >>> 16 & 255;
            digest.update((byte) r); digest.update((byte) g); digest.update((byte) b);
            if (Math.min(r, Math.min(g, b)) >= 235
                    && Math.max(r, Math.max(g, b)) - Math.min(r, Math.min(g, b)) <= 16) candidates++;
        }
        return new Roi(x0, y0, x1 - x0, y1 - y0, candidates, HexFormat.of().formatHex(digest.digest()));
    }

    private static void retain(Trace trace, long sequence, class_1011 pixels) throws Exception {
        if (trace.keyframes.containsKey(sequence)) return;
        if (trace.keyframes.size() >= MAX_KEYFRAMES) throw new IllegalStateException("keyframe_limit");
        byte[] png = pixels.method_24036();
        if (trace.pngBytes + png.length > MAX_PNG_BYTES) throw new IllegalStateException("png_bytes_limit");
        trace.keyframes.put(sequence, png);
        trace.pngBytes += png.length;
    }

    private static void finish(Trace trace, String reason) {
        if (!trace.active) return;
        if (trace.previous == null || renderSequence != trace.previous.sequence) {
            trace.failure = "incomplete_final_render";
            reason = "inconclusive";
        }
        try {
            if (trace.previous != null) retain(trace, trace.previous.sequence, trace.previousPixels);
        } catch (Exception error) {
            trace.failure = "final_keyframe_failed:" + error.getClass().getSimpleName();
            reason = "inconclusive";
        } finally {
            if (trace.previousPixels != null) trace.previousPixels.close();
            trace.previousPixels = null;
            trace.active = false;
            trace.reason = reason;
            trace.finishedNanos = System.nanoTime();
        }
    }

    private static Trace requireTrace(String id) {
        if (current == null || !current.id.equals(id)) throw new IllegalArgumentException("unknown trace");
        return current;
    }

    private static void requireClientThread(class_310 client) {
        if (client == null || !client.method_18854()) throw new IllegalStateException("client thread required");
    }

    private static final class Trace {
        final String id = UUID.randomUUID().toString();
        final long startSequence, startedNanos = System.nanoTime();
        final List<Frame> frames = new ArrayList<>();
        final Map<Long, byte[]> keyframes = new LinkedHashMap<>();
        boolean active = true;
        String reason = "recording", failure;
        long lastNanos, lastKeyframeNanos, finishedNanos;
        int pngBytes;
        Frame previous;
        class_1011 previousPixels;
        Trace(long startSequence) { this.startSequence = startSequence; }
    }

    public record Batch(String traceId, boolean active, String reason, String failure,
            long startSequence, long elapsedNanos, int frameCount, List<Long> keyframeSequences, List<Frame> frames) { }
    public record Frame(long sequence, long elapsedNanos, Long clientWorldTick,
            int framebufferWidth, int framebufferHeight, int guiWidth, int guiHeight,
            String language, boolean screenOpen, boolean hideGui, boolean debugVisible,
            Target target, Roi panelRoi, Roi valueRoi) { }
    public record Target(String dimension, int x, int y, int z, String blockId,
            Long clientWhiteAura, boolean whiteLayoutCandidate) { }
    public record Roi(int x, int y, int width, int height, int whiteCandidatePixels, String rgbSha256) { }
}
