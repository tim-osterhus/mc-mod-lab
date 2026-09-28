# Typed gameplay capability checkpoint

This checkpoint implements a public packaged bridge and bounded typed runner.
Milestones 1-3 and the five shared acceptance cases remain incomplete.

## Verified runtime

- Minecraft 1.21.1, Aura 0.2.1+1.21.1, source expectations pinned to `44cc057`.
- Target SHA-256: `2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
- Public bridge SHA-256: `c449732d08a05c74c7bf70947ad798e2b06a2e24de17c65f87ae4e371a395fae`.
- Ignored local evidence: `.lab-fixtures/core-pump-fueled-03/` and
  `.lab-fixtures/core-pump-unfueled-03/`, each containing
  `scenario-evidence/report.json`, framebuffer capture, and `lifecycle-report.json`.
- Both runs use the same closed seed and bridge. Setup places empty pump/node,
  raw crystal and coal, and a Survival player. No aura, fuel, power, or transfer
  outcome is injected. Only the fueled case performs the coal selection/drop.
- Actual crystal use: server pump 0 to 1,000; server inventory crystal -1 with
  unrelated coal unchanged. Fueled elevated target 0 to 1,000; unfueled target
  0 to 0, correctly failing the positive-transfer assertion.
- Normal save/exit code 0 for both. Peak private bytes: 1,684.4 / 1,658.2 MiB;
  peak working set: 1,127.6 MiB each. No guard breach or sampling error.
- Both reports validate against the portable v2 report schema. Framebuffer
  inspection confirms a rendered in-world Survival scene, not full HUD parity.

Earlier `fueled-01` / `unfueled-02` runs used different bridge hashes and
client-cache inventory. They are historical capability evidence, not the
authoritative paired inventory proof above.

## Review corrections

- Correct client-thread mapping (`isSameThread`, not `isDemo`).
- Inventory and exact Aura snapshots execute on the integrated server thread,
  with source labels and tick binding. Client predictions cannot satisfy exact
  inventory conservation.
- Item identity uses a supported canonical component patch against pinned
  defaults. Unknown/truncated overrides refuse exact assertions; custom-data
  payloads are digested, not returned. Complex custom-data live probes remain.
- Typed action timeout/transport failure marks the profile uncertain and blocks
  retries and seed cloning. The bridge refuses further typed actions after its
  timeout. This quarantines an in-flight callback that might finish after 504;
  it does not promise cancellation or rollback of an already executing action.
- Generic aura delta is a state assertion, not a causal proof. Gameplay claims
  require reviewed real actions and a paired same-bridge negative control.
- Invalid/non-finite numeric observations refuse assertions. Steps persist
  incrementally; dispatch acknowledgements never substitute for observations.

## Checks and limitations

Python suite: 104 tests, 2 skipped. Focused typed runner: 11 passing tests,
including client-prediction rejection, tick provenance, uncertain-action retry
and seed refusal, malformed acknowledgements, unsupported digests, and retained
negative-control values. Java 21 derivative compilation passed. Timeout tests
simulate HTTP failure; no claim of an induced real-client callback stall test.
Release audit includes all 61 tracked files; package has 50 allowlisted files.

Remaining: atomic network accounting and fuel/runtime/blocked-route assertions;
exact custom-data live controls; Black Hole and Pusher entity/accessory fixtures;
storage deposit/save/reopen/withdraw continuation; per-render HUD instrumentation.
No complete five-case acceptance or full Mod Lab completion is claimed.

Next implementation: fixed same-server-tick pump/target observation and bounded
fuel/entity reads, then the complete core positive/control proof. Continue with
server inventory/entity fixtures and the storage lifecycle. Do not use a moving
Aura source HEAD or copy another task's live world/profile.
