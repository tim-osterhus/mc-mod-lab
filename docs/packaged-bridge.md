# Public packaged bridge for Fabric 1.21.1

`scripts/build_packaged_bridge.py` builds a source-reviewed derivative of the
pinned Minecraft Mod MCP v0.3.0 Fabric 1.21.1 release. It first runs the
existing authenticated, loopback-only alpha hardening stage, then maps the
reviewed reflection sites to the exact 1.21.1 intermediary namespace and uses
vanilla screenshot capture. The mapping file is SHA-256 pinned. The builder
refuses changed upstream source or preexisting output paths. Neither upstream
nor derivative JARs are bundled with this repository.

```text
python scripts/build_packaged_bridge.py \
  --upstream ABSOLUTE_PINNED_RELEASE_JAR \
  --gson ABSOLUTE_GSON_2_10_1_JAR \
  --mappings ABSOLUTE_REVIEWED_1_21_1_MAPPINGS_TINY \
  --jdk-bin ABSOLUTE_JDK21_BIN \
  --output NEW_ABSOLUTE_DERIVATIVE_JAR \
  --work NEW_ABSOLUTE_WORK_DIRECTORY
```

The public HTTP surface binds to `127.0.0.1`, requires a per-process bearer
token, rejects Origin-bearing requests, and exposes only status, screenshot,
and a bounded command endpoint. The endpoint admits world/player/screen reads,
four GUI controls, and control-mode entry/exit with per-command parameter
bounds. It denies `execute_command`, and the rebuilt input handler returns an
error even if that method were invoked internally. Calls/events/debug routes
are not registered. The token is generated at launch, never placed in the
manifest, scenario, or report; the client process receives only a small
allowlist of host environment variables plus its port and token.

The first packaged-client smoke used Aura Cascade Reimagined
`0.2.1+1.21.1` with artifact SHA-256
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
Public derivative SHA-256
`5f8683a62bc211fc3b9b6b70021be9570e797707198d57bcaa043e5e6e71af98`
passed loopback ownership, world/player identity, unauthenticated/Origin
denial, forbidden-command denial, a 1280x720 in-world framebuffer capture,
an `E` key transition to the observed Survival inventory screen, and normal
save/exit. This is a bridge capability smoke, **not** an Aura
gameplay parity pass. The five gameplay proofs still need typed semantic
actions/observers and independent visual checks.

Use a reviewed local [runtime manifest example](../examples/runtime-profile.example.json)
to prepare a fresh profile. The launcher argument file is executable input:
its hash detects changes, but does not sandbox the classpath or authenticate
every dependency. Review it and every dependency JAR before launching. The
launcher verifies one Fabric KnotClient, a packaged JAR classpath, exact mod
metadata/hash, an isolated save, and one owned loopback listener. No run may
adopt another task's client, world, port, or token. The 3,800 MiB working-set
and private-byte sample guard applies per workload; it is not an OS hard cap.

The builder is pinned to Minecraft 1.21.1 intermediary mappings. Another
Minecraft version requires a separately reviewed mapping/build/test cycle;
simply changing the manifest version is unsupported.
