# Minecraft Mod Lab

Minecraft Mod Lab is a thin, local verification toolkit for evidence-backed Minecraft mod development. The alpha supports a disposable save copy, environment doctor, and one bounded before/action/after capture workflow. The [scenario v2 runner](docs/scenario-v2.md) adds strict multi-step contracts, exact prepared-packaged-JAR checks, and an opt-in owned client launcher. It does not install mods, edit a target mod, or decide visual parity.

Start with [setup and rebuild instructions](docs/setup.md), or run the
[portable offline example](docs/evidence.md) before preparing a client.
The [alpha acceptance record](docs/checkpoints/2026-09-22-alpha.md) covers the
independent second vanilla fixture and isolated plugin installation.
The [v2 checkpoint](docs/checkpoints/2026-09-25-v2-runner.md) separates a real
packaged-client bridge smoke from the Aura gameplay proofs still to run.
The [packaged bridge guide](docs/packaged-bridge.md) documents its pinned build
and security boundary.

## Pinned bridge candidate and safety

The candidate is [Minecraft Mod MCP v0.3.0](https://github.com/langyo/minecraft-mod-mcp/releases/tag/v0.3.0), specifically its 1.21.1 Fabric release JAR. The upstream [HTTP server source](https://github.com/langyo/minecraft-mod-mcp/blob/v0.3.0/packages/common/src/main/java/xyz/langyo/minecraft/mcp/common/McpHttpServer.java) binds `0.0.0.0` without authentication. **Do not launch that original JAR for this workflow.** A locally vetted derivative must change both bind sites to `127.0.0.1`, preserve upstream attribution/license, and be reviewed separately. This repo includes a local rebuild recipe, but no upstream or derivative JAR.

The CLI rejects a derivative hash equal to the recorded original hash. Before every request it inspects the Windows listening socket and requires exactly one `127.0.0.1` listener owned by the selected PID. It also requires a per-session `MC_MOD_LAB_TOKEN` environment variable of at least 32 characters, checks that unauthenticated and Origin-bearing requests are rejected, and sends `Authorization: Bearer` only to the selected loopback endpoint. It calls the pinned mod's documented `/api/status`, `/api/cmd`, and `/api/screenshot` endpoints directly, not the stdio bridge's first-port auto-discovery. The stock npm MCP bridge is **not compatible** with this hardened authenticated JAR. Scenarios do not expose `execute_command`; `runtime launch` only starts and closes its own prepared client. A self-reported hash is not authenticity proof; record both release-asset and derivative SHA-256 values during local bridge review.

The first local review supplied original SHA-256 `55aab04b1d7ac9203817e071cb83b6d6cf3da7164636867da33877750de64636`. An initial loopback-only derivative had SHA-256 `ef8139c967e8226d680fb90279be7a3ed796b13e28b0feb68d299cd36b21ea49`, but it is **not accepted** by this CLI because it lacks authentication. Pin the authenticated derivative actually being tested in local identity. ZIP timestamps are not reproducible, so use each artifact's measured hash.

The checked-in [auth patch](patches/minecraft-mod-mcp-v0.3.0-loopback-auth.patch), [framebuffer patch](patches/minecraft-mod-mcp-v0.3.0-framebuffer.patch), [dev-click patch](patches/minecraft-mod-mcp-v0.3.0-dev-click.patch), and [rebuild recipe](scripts/harden-bridge.ps1) cover the alpha derivative. The [packaged builder](scripts/build_packaged_bridge.py) adds pinned intermediary mappings, vanilla framebuffer capture, a command-name/parameter allowlist, and a disabled generic command implementation for Minecraft 1.21.1 Fabric. The earlier dev-instance QA run verified a 1280x720 title screenshot with `lab2.jar` and title-to-disposable-world GUI navigation with `lab3.jar` (SHA-256 `0bda1e57a1d5c68711536f6a9c1b6462628d2a2bc097d609ddd480a1aa948ad0`). The lab3 world/player getters returned placeholder or incorrect fields, so that client remains unsupported. A cropped screenshot fails the declared minimum dimensions; no Aura visual parity pass is claimed.

The alpha runner requires a bridge response containing the actual canonical world save path. The [dev-integration patch](patches/minecraft-mod-mcp-v0.3.0-dev-integration.patch) adds that getter and the verified dev key/command routes. The [dev-player patch](patches/minecraft-mod-mcp-v0.3.0-dev-player.patch) adds the verified lab6 player-name and game-mode getter. This CLI does not expose command execution.

The v0.3.0 `/api/status` `version` field is sourced from `mcp.mod.version`, not a reliable Minecraft game-version field. The client PID, port, socket bind, world name, and canonical world save path are checked live. On Windows the CLI additionally checks the selected Java process arguments for one exact `--gameDir` value, including one local `@argfile` directly referenced by that PID. Missing, changed-after-launch, unreadable, or ambiguous argfiles are unsupported. It also requires the marked fixture under that directory's `saves` and a fresh launch log containing `Loading Minecraft 1.21.1 with Fabric Loader`. A verified local dev bridge revision exposed the actual integrated-server save path; the stock world getter does not. A successful capture is **not** visual or parity approval.

## Commands

Python 3.10+ with the standard library is enough:

```text
python lab.py fixture create --seed PATH_TO_CLOSED_SEED_SAVE --root PATH_TO_DISPOSABLE_ROOT --id guide-baseline --world-name LabFixture
python lab.py doctor --identity identity.json
python lab.py capture --identity identity.json --scenario examples/inventory-scenario.json --out reports/inventory
python lab.py validate scenario-v2 examples/scenario-v2.json
python lab.py runtime prepare --manifest PRIVATE_REVIEWED_MANIFEST --out NEW_ABSOLUTE_PROFILE
python lab.py runtime launch --manifest PRIVATE_REVIEWED_MANIFEST --profile PREPARED_PROFILE --scenario PRIVATE_SCENARIO
python -m unittest discover -s tests -v
```

Live commands use the standard library except v2 schema validation, which
uses the pinned `jsonschema` dependency. Evidence validation and the full test
suite also require `python -m pip install -r requirements.txt` in a local virtual
environment. See [portable replay and evidence validation](docs/evidence.md) for
the offline failing/corrected example, and the [completion ledger](docs/completion.md)
for the finite alpha acceptance list. The [second vanilla fixture](docs/vanilla-fixture.md)
uses the same portable written-book scenario on a fresh disposable save.

`fixture create` makes a uniquely named copy and marker. It never deletes or overwrites an existing save. Choose the new copy in an isolated launcher instance, then fill local `identity.json` from [the example](examples/identity.example.json). The example is a contract, not runnable credentials or a real path. Keep identity files, worlds, logs, and screenshots out of publication unless reviewed. The report records only selected state fields, screenshot hashes/dimensions, and relative artifact names.

Set `MC_MOD_LAB_TOKEN` only in the current process/session environment. Never put it in `identity.json`, command arguments, logs, or committed files. The token is not emitted in reports.

The [scenario](examples/scenario.json) permits one screen `click`, `click_button_index`, `use_item` with empty params, or one key from a small allowlist. A generic proposed in-world check is [open inventory](examples/inventory-scenario.json); change its world name to match the fixture. The runner enters MCP control mode for the action and attempts to restore manual control even on failure. It waits at most two seconds for an expected screen class before the after-capture. Action acknowledgement is not proof that a widget or item activated; assert an after-screen class and inspect the PNG. The report records blank button labels and duplicate widget counts without raw labels. `tracked_pids` is the guarded Minecraft/build-tool group, capped at 3800 MiB for this checkpoint. Optional `informational_pids` can include Codex/ChatGPT app processes; their combined telemetry is reported but never blocks the run. These are point samples, not a cold-build peak guarantee, and this alpha does not promise low-RAM operation. Separate workloads may run concurrently only with isolated profiles, saves, ports, and per-workload memory guards. A missing, too-small, or inconsistent screenshot produces `fail`; an unverified identity or unsafe binding produces `unsupported`. `report.json` and `report.md` are written in either case when the output path is writable. PNGs require independent inspection.

The [pilot checkpoint](docs/checkpoints/2026-09-22-pilot.md) records the first real doctor, vanilla control, and deliberate failure results without local artifacts. The [parity record](examples/parity.json) keeps reference provenance, deterministic tests, client check, and visual check independent. Its example statuses are not verified claims. Document deliberate substitutions and exceptions; asset presence or a green unit-test suite does not imply gameplay parity.

## Parent runtime handshake

1. Produce the local hardened derivative outside this repo from the v0.3.0 1.21.1 Fabric release JAR. It must bind only `127.0.0.1`, require a 32+ character per-session bearer token on every route, and reject Origin headers. Record upstream source tag, original asset SHA-256, patch, derivative SHA-256, and license notice.
2. In a disposable Windows/Fabric client, verify with `Get-NetTCPConnection` that its listener is owned by the expected PID and bound only to `127.0.0.1`. Supply the actual port, PID, process-group PIDs, world name, and fixture path in `identity.json`. Independently verify Minecraft 1.21.1 from launcher/log evidence.
3. Run `doctor`, then a harmless GUI scenario. Inspect both PNGs and state, test a known-failing case and its corrected counterpart, and retain the reports. The pilot checkpoint covers one disposable dev client; each new client still needs its own proof.

## Attribution

Minecraft is by Mojang Studios/Microsoft. [Minecraft Mod MCP](https://github.com/langyo/minecraft-mod-mcp) is an external project by langyo and contributors under its own license. This toolkit does not claim its bridge or endorse an unmodified insecure configuration. Aura Cascade is a potential case study, not part of this repository. Public source release and Codex plugin publication are separate decisions.

The original alpha was validated in a Windows Minecraft 1.21.1 Fabric Mojmap
dev instance. The public-source 1.21.1 intermediary bridge builder has since
passed a separate packaged-release world/player/full-frame smoke with a
denylisted command probe and normal exit. The five Aura gameplay proofs have
not yet passed through Mod Lab. See the v2 checkpoint for exact scope.
