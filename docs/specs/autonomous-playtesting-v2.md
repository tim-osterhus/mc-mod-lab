# Autonomous playtesting v2: bounded scenario slice

Status: partially implemented; see [scenario-v2.md](../scenario-v2.md) for the
actual supported CLI, and treat milestones 1-3 as incomplete until their live
acceptance evidence exists. Target: Minecraft 1.21.1 Fabric first, with Aura
Cascade Reimagined as the first case study. This document
specifies reusable Mod Lab engineering. The Aura-specific execution plan and
coverage ledger live in the Aura working tree at
`docs/specs/aura-playtesting-v2.md` (publication pending; the public link is
not yet a source of truth).
Neither document claims that an unexecuted mechanic has passed.

## Decision and boundary

Build the next slice around a versioned, bounded **real-client** scenario runner,
not an unrestricted game-playing agent. The agent chooses questions and reviews
failures; the runner performs allowed actions, checks typed observations, and
records what actually happened. Extend the alpha's disposable fixture, identity,
authenticated loopback, and evidence contracts. Keep alpha `capture` and its v1
reports valid; add a separate `scenario run` command and v2 contracts. A
`captured` alpha report remains action evidence, never a gameplay pass.

The first slice must run five proof cases on the exact packaged release JAR:

| Scenario ID | Required real-client check | Known-broken control |
| --- | --- | --- |
| `aura-core-pump-flow` | Player uses a held White crystal directly on the pump, then drops real coal for fuel; inspect pump/target aura, fuel/time and earned transfer over normal ticks. Require correct accounting and an unfueled or blocked negative. Ordinary-node ground absorption is a separate fixture. | A no-fuel/blocked case must not pass the positive transfer assertion. |
| `aura-black-hole-conservation` | Carry the Black Hole in Survival with identified cobblestone and non-cobblestone stacks; observe intended cobble deletion, unchanged unrelated items, and no duplicate output across slots. | A fixture lacking the Black Hole, or with only unrelated items, must not be reported as positive deletion. |
| `aura-fairy-pusher-control` | Bind and equip Pusher; compare a controlled hostile's actual velocity/displacement with the ring physically unequipped, while holding distance and target state constant. | The unequipped lane must fail the equipped-effect predicate. |
| `aura-storage-reload` | Deposit component-distinct items through real player actions, save and close normally, reopen the same disposable save, then retrieve/count exact stacks and power. This extends, rather than erases, earlier bounded storage round trips. | Deliberately mismatched item component/count in an observer fixture must fail. |
| `aura-hud-continuity` | Aim steadily at a powered node during changing aura for at least 10 seconds at normal 20 TPS; collect per-render timestamps/presence and bounded keyframes or video, checking HUD pixels against read-only node values. Natural zero, seeded-zero, look-away, and other-node controls are separate. | Synthetic missing-frame/zero-row fixtures prove the detector can fail; the positive also needs real rendered frames and independent ROI review. |

These are **harness acceptance cases**, not completion of all Aura coverage.
Each positive needs a negative/control, exact artifact hash, fixture provenance,
step evidence, and a non-pass for any missing required observation. Use existing
Aura audit expectations to select exact values before encoding predicates.

## Existing foundation

`lab.py` currently validates a Windows Java `--gameDir`, fresh Fabric 1.21.1
launch log, selected PID/loopback listener, authenticated bridge derivative,
fixture marker, world path, game mode, and sampled process memory. It supports
one of four GUI actions with a before/after screenshot and screen assertion.
`contracts.py` plus `schemas/report.schema.json` and
`schemas/parity.schema.json` validate artifact hashes and keep deterministic,
client, and visual dimensions independent. `docs/completion.md` explicitly
excludes automatic launch, production JARs, multiplayer, and generic command
execution from the completed alpha. GameTest is likewise not implemented in
this repo. None is implicitly available now.

Aura's existing audit ledger and the linked Aura-specific playtesting spec
determine feature expectations. The five cases above are acceptance references
for the generic harness, not a claim of comprehensive mod parity.

## Scenario contract

Add strict `schema_version: 2` JSON, with duplicate-key rejection and
`additionalProperties: false` at every executable object. No templating,
interpolation, shell, arbitrary Minecraft command, Java reflection, Python
expression, free-form NBT field path, or endpoint name supplied by a scenario.
Registry IDs, coordinates within the reserved fixture region, slot indices,
durations, array lengths, and output sizes have explicit bounds. The runner
rejects unknown steps before touching the client. Defaults: at most 64 steps,
10 minutes wall time, 1,200 game ticks per wait, and 64 retained full-size
keyframes per sequence; a versioned policy may lower, not silently raise,
these limits. Per-render ROI metrics or bounded video can cover more frames
without retaining every frame as a full-size PNG.

