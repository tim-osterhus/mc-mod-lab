# Second fixture: vanilla written book

This procedure tests the same vanilla interaction in any supported Mojmap dev
client. It makes no Aura API, item, guide, or world-name assumptions. Record all
installed mods in the local evidence: running this in an Aura-containing client
does not establish a client with no other mods installed.

## Prepare and reset

1. Coordinate the runtime slot. Close the seed world cleanly before copying it.
2. Create a new marked copy using the command below. Never point identity at the
   seed. Reset means making another new copy from the closed seed with the same
   command; keep the previous copy and evidence intact.
3. Select that exact copy in the isolated client. Populate a local identity from
   `examples/identity.example.json`: actual new save path, internal world name,
   game directory, log, PID, port, fixture id `vanilla-book`, bridge hash, and mode.
4. Record the Minecraft/Fabric/JDK versions and installed mod versions. Use the
   parent's already validated binary. Keep absolute paths and credentials local.

```powershell
python lab.py fixture create --seed $ClosedSeed --root $DisposableSaves --id vanilla-book --world-name $InternalWorldName
python lab.py doctor --identity $Identity
```

The operator supplies these variables from the selected instance. They are not
environment-variable secrets or repo defaults. Set the bridge session token only
in the calling process environment, using the same session as the running client.

## Same assertion, failing and corrected inputs

1. In the fresh marked copy, select an empty hand, aim away from interactable
   blocks, and close all screens. Run the baseline capture below. Expect status
   `fail`, no after-screen, and a screen-class mismatch. Inspect both images.
2. Prepare a vanilla `minecraft:written_book` with a readable page titled
   `Control`, using the operator's manual setup or authorized setup commands.
   Select it in the same hand, aim away from interactable blocks, close screens,
   and run the corrected capture with the exact same scenario. Expect `captured`
   and `BookViewScreen`; independently inspect both images and the readable page.
3. Verify control-mode exit is acknowledged in both reports. Preserve both runs.
   Save and close the client before making any further seed copy.

```powershell
python lab.py capture --identity $Identity --scenario examples/vanilla-book/scenario.json --out reports/vanilla-baseline
python lab.py capture --identity $Identity --scenario examples/vanilla-book/scenario.json --out reports/vanilla-corrected
```

Use fresh output directories. A passing corrected capture means the bounded
screen assertion succeeded, not that the entire mod or its visual parity passed.
The current live CLI uses exit 0 for captured and 2 for failure/unsupported;
inspect the JSON status to distinguish them. Historical pilot wrapper exit codes
in the checkpoint note are operator observations, not this CLI's exit contract.

Return a sanitized summary: toolkit commit, bridge hash, installed-mod list,
fresh-copy/marker and identity checks, both statuses and actual screen classes,
image dimensions and independent visual outcome, control-mode exit, scoped
memory measurements with sampling caveats, and clean client exit. Do not publish
the raw local identity, player name, token, save, or unreviewed reports.
