---
name: mc-mod-lab
description: Prepare disposable Minecraft mod QA fixtures and audit bounded before/action/after evidence without claiming unsupported live capabilities.
---

# Minecraft Mod Lab

From the directory containing this `SKILL.md`, resolve `../..` as the plugin root. Read its
`README.md` and `docs/setup.md`; invoke that root's `lab.py` by absolute path
even when the current working directory is a target mod project. Do not assume
the plugin is installed in the current repository. Use a local Python environment
with the plugin's `requirements.txt` when validating evidence.

1. Record reference provenance and a specific behavioral claim. Keep deterministic tests, client observations, and visual assessment independent.
2. Create a fresh disposable copy with `fixture create`. Never use a valued save or overwrite a prior fixture.
3. Use only a vetted, authenticated, loopback-bound local derivative of Minecraft Mod MCP v0.3.0. Confirm its source patch and actual JAR hash, then run `doctor` against the explicit PID, port, game directory, fresh launch log, fixture, and memory budget. Do not install or launch a stock bridge as part of this skill.
4. Run one `capture` scenario with a declared after-screen class. The CLI takes before/after screenshots and state, enters bridge control mode for one bounded GUI action, and attempts to restore manual control. Inspect both PNGs independently; an action acknowledgment is not proof of correct GUI behavior.
5. Inspect the images and reference contract separately. Keep failed, unreviewed, and unsupported dimensions explicit; do not turn a recorded action into a parity pass.
6. Record the feature contract with the parity schema, dated references/tests,
   client report and independent visual reviewer. Document an approved exception
   instead of silently marking a substitution as parity. Run `lab.py validate`
   for the report and parity manifest; a valid manifest is not a gameplay pass.
7. For a portable introduction, run `lab.py replay --out <new-output-directory>`.
   This tests a failing/corrected synthetic example without Minecraft. It is not
   live evidence. Follow `docs/vanilla-fixture.md` for a second real fixture.

For an independently prepared packaged instance, read `docs/scenario-v2.md`
before using `lab.py scenario run`, or `runtime prepare/launch/resume` for an
owned lifecycle. The pinned public 1.21.1 bridge supports bounded server-thread
inventory/Aura/accessory/entity observers, normal tick waits and real client
actions, including receipt-bound storage reload. Read `docs/packaged-bridge.md`
before rebuilding it. Never treat input dispatch as the observed outcome.
For HUD evidence, use declared-target structural validation and separate
independent PNG/ROI review; capture success is not visual approval.
For developer inspection, `screen_slots` is a client menu cache and
`block_entity_inventory` is a bounded integrated-server read. Neither is
player knowledge. `capture_animation` provides bounded general render PNGs
and a contact sheet, with no automatic visual verdict. Read
`docs/specs/2026-09-27-tool-integrations.md` for negative controls and
`docs/mapping-lookup.md` for the offline pinned source lookup procedure.
A private diagnostic bridge is not a supported public backend.
Unsupported steps must remain unsupported in the report.

For the separate deterministic lane, read `docs/gametest.md`. The fixed
Fabric 1.21.1 GameTest adapter runs only the reviewed packaged Aura conservation
fixture in a fresh headless profile. Use its explicit runtime inventory and
reviewed adapter hash; never download extra mods or reuse a valued server.
Import both the real positive and intended-failure control with
`gametest_import.py`; client and visual checks stay `not_run`. This is not
a substitute for real-player callbacks, screenshots, or Survival playtesting.

Keep source collection portable: public URLs/timestamps or a named local evidence
bundle, never copied private user paths or downloaded videos. Implement one
feature slice in the target mod only when separately authorized, and preserve
the same assertion across its failing and corrected evidence. Fixture reset means
a fresh copy of a closed seed, never deleting the previous save. Use `docs/evidence.md`
for validation commands and separate deterministic, client, and visual statuses.

The upstream Minecraft Mod MCP v0.3.0 JAR binds all interfaces without authentication and is rejected by this toolkit. The packaged builder is pinned to reviewed Minecraft 1.21.1 Fabric intermediary mappings; other versions need separate capability proof. Five bounded Aura harness cases do not establish all-mechanics parity or autonomous Survival. Do not run arbitrary game commands or change the target mod from this skill.