Future semantic-action shape (illustrative, **not** accepted by the current v2
runner; the runnable supported example is
[examples/scenario-v2.json](../../examples/scenario-v2.json)):

```json
{
  "schema_version": 2,
  "id": "aura-core-pump-flow",
  "fixture": "aura-pump-empty",
  "runtime": {"kind": "packaged-client", "artifact": "aura-candidate"},
  "limits": {"wall_seconds": 600, "max_steps": 64},
  "setup": {"profile": "prepared-pump-circuit", "disclosure": "pump, target node, geometry and raw inputs supplied; no aura, fuel or transfer seeded"},
  "steps": [
    {"id": "before", "observe": ["aura:pump", "aura:node:target", "player:inventory", "ground_items"]},
    {"id": "aim-pump", "action": {"type": "aim_at_block", "marker": "pump"}},
    {"id": "select-crystal", "action": {"type": "select_hotbar", "slot": 0, "item": "aura:aura_crystal_white"}},
    {"id": "use-crystal", "action": {"type": "use_item_at_block", "marker": "pump"}},
    {"id": "charge", "wait": {"type": "predicate", "max_ticks": 80}, "require": {"type": "pump_crystal_acceptance", "item": "aura:aura_crystal_white", "pump": "pump"}},
    {"id": "select-fuel", "action": {"type": "select_hotbar", "slot": 1, "item": "minecraft:coal"}},
    {"id": "drop-fuel", "action": {"type": "drop_selected", "count": 1}},
    {"id": "fuel", "wait": {"type": "predicate", "max_ticks": 80}, "require": {"type": "pump_fuel_acceptance", "item": "minecraft:coal", "pump": "pump"}},
    {"id": "flow", "wait": {"type": "ticks", "count": 80}, "require": {"type": "numeric_delta", "path": "aura:node:target.white", "gt": 0}},
    {"id": "after", "observe": ["aura:pump", "aura:node:target", "screen", "frame"]}
  ],
  "cleanup": "save-exit"
}
```

The symbolic `path`, marker, `ground_absorption`, and
`pump_fuel_acceptance` above resolve through registered, typed fixture/Aura
observers; they are not arbitrary object traversals or NBT queries.
`pump_crystal_acceptance` requires the held crystal to be used on the targeted
pump and pump aura to increase, not just a use acknowledgement. The separate
ordinary-node ground-absorption fixture requires a dropped crystal entity to
disappear through normal interaction and node aura to increase. White aura can
flow horizontally when a gradient exists; an equal-pair control does not show
that behavior. Direct use keeps the core pump fixture smaller and has been
verified independently. Fuel acceptance requires the coal entity to be consumed
and pump fuel/time to increase; later target gain comes from normal ticks.
The fixture declares exact pump/drop-marker positions so aim is verified.
Fixture profiles and observers are maintained
code/data reviewed with the target mod adapter, not inline privileged
instructions. A real schema example should use stable IDs/coordinates from
its disposable fixture and declare every required capability. A fixture may
provide terrain, raw materials, or initial power if disclosed. It must not
inject the action's expected result (transfer, output, inventory delta, HUD
pixels, or fairy effect). `natural-acquisition` mode forbids privileged setup
after world start; it is **not** used by these five proof cases.

### Execution semantics

- Steps are serial, numbered, and checkpointed. One control owner holds a
  renewable action lease; no concurrent agent, reflex module, or helper may
  steer the same player. On handoff, release held keys/buttons, await a neutral
  input state, then acknowledge the new owner. Reflex is off by default in
  controlled tests.
- Semantic actions initially cover select verified hotbar item, aim at a
  verified block/entity, bounded move to a fixture marker, attack, use, drop, interact, open/close
  screen, and validated slot click. The bridge must return action acknowledgement
  **and** the requested state transition must be observed; acknowledgement alone
  never passes. Each capability is independently probed, versioned, and
  unsupported if absent. Keep the existing security checks on every request.
- Read-only observations initially cover player position/mode/health/effects,
  inventory registry IDs/counts/components needed by the assertion, target,
  screen class/slots, bounded nearby entities/block states, and full-frame
  screenshots. Aura-specific power/receipt/progress readouts are separate
  observer capabilities. Observers may expose privileged internal telemetry
  only to the harness, never to a novice-agent view.
