package lab.gametest;

import com.google.gson.GsonBuilder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.LinkedHashMap;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipFile;
import java.util.Map;
import net.fabricmc.fabric.api.gametest.v1.FabricGameTest;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.class_2246;
import net.minecraft.class_2338;
import net.minecraft.class_4516;
import net.minecraft.class_6302;
import pixlepix.auracascade.block.AuraContent;
import pixlepix.auracascade.block.entity.AuraNetworkBlockEntity;
import pixlepix.auracascade.parity.AuraColor;

/** Pinned 1.21.1 intermediary API. Initial input injection is not a player action. */
public final class AuraTransferTests implements FabricGameTest {
    private static final String RELEASE_SHA =
        "2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8";
    private record Sample(long tick, int source, int target, int sourcePower, int targetPower) {}
    private Map<String, Object> loaded;

    @class_6302(method_35936 = FabricGameTest.EMPTY_STRUCTURE, method_35932 = 100)
    public void conservedTransfer(class_4516 test) throws Exception {
        loaded = new LinkedHashMap<>();
        for (String id : List.of("minecraft", "fabricloader", "fabric-api", "fabric-gametest-api-v1",
                "patchouli", "aura", "mc-mod-lab-gametest")) {
            var container = FabricLoader.getInstance().getModContainer(id).orElseThrow();
            List<String> hashes = new ArrayList<>();
            List<String> contents = new ArrayList<>();
            for (Path path : container.getOrigin().getPaths()) {
                if (!Files.isRegularFile(path)) throw new IllegalStateException("Nonpackaged loaded origin");
                hashes.add(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(Files.readAllBytes(path))));
                contents.add(contentHash(path));
            }
            loaded.put(id, Map.of("version", container.getMetadata().getVersion().getFriendlyString(),
                "origin_sha256", hashes, "origin_content_sha256", contents));
        }
        var mod = FabricLoader.getInstance().getModContainer("aura").orElseThrow();
        var paths = mod.getOrigin().getPaths();
        if (paths.size() != 1 || !Files.isRegularFile(paths.getFirst())) {
            throw new IllegalStateException("A single packaged Aura release is required");
        }
        String sha = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
            .digest(Files.readAllBytes(paths.getFirst())));
        if (!RELEASE_SHA.equals(sha)) throw new IllegalStateException("Wrong Aura release bytes");
        boolean blocked = Boolean.getBoolean("mc-mod-lab.gametest.blocked");
        class_2338 sourcePos = new class_2338(2, 4, 2);
        class_2338 targetPos = new class_2338(2, 1, 2);
        test.method_35984(sourcePos, AuraContent.AURA_NODE);
        test.method_35984(targetPos, AuraContent.AURA_NODE);
        if (blocked) test.method_35984(new class_2338(2, 3, 2), class_2246.field_10340);
        AuraNetworkBlockEntity source = (AuraNetworkBlockEntity) test.method_36014(sourcePos);
        AuraNetworkBlockEntity target = (AuraNetworkBlockEntity) test.method_36014(targetPos);
        test.method_46226(source.inspectionState().totalAura() == 0
            && target.inspectionState().totalAura() == 0, "Fixture must begin empty");
        source.feedCrystal(AuraColor.WHITE, 1000);
        List<Sample> samples = new ArrayList<>();
        samples.add(sample(0, source, target));
        // Never call the transfer kernel or tick methods: world block tickers do all work.
        for (int tick = 1; tick <= 80; tick++) {
            final int at = tick;
            test.method_35951(at, () -> {
                Sample current = sample(test.method_36045(), source, target);
                samples.add(current);
                boolean conserved = current.source >= 0 && current.target >= 0
                    && current.source + current.target == 1000;
                if (!conserved || at == 80) {
                    writeEvidence(sha, blocked, samples);
                }
                test.method_46226(conserved, "Aura must remain exactly 1000 on every sampled tick");
                if (at == 80) {
                    test.method_46226(current.target > 0 && current.source < 1000,
                        "Expected earned source-to-target transfer by tick 80");
                    test.method_36036();
                }
            });
        }
    }

    private static Sample sample(long tick, AuraNetworkBlockEntity source, AuraNetworkBlockEntity target) {
        return new Sample(tick, source.inspectionState().totalAura(),
            target.inspectionState().totalAura(), source.storedPower(), target.storedPower());
    }

    private static String contentHash(Path path) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (ZipFile archive = new ZipFile(path.toFile())) {
            for (String name : archive.stream().filter(e -> !e.isDirectory())
                    .map(e -> e.getName()).sorted().toList()) {
                digest.update(name.getBytes(StandardCharsets.UTF_8));
                digest.update((byte) 0);
                try (var stream = archive.getInputStream(archive.getEntry(name))) {
                    digest.update(MessageDigest.getInstance("SHA-256").digest(stream.readAllBytes()));
                }
            }
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private void writeEvidence(String sha, boolean blocked, List<Sample> samples) {
        try {
            var report = Map.of("schema_version", 1, "artifact_sha256", sha,
                "minecraft", "1.21.1", "blocked", blocked, "test", "auratransfertests.conservedtransfer",
                "fixture_injection", "two placed nodes; source.feedCrystal(WHITE,1000) before ticking; optional stone obstruction",
                "samples", samples, "loaded_mods", loaded);
            Path path = Path.of("gametest-observations.json");
            if (Files.exists(path)) throw new IllegalStateException("Evidence already exists");
            Files.writeString(path, new GsonBuilder().setPrettyPrinting().create().toJson(report));
        } catch (Exception error) {
            throw new IllegalStateException("Cannot save GameTest evidence", error);
        }
    }
}
