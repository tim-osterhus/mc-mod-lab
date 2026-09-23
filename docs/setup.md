# Setup and supported workflow

## Scope and prerequisites

Live capture supports Windows, Minecraft 1.21.1, Fabric, and a Mojmap development
runtime. Have an existing working Fabric development client, Java 21, Git,
PowerShell, and Python 3.10+ available. The client may contain other mods; record
their versions. This toolkit does not create a development project, remap a
production JAR automatically, download Minecraft, manage accounts, or launch it.
Production intermediary mappings have not been validated. Report an unsupported
profile instead of weakening identity checks to make it pass.

Clone this repository, then create a repo-local Python environment:

```powershell
git clone https://github.com/tim-osterhus/mc-mod-lab.git
cd mc-mod-lab
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python lab.py replay --out reports/first-replay
.venv/Scripts/python lab.py validate parity reports/first-replay/parity.json --portable
```

Use that interpreter consistently: Windows `py` may honor a script shebang and
select a different Python installation than `py -c`. `doctor` and `capture` use
the standard library, while schema validation requires the pinned dependency.

## Harden the pinned bridge

1. Obtain `minecraft-mcp-1.21.1-fabric-v0.3.0.jar` from the upstream
   [v0.3.0 release](https://github.com/langyo/minecraft-mod-mcp/releases/tag/v0.3.0).
   Verify SHA-256 `55aab04b1d7ac9203817e071cb83b6d6cf3da7164636867da33877750de64636`.
   Never launch the original asset for this workflow.
2. Review `patches/PROVENANCE.md` and all five patches. They modify only three
   upstream classes: loopback/authentication, framebuffer capture, dev input,
   world identity, and player identity. Review the upstream license notices.
3. Supply a local Gson 2.10.1 JAR and a JDK whose `javac` supports `--release 8`.
   Choose new work and output paths outside any target mod's source tree. Run:

```powershell
./scripts/harden-bridge.ps1 -UpstreamJar $OriginalJar -GsonJar $GsonJar -JdkBin $JdkBin -WorkDirectory $NewBuildDirectory -OutputJar $NewHardenedJar
Get-FileHash -Algorithm SHA256 -LiteralPath $NewHardenedJar
```

The script downloads three sources from one pinned upstream commit and verifies
their hashes, applies the patches, compiles only those classes, and updates a copy
of the original release. It refuses overwrites. It does not launch Minecraft or
Gradle. This is a repeatable source transformation, not a byte-reproducible JAR:
compiler/ZIP metadata can change the derivative hash. Pin the actual output hash
in local identity. Use the existing development project's supported remapping
process to load the derivative into its Mojmap runtime. The user/operator must
verify that exact runtime artifact and mapping profile; source compilation alone
does not establish compatibility.

Generate a new token of at least 32 random characters in the launcher's process
environment under `MC_MOD_LAB_TOKEN`. Give the same value only to the test-shell
environment. Never put it in command arguments, the identity file, reports, or
Git. The derivative rejects missing/short tokens, non-bearer requests, and Origin
headers. Stock npm MCP transport cannot authenticate to this derivative.

## Live handshake and reset

Coordinate one runtime slot for build/client workloads. Prepare a closed seed,
then follow `docs/vanilla-fixture.md` to create a new disposable copy. Copy the
identity template to ignored `identity.json`; replace every placeholder and
record the actual selected Java PID, port, mode, internal world name, canonical
save path, game directory, fresh log, original/derivative hashes, and tool PIDs.
Port is required even when it is the usual 9876. Use the selected PID's real game
directory, including when Java was launched through a local absolute `@argfile`.

```powershell
.venv/Scripts/python lab.py doctor --identity identity.json
.venv/Scripts/python lab.py capture --identity identity.json --scenario examples/vanilla-book/scenario.json --out reports/book-01
.venv/Scripts/python lab.py validate report reports/book-01/report.json --portable
```

Doctor verifies socket ownership/bind/auth, process launch evidence, fixture
identity, and actual world/player fields. Do not accept placeholder world names
or modes. If the world default mode and actual player mode differ, deliberately
prepare a consistent fixture; do not relabel either observed value. The guide
has a tested empty-hand failure and written-book correction procedure.

Reset always means another `fixture create` from the closed seed; no in-place
reset/delete command exists. Keep captures in new output directories. Screenshot
dimensions and hashes are automatic checks; a separate reviewer must inspect
content, clipping, readable text, and visible controls. Report blank/duplicate
widget diagnostics separately from visual findings.

The memory guard samples the declared Minecraft/tool PID group with a 3800 MiB
working-set ceiling. Other desktop apps are optional informational telemetry.
Sampling cannot guarantee a continuous hard peak; measure private allocation
separately when evaluating the workload. Close the client normally after testing.

## Package and isolated installation smoke

```powershell
.venv/Scripts/python scripts/package_plugin.py --out dist/mc-mod-lab.zip
.venv/Scripts/python scripts/plugin_smoke.py --codex $NativeCodexExecutable
```

Use an installed native Codex CLI executable (`codex.exe` on Windows) for the
smoke, not its npm shell wrapper. The smoke owns that child process, installs the
allowlisted package into a fresh temporary profile/config/cache, starts a fresh
local app-server and checks `skills/list`, then runs the installed CLI's replay
and validation. It does not start a model session or a game. It removes only its
temporary directory after the owned process exits and checks that the host's
normal config and personal marketplace files were not changed.

This tests the Codex compatibility manifest and CLI skill discovery on the tested
host version. It does not submit to a public directory or install into the user's
normal profile. Normal profile installation is a separate operator decision.
The packaging and marketplace formats are described in the
[official plugin documentation](https://developers.openai.com/plugins/build/plugins).
