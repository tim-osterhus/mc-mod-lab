# Fabric GameTest deterministic lane

Milestone 4 adds one bounded **real in-world** deterministic test, not a client
driver or Survival agent. It runs the exact packaged Aura 0.2.1 release in a
fresh Fabric 1.21.1 headless GameTest server. Its reports cannot approve GUI,
HUD, player input, multiplayer, or visual parity.

## Supported profile

The fixed [reviewed inventory](../examples/gametest-runtime-1.21.1.json) pins
the installed Fabric server launcher, Minecraft server, every required library,
Fabric Loader 0.19.1, Fabric API 0.116.11+1.21.1, GameTest API
2.0.5+6fc22b9919, Patchouli 1.21.1-93-FABRIC, and Aura
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
All were already available locally. The runner downloads nothing, copies only
explicitly listed executable inputs, and does not copy source worlds, configs,
credentials, or extra discovered mods. No Minecraft or third-party JAR is
distributed in this repository/plugin.

Java 21 and the reviewed local runtime are **trusted executable inputs**.
Hash agreement prevents accidental substitution; it is not a sandbox or
cryptographic attestation against a compromised host. Symlinks and Windows
reparse-point ancestors are refused. Existing output directories are refused.
Only the owned child receives cleanup, with a bounded graceful stop attempt
before forced termination on a guard failure. Forced cleanup cannot pass.
The Python helper plus Java workload is sampled every half second with a
3800 MiB private/working-set guard and a 180-second runtime bound. This is a
sampled guard, not a hard operating-system memory limit.

Fabric's cached module implements the `fabric-gametest` entrypoint and the
`fabric-api.gametest` / `fabric-api.gametest.report-file` system properties.
The latter must include a parent directory for this API version. The
[1.21.1 official testing guide](https://docs.fabricmc.net/1.21.1/develop/automatic-testing)
distinguishes unit tests from GameTest, but currently documents only unit-test
setup. This adapter was compiled and run against the cached GameTest API itself,
not inferred from the JUnit guide. No target-mod Gradle build is involved.

## Build and run

Supply reviewed existing files; placeholders below are not download commands:

```text
python scripts/build_gametest_adapter.py --jdk-bin JAVA21_BIN --minecraft INTERMEDIARY_1211_JAR --aura RELEASE_021_JAR --gametest GAMETEST_API_JAR --fabric-loader LOADER_COMPILE_JAR --gson GSON_JAR --work NEW_BUILD_DIR --output NEW_ADAPTER_JAR
python gametest_runtime.py --runtime REVIEWED_SERVER_ROOT --java JAVA21_EXE --aura RELEASE_021_JAR --fabric-api FABRIC_API_JAR --patchouli PATCHOULI_JAR --gametest GAMETEST_API_JAR --adapter REVIEWED_ADAPTER_JAR --adapter-sha256 REVIEWED_ADAPTER_SHA256 --out NEW_POSITIVE_PROFILE
python gametest_import.py NEW_POSITIVE_PROFILE --adapter-sha256 REVIEWED_ADAPTER_SHA256
python lab.py validate parity NEW_POSITIVE_PROFILE/parity.json --portable
```

The compiler uses `--release 21`, no annotation processors, and a 512 MiB heap.
The adapter ZIP uses stable entry timestamps. Review source/compiler inputs and
the printed adapter hash before launching it. The public runtime requires the
explicit reviewed adapter hash independently of its staged inventory.

Repeat the same runtime command with **another fresh** output directory and
`--blocked`. Import that profile too. Its XML test and deterministic parity
status must remain **fail**; `expected_outcome_verified: true` separately means
the intended negative was demonstrated. Repeat the positive on a third fresh
profile when checking the failing/corrected sequence. Never reuse output from
a crashed, incomplete, or modified fixture.

## Fixture and acceptance

The adapter places ordinary Aura nodes at relative `(2,4,2)` and `(2,1,2)` in
Fabric's empty structure. It verifies both empty, then calls
`source.feedCrystal(WHITE,1000)` **once before ticking**. This is disclosed
initial-state injection, not crystal pickup or a real-player-use claim. No
transfer method, block ticker, or final aura value is invoked/injected by the
test. Actual server block tickers perform the transfer. The blocked fixture
adds stone at `(2,3,2)` and otherwise runs the same positive test.

The test observes ticks 0 through 80, requiring nonnegative source/target and
an exact sum of 1000 at each sample. The positive must end with earned target
aura and reduced source aura. The negative must retain 1000/0 throughout and
fail the specific earned-transfer assertion. Falling-power values are recorded,
not independently certified as a general power formula. GameTest runs accelerated
logical ticks; these results do not establish ordinary wall-clock 20 TPS timing.

The importer refuses missing/duplicate/skipped/extra cases, malformed XML,
entity declarations, inconsistent declared totals, wrong failure reasons,
incomplete tick sequences, altered artifacts, mismatched loaded versions or
origins, guard violations, and wrong process outcomes. Patchouli registers its
own `patchoulismoketest.doesitrun`; that auxiliary case is required to pass.
The loaded Minecraft remap is verified by sorted entry-name/content digests,
because ZIP timestamps vary between fresh remaps. Other loaded mod/loader
origins use exact byte hashes. The exact original server inputs are separately
pinned before execution; an inventory made from arbitrary files is insufficient.

`gametest-observations.json`, XML, and lifecycle evidence produce
`deterministic-report.json` and the existing `parity.json` contract. Parity
validation re-imports GameTest evidence rather than trusting a status string.
Both client and visual dimensions remain `not_run`. Keep runtime directories,
logs and worlds private; review any evidence intended for publication.

## Remaining scope

This is a fixed 1.21.1 adapter/importer, not a general discovery engine for all
GameTest suites or Minecraft versions. Recipe, save-state, other colors and
randomized invariants need their own declared tests. Milestone 5 (broader
Survival/backend exploration and the remaining matrix) is later work. See the
[checkpoint](checkpoints/2026-09-27-gametest.md) for exact live evidence.
