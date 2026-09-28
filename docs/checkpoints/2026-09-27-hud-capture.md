# Bounded HUD capture checkpoint

## Accepted bounded HUD update

The independent review now accepts HUD as the fourth of five shared proofs.
Pusher remains pending. This update supersedes the earlier pending status below.
The RGB-sensitive reruns use bridge SHA-256
`cea41110320b5ac5927b82ea5eff924a1e420796f94136ab68a1348eb3e8ed86`.
They retain adjacent frames whenever the value-ROI RGB SHA changes, not the
whole panel. The earlier numeric-only retention left three unexplained rendered
ROI states; those are evidence gaps, not product defects or known occlusion.

- `.lab-fixtures/hud-dynamic-03/scenario-evidence/hud-changing/trace.json`:
  508 frames, 18.877 seconds, 18 numeric changes, 38 PNGs.
- `.lab-fixtures/hud-cross-zero-03/scenario-evidence/hud-crossing/trace.json`:
  510 frames, 18.648 seconds, 10 numeric changes, 33 PNGs.
- `.lab-fixtures/hud-other-node-02/scenario-evidence/hud-other-node/trace.json`:
  496 frames, 17.731 seconds, 19 PNGs, all value candidates zero after switching
  from a charged pump to the separate empty ordinary node at (0,164,0).

All 1,018 positive/crossing numeric ROI records map to retained, independently
reviewed exact pixel patterns. Parent Pillow checks all 71 final positive PNGs,
and both ROIs per PNG, against recorded hashes/counts. Astra-low independently
reviewed all 30 numeric/RGB transition pairs through lossless crop sheets plus
raw full-frame context, including first/last frames. The visible dropped coal
in crossing-03 frame 2392 changes background pixels but leaves the 1000 glyphs
intact. This does not establish the cause of unretained earlier frames.

Seeded-zero, look-away and other-node controls also received independent visual
review. Their older capture bridges are disclosed: static/seeded-zero/look-away
used `b6e639567750155f294d6e2b77430ef32c496f6b68ebccd7ae644f24a3df25da`,
and other-node used `621eba6da28edd5b88ae1c6656cb6923f2fd53e1d0e5be68bc9f3b2a91a67bb1`.
These controls validate absence/reset, not one interchangeable global baseline.
Final positives and controls all closed normally, code 0; no owned JVM remains
from these captures. Peak private memory of the two final positives was
1,702.0 and 1,635.5 MiB; other-node was 1,664.0 MiB.

Independent review is recorded in the sibling Aura audit
`docs/audits/2026-09-27-hud-visual-review.md`. The accepted scope is fixed English
ordinary White HUD, GUI scale 2 numeric ROI and rendered buffer continuity.
Static calibration additionally inspected scale 3, but that is not a scale-3
changing-continuity claim. No automatic baseline approval, general OCR,
full-screen correctness or monitor-presentation claim is made.

## Earlier capture checkpoint

Three of five shared gameplay proofs remain accepted: core pump, passive Black
Hole and component-exact storage reload. This checkpoint adds real rendered
evidence, not a fourth or fifth gameplay acceptance claim. Pusher integration
and independent changing-HUD visual acceptance are still pending.

## Runtime and scope