- `wait.ticks` uses server game-time change, not sleep duration. `wait.event`
  requires a named, timestamped, read-only event stream with monotonic sequence;
  if unavailable, report `unsupported` or use an explicitly declared bounded
  polling predicate. Timeout, lost input, unchanged game time, wrong world,
  stale target, disconnect, budget exceedance, and missing response terminate
  the step. Never treat an absent observation as false or as a pass.
- Cancellation is checked between actions and during waits. A watchdog releases
  held input, exits control mode, records the last known step, and attempts a
  normal save/exit only when instance identity is still verified. Timeout or
  failed cleanup remains visible; never delete a save or kill an unknown PID.
  No-progress checks use expected positional/state delta over bounded ticks,
  not a blind wall-clock timer.
- Setup, action, and observer use separate capabilities and logs. The report
  records fixture material/power provenance, every privileged setup call,
  player action, observer read, control handoff, and cleanup outcome. A QA
  adapter can use privileged setup in the sealed fixture phase only, not while
  accepting ordinary-operation behavior.

## Runtime, memory, and evidence

Add an opt-in packaged-client lifecycle runner for an allowlisted local
Minecraft/Fabric/JDK/mod profile. Before launch, hash the exact release JAR,
loader, API, guide dependency, bridge derivative, and fixture seed; compare
them to a reviewed manifest. Copy a **closed** seed to a fresh marked save;
never launch against the source save. Verify the process, log, world path,
loaded mod list/hash, socket, and authentication before taking control. Save
and close normally; reopen by explicit lifecycle step for persistence tests.
Do not overwrite an occupied mods folder or adopt an unrelated process. A
packaged runtime that cannot prove artifact identity is `unsupported`.

Independent isolated sessions may run concurrently. Each Mod Lab workload
uses its own profile, disposable save, ports, token, and process group; it must
never attach to another task's game. The budget is 4.5 GB per
Minecraft/build/helper workload (Codex desktop excluded). Retain the alpha's
3,800 MiB working-set guard per workload by default, and sample both working
set and private bytes for its launched descendants. These are separate
measures, not quantities to sum. Record sample interval, peak, and process
set. Sampling is not an OS-enforced RAM cap and cannot rule out unseen peaks;
report that limitation. On guard breach, cancel, attempt graceful cleanup,
and mark the safety check `fail`. Two-client cases need a fresh aggregate
measurement of their own workload, not an inherited single-client claim.

Introduce `schemas/scenario-v2.schema.json` and
`schemas/scenario-report-v2.schema.json` without rewriting v1 reports. Per-step
status is `pass`, `fail`, `inconclusive`, `unsupported`, or `not_run`:

- `pass`: required observation, transition, assertion, and artifacts agree.
- `fail`: supported execution contradicts a declared assertion or a safety
  invariant; a real defect and a broken test fixture are distinguished in
  `cause`, not guessed away.
- `inconclusive`: execution occurred but evidence cannot distinguish outcomes
  (e.g., random event did not occur within trial budget, occluded/undersampled
  rendering, or interrupted comparison).
- `unsupported`: required backend/capability/identity unavailable or unsafe.
- `not_run`: never attempted, including steps skipped after an earlier stop.

An overall `pass` requires all required steps pass and cleanup be verified.
Optional observations cannot fill missing required fields. Report scenario
schema/hash, artifact/JAR hash, runtime profile, fixture provenance, exact
action/observer versions, step timestamps/game ticks, assertion values with
units, failures, cancellation, memory, logs, screenshots/frame series, and
artifact SHA-256. Keep private raw traces separate; portable reports contain
relative paths and no token, local world path, or sensitive inventory text.
Visual review remains independent and named; numeric image similarity is a
triage signal, not automatic UI approval. HUD assertions use a stable cropped
region plus temporal presence/content, not whole-screen similarity. The HUD
case requires per-render timestamp, frame sequence, target identity, game tick,
and pixel-derived ROI presence/content for at least 10 seconds of normal
20-TPS operation, with bounded full-frame keyframes or an actual bounded video.
Independently review ROI pixels at every flagged disappearance/transition and
selected ordinary frames. The observer must separately identify a naturally
reached zero during a powered cycle and a deliberately seeded zero control;
one cannot stand in for the other. If a natural crossing is not observed within
the declared bounded extension, report that subcheck `inconclusive`. Missing
render frames, nonmonotonic timestamps, or unvalidated ROI telemetry also make
single-frame continuity `inconclusive`, even when sparse keyframes look fine.
A synthetic negative tests the detector, not the actual runtime visual.
Baseline updates require explicit review and cannot be generated from the
candidate under test.

