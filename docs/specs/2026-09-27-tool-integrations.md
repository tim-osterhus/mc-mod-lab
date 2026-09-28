# Bounded developer inspection and animation evidence

Status: implementation contract. Target only the reviewed Minecraft 1.21.1
Fabric client and Aura 0.2.1+1.21.1 packaged artifact already pinned by Mod
Lab. This extends scenario v2; it does not change alpha capture, GameTest,
Aura code, or the autonomous Survival spike.

## Decision

The comparison found three useful near-term ideas: richer read-only screen and
block-entity inspection, short general render capture, and mapping/source
lookup for bridge maintenance. The current bridge already derives from
[langyo v0.3.0](https://github.com/langyo/minecraft-mod-mcp/releases/tag/v0.3.0).
[use-ai-for-mc/mcdev-mcp](https://github.com/use-ai-for-mc/mcdev-mcp) and its
[DebugBridge](https://github.com/use-ai-for-mc/debugbridge) are separate
inspection tools; the [CurseForge 1.21.1 DebugBridge](https://www.curseforge.com/minecraft/mc-mods/debugbridge)
is a NeoForge fork, not a Fabric 1.21.1 backend. The independent
[embeddedt/mcdev-mcp](https://github.com/embeddedt/mcdev-mcp) is Java source,
mapping, issue, and primer lookup, not a runtime driver. No code is copied from
these projects. Keep Mod Lab's authenticated, Origin-rejecting, fixed-capability
transport. Do not expose Groovy, raw commands, NBT paths, port discovery, or
runtime downloads.

The inspected upstream checkpoints and near-term dispositions were:

| Project | Source/relationship | Decision and scope |
| --- | --- | --- |
| [langyo/minecraft-mod-mcp](https://github.com/langyo/minecraft-mod-mcp/tree/v0.3.0) | v0.3.0, source commit `50e059d`; Mod Lab already derives its fixed 1.21.1 Fabric bridge from this release (MIT notice retained) | **Adapt, high priority:** add only bounded observers/capture to the existing hardened bridge; no new transport. |
| [use-ai-for-mc/mcdev-mcp](https://github.com/use-ai-for-mc/mcdev-mcp/tree/7b98bdb) | Separate MIT Node source-search server and paired [Fabric DebugBridge](https://github.com/use-ai-for-mc/debugbridge); not the embeddedt repo | **Reference, low priority:** source-search ideas inform offline mapping docs. Do not deploy its arbitrary Groovy bridge, bundle decompiled source, or assume Fabric 1.21.1 runtime support. A safe source index would be a separate medium-sized, licensed project. |
| [embeddedt/mcdev-mcp](https://github.com/embeddedt/mcdev-mcp/tree/f642eba) | Independent OSL-3.0 Java mapping/source/issue/primer lookup; no runtime control, source-path tool does not target Fabric | **Reference, low priority:** document the existing pinned Tiny lookup; copy no OSL code and add no backend. |
| [CurseForge DebugBridge](https://www.curseforge.com/minecraft/mc-mods/debugbridge) | 1.21.1 publication uses the [NeoForge/Forge source fork](https://github.com/pihoue/debugbridge-dev-1.21.1-1.20.1/tree/b959163), not a Fabric 1.21.1 backend | **Defer:** loader mismatch and broad script execution make it unsuitable for this Mod Lab runtime. |

These sources were inspected on 2026-09-27. Integration size is qualitative:
the two fixed observers and recorder extension are a contained bridge/runner
change; a new source-indexing or scripting backend is a separate project, not
a near-term extension. No dependency or license from the reference-only tools
is redistributed.

### AI-assisted Minecraft Developers detour

The [organization inventory](https://github.com/AI-assisted-Minecraft-Developers)
listed six public repositories on 2026-09-27. This is a source and contract
review, not a test of their published binaries. Both substantial projects were
updated that day, but recent commits alone do not establish stable releases or
compatibility with the exact pinned Aura fixture.

| Repository at inspected revision | Actual surface and relation to Mod Lab | Decision |
| --- | --- | --- |
| [WorldDriver `688e43a`](https://github.com/AI-assisted-Minecraft-Developers/worlddriver/commit/688e43ab776b83713807627bfbc3499cadc98685), LGPL-3.0-only | Minecraft 1.21.1 Fabric/NeoForge, Java 21 and Architectury; MCP, WebSocket and Rhino expose client screenshots/GUI, server reads and writes, recipes, and a bot. Its [transport security contract](https://github.com/AI-assisted-Minecraft-Developers/worlddriver/blob/688e43ab776b83713807627bfbc3499cadc98685/docs/guide/transports.md#security) says no authentication, script class filter off by default, and operator commands reachable through the API. Origin checks do not authenticate a socket client. | **Reference, not integrate:** useful proof that richer vision/control is feasible, but a second privileged backend would violate the fixed-capability boundary. Its bot's planning and hidden-state tools are not B01 no-cheat player evidence. Reassess only in a separately isolated, security-reviewed driver experiment; do not copy LGPL source. |
| [StageWright `6b82369`](https://github.com/AI-assisted-Minecraft-Developers/stagewright/commit/6b8236955454b5cf89a043dd594e8761d9f573a1), LGPL-3.0-only | Minecraft 1.21.1 Fabric/NeoForge, Java 21; origin-relative scenes, tick-budgeted awaits, multiple process topologies, JSONL results and [measurement canaries](https://github.com/AI-assisted-Minecraft-Developers/stagewright/blob/6b8236955454b5cf89a043dd594e8761d9f573a1/docs/guide/gates.md#the-failure-modes-that-are-not-a-failing-scene). Its CLI/Gradle flow installs a framework mod and may run Rhino scene files. Mod Lab already has a pinned Fabric GameTest adapter, exact case census, expected-broken control, and skip/crash rejection. | **Adapt one control, no runtime integration:** add an offline regression that a failure followed by a skip cannot erase failure. A full StageWright backend is a medium-to-large independent integration with extra artifact and process trust, not needed for this bounded release. No LGPL code copied. |
| [skills `cacb10c`](https://github.com/AI-assisted-Minecraft-Developers/skills/commit/cacb10c5e586f1afb92a41b9038a8bb3d05c073e) | Four agent skills for dependency updates, mod dependency editing, textures and JDWP; the [README](https://github.com/AI-assisted-Minecraft-Developers/skills) describes optional API credentials, runtime Python dependency install, and a downloaded debugger server. The inspected root shows no license file; reuse rights are uncertain. Last shown update was 2026-09-19. | **Defer/reject for this release:** no skill install or source copy; dependency mutation, image assets and live debugger attachment are outside the pinned evidence runtime. |
| [neoforge_template](https://github.com/AI-assisted-Minecraft-Developers/neoforge_template), [mod-inspiration](https://github.com/AI-assisted-Minecraft-Developers/mod-inspiration), [.github](https://github.com/AI-assisted-Minecraft-Developers/.github) | Respectively an MIT NeoForge template fork, gameplay concept notes, and organization profile/workflow files; organization page showed last updates in May 2026. | **No integration:** none is a Fabric 1.21.1 inspection or evidence capability. |

The StageWright-inspired control is a test of our existing XML contract, not
an import of its parser or a claim of StageWright runtime compatibility. It
preserves the existing principle that a broken measurement is not gameplay
success. All other organization ideas are reference/deferred because this
release already has the useful bounded inspection/capture surface. No
third-party software from this organization was installed or run.

## Capability matrix

| Capability | Authority | Use | Limit |
| --- | --- | --- | --- |
| Existing `screen` / buttons | Client UI | Navigate and verify screen class | No slot or hover detail |
| New `screen_slots` | Client menu cache | Developer inspection of handled-screen slot identities, counts, coordinates and hovered slot | At most 128 slots; coordinates do not prove pixel visibility or exact inventory state |
| Existing `player_inventory`, Aura and entity observers | Integrated server | Exact declared gameplay assertions where component digests are complete | Fixed schemas, loaded world |
| New `block_entity_inventory` | Integrated server | Developer inspection of one loaded nearby block entity and bounded inventory | Within 16 blocks of player; at most 64 slots; no raw NBT or arbitrary field traversal |
| Existing `capture_hud_trace` | Rendered framebuffer plus client metadata | Fixed English White Aura HUD continuity, independent visual review | Existing limits and controls unchanged |
| New `capture_animation` | Rendered framebuffer plus client metadata | General short animation/contact-sheet evidence | 2-10 seconds, sampled rendered frames, at most 64 PNGs/32 MiB, 1920x1080; no automatic visual verdict |
| Existing pinned Tiny mapping builder | Reviewed local source input | Translate known 1.21.1 source names while maintaining bridge | No runtime MCP tool, download, or redistributed Minecraft source |

`screen_slots` and animation metadata are **developer inspection**, not what a
Survival player knows or an authoritative game-state transition. `block_entity_inventory`
is server-authoritative but also a developer inspection capability, not a
player-perception API. Scenario reports must label these sources and retain
`visual_check: not_reviewed` until a separate review. Existing exact gameplay
assertions must not accept client menu state as server inventory proof.

## Contracts and acceptance

1. `screen_slots` returns the current handled screen class, slot count,
   bounded slot rows with index and GUI bounds, item ID/count and an optional
   complete component digest, plus the currently hovered slot index or null.
   It does not return custom names, tooltip text, NBT or arbitrary components.
   Source is `client_menu_cache`; `server_authoritative` is false. A title/no
   handled screen, more than 128 slots, invalid geometry, or an inconsistent
   hover index is unsupported, never a fabricated empty result. Positive:
   open a reviewed inventory with a known item, observe its occupied slot and
   a bounded hovered index; inspect the matching framebuffer and report.
   Deliberately moving hover onto that item remains a separate live control.
   Negative: close the GUI and require
   `unsupported`; mutate an offline observation to a bogus hover or oversized
   slot list and require validation failure.
2. `block_entity_inventory` accepts only `x,y,z`. The bridge schedules one
   integrated-server-thread read, checks the player/dimension, loaded chunk,
   distance <=16, block entity and at most 64 inventory slots. It returns
   dimension, coordinates, block and block-entity registry IDs, same server
   tick, and occupied slots with item ID/count and complete component digest
   when available. Unsupported component patches remain explicitly incomplete;
   they cannot establish exact identity. A non-inventory block entity returns
   an explicit `hasInventory: false`, not invented contents. Positive: inspect
   a prepared nearby container and compare a normal interaction before/after
   on the same world. Negatives: air, unloaded/out-of-range position, oversized
   container, mixed tick, or malformed rows cannot pass. No generic NBT codec.
3. `capture_animation` uses the existing render hook but a separate generic
   trace mode. It records each render sequence/timestamp and retains the first,
   last and sampled PNGs at a declared interval, within the existing 64-PNG,
   32-MiB and 1920x1080 limits. A contact sheet is derived only from retained
   PNGs with bounded dimensions; original PNG hashes remain in the report.
   Captures from a title or in-world screen are valid visual evidence, not
   gameplay proof. Positive: one visible state-changing animation with at
   at least two retained frames with different decoded pixels and independent
   image review; distinct PNG file hashes alone are insufficient.
   Negatives: missing/noncontiguous frame, keyframe mismatch, zero images,
   over-budget or a static sequence fail motion coverage, even if static PNGs
   differ in metadata or encoding. The static control
   may still be a structurally complete capture. Neither structural completion
   nor pixel difference alone grants visual approval.
4. Mapping/source lookup stays outside the runtime. Document how to inspect
   the exact reviewed Tiny mapping and local Minecraft/Aura JARs already
   required by `build_packaged_bridge.py`; keep it read-only and version-pinned.
   A missing or hash-mismatched mapping refuses a bridge rebuild. Do not bundle
   decompiled Minecraft source, install another MCP server, copy OSL-3.0 code,
   or add an auto-download path. This is a documentation/integration decision,
   not a new runtime capability.

The runner must reject unknown names/fields and preserve existing timeout,
uncertain-action quarantine, identity, exact artifact, normal exit, memory
guard and report contracts. Tests include schema rejection, source/tick/size
provenance, positive and deliberate negative controls, artifact validation,
builder compilation, and packaged-client smoke on a fresh disposable fixture.
Publish only after independent review of code and retained images. The full
Survival driver still requires navigation, planning, player-visible sensing
and separate causal trials; these inspection tools do not claim it.

## B01 Survival readiness boundary

This delivery does not make B01 (guide-led fresh-world Survival with no
privileged resources after start) runnable by an autonomous policy. A human
can already perform a bounded real-client dry run in a disposable world using
visible screenshots and ordinary controls, while Mod Lab keeps separate
evidence. The current scripted runner is not an adaptive visible-input policy:
its fixed steps cannot read the guide and choose a new action, camera/mouse
control is incomplete, and several convenient typed actions require hidden
coordinates or item IDs. Do not expose `screen_slots`, block-entity data,
server inventory/Aura observations, render metadata, source/mappings, seed
answers, or fixture coordinates to the B01 actor. Raw screenshots may be shown
to the actor; hashes, typed summaries and server state stay on the evaluator
side. Even a server-authoritative observation is not player knowledge.

The next *bounded* B01 tooling milestone is one isolated real-client policy
adapter: allow only rate-limited framebuffer images and ordinary visible
inputs (bounded mouse look/move/click, hotbar keys, use/attack, forward/crouch,
GUI keys); put it under the existing exclusive control lease, cancellation,
neutral-input release, timeout and memory guard. Run one fresh-world,
no-cheat guide-led task with no supplied materials or hidden answers after
start; keep server observers only for independent outcome scoring and a
paired negative/control trace. Record death, stuck/no-progress and recovery,
not just a final state. Do not add open-ended task planning, an NPC backend,
or broad command execution to this milestone. The separate
[Survival-agent spike](autonomous-playtesting-v2.md#survival-agent-research-spike-separate-milestone)
still evaluates any later task-driver backend independently.