All live evidence uses the preserved Aura 0.2.1+1.21.1 artifact SHA-256
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`
and source expectations pinned to `44cc057`. The final transition reruns share
bridge SHA-256
`621eba6da28edd5b88ae1c6656cb6923f2fd53e1d0e5be68bc9f3b2a91a67bb1`.

The required GameRenderer HEAD/RETURN mixin records a contiguous global render
sequence. Vanilla framebuffer capture supplies physical top-left RGB ROIs and
bounded PNG keyframes. It retains first/last, periodic frames, and adjacent
before/after frames for target, visibility, candidate-presence and client White
aura-value changes. Metadata is client state, never server truth or numeric
pixel recognition. The fixed English White-value ROI is validated only for the
ordinary node/pump layout, not capacitors, multiple colors or resource packs.

Limits are 1,200 frames, 30 seconds, 64 PNGs, 32 MiB retained PNG bytes and a
1920x1080 framebuffer. Bounds, missing frames, incomplete final renders or
capture exceptions are explicit incomplete evidence. Automatic limit stops
cannot pass the strict validator. The helper observes rendered buffers, not
physical monitor presentation. Public transport remains authenticated,
loopback-only and fixed-capability; no command execution is added.

## Fresh transition evidence

Local ignored captures (not shipped with the plugin):

- `.lab-fixtures/hud-dynamic-02/scenario-evidence/hud-changing/trace.json`:
  490 contiguous frames, 17.940 seconds, 16 numeric changes with all 16 adjacent
  PNG pairs, 36 keyframes. Twelve real crystal uses charge the pump before
  capture; a real coal drop starts natural flow after recording starts.
- `.lab-fixtures/hud-cross-zero-02/scenario-evidence/hud-crossing/trace.json`:
  525 contiguous frames, 19.014 seconds, 10 numeric changes with all 10 pairs,
  31 keyframes. One real crystal use supplies 1,000 aura before a real fuel drop.
  Natural 100-to-zero transition is retained at sequences 2391/2392.

Both clients saved and exited normally, code 0. Sampled private peaks were
1,635.0 and 1,674.1 MiB, below the per-workload 3,800 MiB guard. This is a
sampled guard, not an OS-enforced hard cap. Authoritative before/after samples
bracket the capture start/stop acknowledgements. Python and Java clock origins
remain separate. Structural replay binds the declared Overworld pump at
(0,161,0); the block observer lacks a dimension field, so this is a fixed
Overworld fixture assumption, not a multidimension proof.

Independent Pillow decoding checked all 67 final PNGs, both physical ROIs per
image, recorded RGB SHA-256 and white-candidate counts. These checks establish
pixel-metric integrity and orientation/scaling, not visual correctness.
Independent visual review of the final changing/zero transition pairs is pending.

Earlier static, seeded-zero, look-away and late-zero controls remain local
under `.lab-fixtures/hud-smoke-02`, `hud-seeded-zero-01`, `hud-look-away-01`
and `hud-dynamic-01`. Initial changing/crossing runs retained no complete
adjacent numeric-transition pairs. They are incomplete transition evidence,
not product failures. The fresh `02` runs supersede that retention limitation.
The first HUD bridge launch also failed due to an overly broad mixin package;
the dedicated `common.hudmixin` package fixes it. The failed launch is retained.

## Using the validator

The scenario `capture_hud_trace` action accepts a duration of 10..20 seconds,
the source block coordinates and optional `trigger: drop_selected`. It records
normal-tick capture, authoritative bracketing samples and bounded PNG downloads.
Collection success alone does not run or replace acceptance review.

```python
import json
from pathlib import Path
from hud_trace import validate_capture

capture = json.loads(Path("reviewed-trace.json").read_text())
coverage = validate_capture(
    capture,
    expected_target={"dimension": "minecraft:overworld", "x": 0, "y": 161,
                     "z": 0, "blockId": "aura:aura_node_pump"},
    require_value_transitions=True,
)
assert coverage["capture_status"] == "complete"
assert coverage["visual_status"] == "unreviewed"
```

Control modes are `seeded_zero`, `lookaway` and `other_node`; the latter two
require the declared positive target. The validator verifies sequence,
timing/freshness, dimensions/ROI geometry, target identity and bounded server
tick-rate intervals. It does not decode PNGs or infer text from metadata.
Missing transition keyframes refuse explicit transition coverage. Separate
pixel-integrity and independent visual review are still required.

## Preparatory Pusher work

The bounded input allowlist now admits B and fresh profiles use GUI scale 2.
The stationary-entity impulse assertion compares identical server-observed
target/player positions, UUID, health, dimension and outward velocity against
a zero initial velocity. It is not displacement or a removal-decay proof.
`AuraAccessoryObservers.java` is a Java-21-compiled, read-only four-slot/cursor
helper with complete component-digest gates. Its endpoint/runner integration
is not enabled in this bridge checkpoint. No accessory setter was added.

The full Python suite passes 165 tests with two host symlink-permission skips.
The final packaged bridge compiles with Java 21 and was exercised in both fresh
transition clients. Offline tests do not substitute for gameplay evidence.

Next: independently review the final HUD transition images and controls,
wire accessory observation, then run actual B-screen equip and matched Pusher
negative controls. The five-case slice is not complete.