## GameTest route

Provide a **Fabric 1.21.1** adapter interface that imports structured
GameTest results into the same evidence ledger, not a NeoForge-specific runner
and not a substitute for client UI tests. First target aura transfer,
conservation, obstruction, recipe consumption, and save-state invariants.
Run the actual mod code in-world with known structures and bounded ticks;
identify any test hooks or initial-state injection in the report. Keep
deterministic GameTest, real-client interaction, and independent visual review
as separate dimensions. [Fabric's 1.21.1 testing guide](https://docs.fabricmc.net/1.21.1/develop/automatic-testing)
documents the platform route. A headless launcher may run deterministic tests,
but headless execution without rendering cannot accept screenshots or HUD.

## Aura coverage boundary

The 16 targeted mechanics and 11 broader suite obligations, including their
controls and prior-evidence distinctions, are specified only in
`aura-cascade-unofficial-port/docs/specs/aura-playtesting-v2.md` in the sibling
working tree (publication pending).
Mod Lab provides the runner, typed evidence, and capability labels; it does not
silently mark a mod-specific obligation complete. Random outcomes require
predeclared trials and uncertainty, not a pass inferred from a short quiet run.

## Survival-agent research spike (separate milestone)

The proposed hybrid architecture is useful: a goal planner chooses what to
investigate; deterministic tasks handle routine navigation, gathering,
crafting, eating, and survival reflexes; direct embodied controls handle new
mod interactions. But a task engine is **not** automatically an equivalent
player. Maintain a real Fabric client as the baseline and label server-side
NPC-only evidence separately. The first spike must test a fixed vanilla goal
(gather wood, craft a tool, obtain food, navigate to a marked site) under the
same world seed/time budget with a real-client task driver and an optional NPC
backend. Record task completion, invalid actions, deaths, stuck/no-progress,
recovery, CPU/RAM, and failure traces. Then attempt one Aura guide-led action
through direct real-client control. Output an accept/reject/defer decision for
each backend, **not** a promise of full autonomous Survival progression.

Use a small typed driver contract, not a free-form executable command:

```text
submit_task(goal: {kind, target_id?, count?, marker?},
            limits: {wall_seconds, game_ticks, retries},
            policy: {allow_combat, allow_block_break, reflex}) -> task_id
status(task_id) -> {state, progress, public_observations, failure_code}
cancel(task_id) -> {acknowledged, input_released, terminal_state}
```

Initially allow only `gather_item`, `craft_item`, `obtain_food`, and
`navigate_to_fixture_marker`. Validate registry IDs, counts and world bounds
before dispatch; `status` is read-only and never leaks privileged harness
telemetry to a novice policy. `progress` includes last action/game tick and a
bounded no-progress reason; terminal states include succeeded, failed,
cancelled, timed_out and unsupported. The driver must acquire the same action
lease as direct controls. Task-to-direct/reflex handoff cancels the prior task,
releases held input, observes a neutral state, then grants the next owner.
Timeout, dropped input, lost task ID, and failed cancellation cannot silently
continue. Reflex is disabled in the paired controlled benchmark.

Run five paired fresh-world trials per candidate backend across five declared
seeds, with identical goals, limits and starting inventories in each pair.
This is a capability smoke, **not** a statistical estimate of human usability.
`accept` means at least four of five vanilla goals complete within budget, all
five runs terminate/clean up safely, no permission or knowledge-boundary
violation occurs, aggregate memory stays under the declared guard, and a
real-client driver completes the one Aura guide-led action through real input.
`defer` means capability/identity is unsupported or the bounded evidence is
insufficient; `reject` means unsafe/unbounded behavior, failed cancellation,
or repeatable task failure under supported conditions. Record individual
outcomes and failures rather than only the threshold. An NPC backend meeting
its vanilla threshold is accepted **only as an NPC task accelerator** until
paired semantic-equivalence probes compare real-player versus NPC item use,
accessory equip/callbacks, crafting transactions, Survival/Adventure
permission gates, inventory conservation, and client/server sync. Any mismatch
keeps that mechanic real-client-only. No NPC trial can pass GUI/rendering or
player-only mod acceptance on its own.

Candidate assessment as of this spec:

- [PlayerEngine](https://github.com/Goodbird-git/PlayerEngine) is a
  server-side framework for custom `LivingEntity` NPCs, not a `PlayerEntity` or
  a real-client replacement. Its [Fabric 1.21.1 artifact](https://modrinth.com/mod/playerengine/version/msqQbeg3)
  exists, but runtime compatibility with Aura, player-only hooks, networking,
  screens, permissions and performance is untested. Its repo is LGPL-3.0;
  dependency/distribution review precedes integration.
- [AI Companion](https://github.com/adevivo/ai-companion) targets Fabric
  1.20.1 and bundles a PlayerEngine fork, so it is not a 1.21.1 drop-in.
  Audit every included component's actual license before copying glue code.
- [AIRI's Minecraft integration](https://airi.moeru.ai/docs/en/docs/integrations/minecraft)
  is Mineflayer-based local-development infrastructure with a planned Fabric
  migration. Borrow its perception/planner/reflex/task separation, not a
  long-term dependency on its present bridge.
- AltoClef/Automatone/Baritone and Mineflayer remain optional, pinned
  candidates, not core requirements. Check active fork, loader/version,
  licensing, protocol/mod registry behavior and a live Aura smoke before any
  supported label. An NPC or protocol bot result cannot establish client GUI,
  accessory callbacks, rendering, or genuine two-real-client behavior.

For a novice persona, a fresh prompt is insufficient. Run the player policy in
a separate process with explicit tool/filesystem/network permissions exposing
only player-visible screens, tooltips, guide, recipes, inventory, chat and
ordinary world state. No source files, internal recipe registry, hidden NBT,
test answer, or privileged observer channel. Harness telemetry stays behind a
one-way evidence boundary. Record any known prior model knowledge as residual
bias; do not call this equivalent to a genuinely new human player. The
task/reflex/direct drivers must share the same action lease and cancellation,
no-progress, dropped-input, and survival emergency policy. Reflex remains
disabled for controlled mechanics tests and is an explicit opt-in for
exploratory Survival.

## Delivery sequence and acceptance

Steps 1-3 define the **next slice**. Steps 4-5 are follow-on milestones and do
not postpone the first slice's bounded release once its own gate passes.

1. Contract and safety: v2 schema/validator, capability negotiation, action
   lease, bounded waits, cancellation/cleanup, typed missing-observation
   behavior. Offline tests reject unknown commands, fake success, missing
   observations, stale world/PID, and unsafe fixture paths.
2. Runtime: packaged-client artifact/loaded-mod proof, disposable launch and
   normal save/reopen, aggregate per-workload memory sampling and isolated
   profile/port ownership. Independent isolated workloads may run concurrently.
   Validate on an exact release candidate; keep dev-client results separate.
3. Five proof scenarios: implement Aura fixture/observer adapters and the
   five table rows, each with a deliberately broken control and positive
   rerun on a fresh fixture. Independent screenshot review for HUD and any
   UI-sensitive claim. All reports validate hashes/portable paths.
4. Deterministic lane: Fabric GameTest importer and at least one conserved
   transfer test, linked without collapsing the real-client/visual statuses.
5. Later: remaining T/B matrix, two-real-client cases, random/statistical
   trials, visual baselines, profiling, and the survival-agent backend spike.

The release gate for the **tooling slice** is all five exact-artifact positives
and their known-broken controls passing, clean normal teardown, no unreviewed
visual promotion, contract/unit/CI checks green, and a linked Aura coverage
report showing deferred mechanics as `not_run` or `unsupported`, never
implicitly green. This does **not** gate Aura releases on every suite until
separately adopted by that project's maintainer. Missing observation, fixture
cheating, incorrect JAR, exceeded budget, or failed cleanup blocks a pass.

## Implementation touchpoints and non-goals

Expected files: keep `lab.py` v1 CLI stable; add a small scenario-runner module,
typed bridge action/observation adapter, guarded packaged-launch module, v2
schemas and report validator in `contracts.py`, fixture profiles/examples,
focused tests, and user-facing setup/evidence docs. Update
`package-files.json`, `scripts/check_release.py`, plugin skill/docs, and CI
when new distributable modules/schemas/examples are actually added; the
current alpha allowlist does not automatically package them. Avoid a general
plugin API until the concrete Fabric and Aura adapters need one.

No unrestricted shell or in-game command execution, no auto-download of
third-party mods, no destructive world reset, no public secret/runtime traces,
no automatic publication, no claim of all-mechanics or full legacy parity,
and no claim that a successful statistical/visual heuristic proves usability.
Headless automation, Baritone/PlayerEngine, Mineflayer, spark, multiplayer and
autonomous fuzzing are optional later work after measured, licensed capability
proofs. Human judgement still owns whether progression is clear and fun.
