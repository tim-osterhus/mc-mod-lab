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
  --minecraft ABSOLUTE_1_21_1_INTERMEDIARY_JAR \
  --aura ABSOLUTE_PINNED_0_2_1_JAR \
  --fabric-loader ABSOLUTE_FABRIC_LOADER_JAR \
  --datafixerupper ABSOLUTE_DFU_JAR \
  --brigadier ABSOLUTE_BRIGADIER_JAR \
  --sponge-mixin ABSOLUTE_SPONGE_MIXIN_JAR \
  --jdk-bin ABSOLUTE_JDK21_BIN \
  --output NEW_ABSOLUTE_DERIVATIVE_JAR \
  --work NEW_ABSOLUTE_WORK_DIRECTORY
```

The public HTTP surface binds to `127.0.0.1`, requires a per-process bearer
token, rejects Origin-bearing requests, and exposes status, screenshot,
a bounded command endpoint, and the fixed `/api/scenario/v2` typed endpoint.
The command endpoint admits world/player/screen reads,
four GUI controls, and control-mode entry/exit with per-command parameter
bounds. It denies `execute_command`, and the rebuilt input handler returns an
error even if that method were invoked internally. Calls/events/debug routes
are not registered. The token is generated at launch, never placed in the
manifest, scenario, or report; the client process receives only a small
allowlist of host environment variables plus its port and token.

The typed endpoint accepts only server-tick, player-inventory, and exact-coordinate
Aura-block reads and four client actions: verified hotbar selection, bounded
single-item drops, fixture-block aiming, and use against the verified current
block crosshair. It rejects unknown capabilities, fields, nested values,
duplicate JSON keys, and bodies over 4096 bytes. An action result reports
input dispatch or rejection, not the requested world transition. The Aura
adapter is only invoked when the Aura mod is loaded; the generic tick and
inventory observers remain independent. `aura_block` snapshots explicitly label
their source as the client block-entity cache, include client world game time,
and do not claim server authority or a known per-block sync tick.
`aura_block_server` instead schedules its read on the integrated server thread,
reports the server tick and world time, and is the only block observer accepted
by exact Aura assertions. Neither observer forces unloaded chunks.
`player_inventory` likewise reads the player identified by UUID on the
integrated server thread and binds its snapshot to the server tick. Client
prediction alone cannot satisfy inventory conservation. Component identity
uses item ID plus a canonical override/removal patch against the pinned registry
defaults. Supported overrides are bounded custom data, damage, max damage, max
stack size, repair cost, and enchantment glint override. Unknown or truncated
component patches withhold exact aggregate digests. Raw custom data is not
returned. The later storage checkpoint below validates one bounded exact
storage/reload fixture, not arbitrary component codecs or storage layouts.

Actions require control mode. Their acknowledgements are not completion checks:
scenarios must wait for normal server ticks and assert the observed transition.
Profiles disable pause-on-lost-focus so headless orchestration does not silently
stop the singleplayer simulation.

The first packaged-client smoke used Aura Cascade Reimagined
`0.2.1+1.21.1` with artifact SHA-256
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
Public derivative SHA-256
`5f8683a62bc211fc3b9b6b70021be9570e797707198d57bcaa043e5e6e71af98`
passed loopback ownership, world/player identity, unauthenticated/Origin
denial, forbidden-command denial, a 1280x720 in-world framebuffer capture,
an `E` key transition to the observed Survival inventory screen, and normal
save/exit. This is a bridge capability smoke, **not** an Aura
gameplay parity pass. The five gameplay proofs still need complete typed
assertions, sealed fixtures, and independent visual checks.

A subsequent packaged run on the same target artifact used public derivative
`26af829b9c6647580da804cedec2a74500bd803e17c37b70d1daa602c8c4d105`.
Actual Survival crystal use charged an empty pump to 1,000 aura; a typed inventory
comparison observed one crystal consumed and the unrelated coal unchanged.
After a real coal drop, the elevated node reached 1,000 aura. The separate
unfueled control remained at zero and correctly failed the positive-transfer
assertion. Both clients saved and exited normally. This is a bounded transfer
capability proof, not atomic network conservation, fuel-consumption accounting,
or completion of the five shared gameplay cases.

The [server-authoritative paired rerun](checkpoints/2026-09-27-typed-gameplay.md)
uses one newer bridge for both cases and supersedes the earlier client-cache
inventory evidence. It records exact evidence locations, tests, and remaining
acceptance gaps.

The later [core and passive inventory checkpoint](checkpoints/2026-09-27-core-and-black-hole.md)
adds a fixed atomic pump-pair observer, fuel/runtime accounting, and matched
blocked/unfueled controls, plus the bounded Black Hole inventory fixture.
The later [storage checkpoint](checkpoints/2026-09-27-storage-reload.md) adds
real deposit, normal same-save reopen and component-exact withdrawal with an
unpowered negative. Pusher and per-render HUD acceptance remain pending.

`python lab.py runtime resume --manifest <reviewed-manifest> --profile <profile> --scenario <scenario>`
reopens only a hash-bound, normally closed successful public run. It consumes
the saved receipt and writes independent evidence under `runs/<id>`. It does
not clone/reseed the world. For the fixed storage observer, the last recorded
state is rechecked before new actions; place that final observation after all
mutations. Input cleanup confirms client-thread key release, not a server
tick transition; use typed server predicates after normal ticks for gameplay.

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
For an offline mapping/source lookup that does not add a second backend, see
[mapping lookup](mapping-lookup.md). The public bridge also has fixed
`screen_slots` and `block_entity_inventory` observers and a bounded general
animation mode, described in [scenario v2](scenario-v2.md). The authenticated
transport, fixed allowlists and exact Minecraft 1.21.1/Aura 0.2.1 artifact
checks still apply. These inspection views are not Survival-player knowledge.

The [render-capture checkpoint](checkpoints/2026-09-27-hud-capture.md) adds
bounded per-render framebuffer evidence and an independent structural validator.
`capture_hud_trace` collects evidence; its successful action/report is not a
visual verdict. Use `hud_trace.validate_capture` with the declared fixture
identity before independent PNG calibration and visual review. Pusher and HUD
acceptance status is recorded in that checkpoint: HUD is now independently
accepted in its fixed scope. The [five-proof first slice](checkpoints/2026-09-27-five-proof-slice.md)
also records independent Pusher equip/removal acceptance and remaining limits.
