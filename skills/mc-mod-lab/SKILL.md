---
name: mc-mod-lab
description: Prepare disposable Minecraft mod QA fixtures and audit bounded before/action/after evidence without claiming unsupported live capabilities.
---

# Minecraft Mod Lab

Read the repository `README.md` before using the CLI.

1. Record reference provenance and a specific behavioral claim. Keep deterministic tests, client observations, and visual assessment independent.
2. Create a fresh disposable copy with `fixture create`. Never use a valued save or overwrite a prior fixture.
3. Use only a vetted, authenticated, loopback-bound local derivative of Minecraft Mod MCP v0.3.0. Confirm its source patch and actual JAR hash, then run `doctor` against the explicit PID, port, game directory, fresh launch log, fixture, and memory budget. Do not install or launch a stock bridge as part of this skill.
4. Run one `capture` scenario with a declared after-screen class. The CLI takes before/after screenshots and state, enters bridge control mode for one bounded GUI action, and attempts to restore manual control. Inspect both PNGs independently; an action acknowledgment is not proof of correct GUI behavior.
5. Inspect the images and reference contract separately. Keep failed, unreviewed, and unsupported dimensions explicit; do not turn a recorded action into a parity pass.

The upstream Minecraft Mod MCP v0.3.0 JAR binds all interfaces without authentication and is rejected by this toolkit. The packaged source patches are validated for a Windows Minecraft 1.21.1 Fabric dev instance, not a general production-JAR promise. Do not run arbitrary game commands or change the target mod from this skill.
