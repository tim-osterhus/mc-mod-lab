# Developer inspection and general render capture checkpoint

Date: 2026-09-27. This checkpoint extends the public packaged-client Mod Lab
runtime; it does not change Aura or claim autonomous Survival support.

## Delivered and verified locally

- `screen_slots` reads only a handled client menu cache, capped at 128 slots.
  The real 1.21.1 Fabric inventory returned 46 slot rows, two occupied stacks
  and a hovered index. Its source is explicitly non-authoritative.
- `block_entity_inventory` performs a same-tick integrated-server read of one
  loaded nearby block entity. The real fixture identified the Aura pump at
  `(0,161,0)` and correctly reported `hasInventory: false`. A second disposable
  fixture placed a prefilled vanilla chest at `(2,161,0)`: the server returned
  `hasInventory: true`, 27 slots, and two coal in slot 0 with a complete
  component digest. Normal aim/use opened that chest; the 63-slot client menu
  cache and captured framebuffer showed the matching stack. Closing the menu
  left the server inventory unchanged. This is an inspector/interaction proof,
  not an item-transfer or Aura gameplay assertion. No generic NBT is exported.
- `capture_animation` reuses the reviewed renderer hook with a separate mode,
  bounded sampling and a derived contact sheet. A real 3-second request
  retained 113 render frames and five PNGs; file hashes, decoded pixels and
  dimensions were revalidated from the saved report. The images visibly show
  movement followed by a death screen. A separate independent review of the
  contact sheet confirmed five populated panels, a readable HUD in the first
  two, and a world/particle-to-death-screen transition in the remaining three.
  This proves general capture plumbing, **not** Aura behavior, visual parity,
  or gameplay success. The raw `visual_status` and scenario `visual_check`
  remain `not_reviewed`; the external review is recorded only here.
- Mapping lookup stays offline using the exact pinned 1.21.1 Tiny file. No
  source bundle, second MCP backend, arbitrary command or runtime download was
  added.

The rebuilt local derivative SHA-256 was
`eaf2ad162c3effd5f1e71fcebf44725aa60fc90f469e3f99d03eba53d290d6c2`.
The live profile loaded the unchanged Aura `0.2.1+1.21.1` artifact SHA-256
`2290a1a344fa8e1e43d631729b5f88d422923d573db90d1a592945fecc1aacc8`.
The owned client exited normally; peak sampled working set was 1215.6 MiB.
All eight scenario steps passed, but the scenario's final status was
`inconclusive` because it intentionally had no gameplay requirement.
The portable scenario-report validator accepted the saved report, capture
metadata, every original PNG and the contact-sheet artifact hashes.
The chest run passed all seven observation/action/wait steps and portable
report validation, also ending `inconclusive` because no gameplay assertion
was declared. Its owned client exited normally with exit code 0, peak sampled
working set 1125.6 MiB, and both owned PIDs absent after cleanup. The private
fixture and GUI image remain outside the publication allowlist.

Two additional fresh-client negative controls returned `unsupported` with
normal exit: `screen_slots` with no handled GUI open, and
`block_entity_inventory` at `(1000,161,0)`, beyond the 16-block range. Both
reports passed portable structural validation. Offline controls reject
malformed/oversized menu or block-entity rows, false authority, malformed
boolean/float coordinates or ticks, mismatched server ticks, unknown commands,
frame-index gaps, altered PNGs, overlong
capture requests and same-pixel frames with different PNG metadata when motion
is required. The initial live menu read also failed safely when Gson omitted
empty-slot nulls; the validator now normalizes only those documented nullable
fields. Independent review identified the strict coordinate/tick and decoded
pixel-motion corrections; the reviewer reran their focused tests and the saved
animation validation with no further finding in the inspected code. The
AI-assisted Minecraft Developers source detour adapted one failure-plus-skip
GameTest importer regression and added no runtime dependency or copied source.
No private world, token, image, JAR or runtime profile is shipped.

## Survival boundary

B01 guide-led fresh-world Survival still lacks an isolated adaptive policy
using only pixels and ordinary inputs. These developer probes are withheld
from such an actor. The narrow next tooling milestone is the bounded
visible-input adapter described in the
[integration spec](../specs/2026-09-27-tool-integrations.md#b01-survival-readiness-boundary),
not an open-ended autonomous backend.
