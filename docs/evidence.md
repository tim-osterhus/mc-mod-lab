# Evidence contracts and portable replay

Install the one validation dependency in a local Python environment:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python lab.py replay --out reports/replay-01
.venv/Scripts/python lab.py validate report reports/replay-01/baseline/report.json --portable
.venv/Scripts/python lab.py validate report reports/replay-01/corrected/report.json --portable
.venv/Scripts/python lab.py validate parity reports/replay-01/parity.json --portable
```

On Linux/macOS, use `.venv/bin/python`. Replay and validation work offline once
dependencies are available; live capture remains Windows-only. Choose a fresh
output directory each time. The replay uses the same `assert_after` function as
live capture: null after-screen fails, `BookViewScreen` succeeds for the exact
same vanilla scenario. Generated images are synthetic color patterns, not game
screenshots. The fixed timestamp makes output reproducible. The deterministic
check passes while client and visual checks stay `not_run`.

`validate` returning `valid` means the evidence is well-formed and its file hashes
match. It does not mean a feature passed. The JSON result retains each parity
dimension independently. A green deterministic test cannot override a failed
client test. A replay report cannot support a live client pass.

## Parity manifest

Start from `examples/parity.json`, governed by `schemas/parity.schema.json`.
Each feature has a concrete requirement, dated public URL or named `bundle:`
reference, optional video timestamp, implementation status/revision, and three
independent checks. `pass` and `fail` require a dated artifact. Visual conclusions
also require an independent reviewer. Intentional substitutions belong in
`exceptions` with a decision, rationale, approver, and date; they never silently
turn a failed dimension into a pass.

Artifact objects contain `file` and `sha256`. Files resolve relative to the JSON
that references them. Use forward-slash relative paths, never `..`, absolute
paths, symlinks, or credentials. A client check's artifact is a live capture
report whose status must match the check. Reports recursively verify their PNG
artifact hashes and dimensions. Visual review is recorded separately in parity,
not by changing the capture report's `visual_check` from `not_reviewed`.

## Capture reports

`schemas/report.schema.json` accepts the historical alpha report shape. New
reports add `evidence_kind: live` and the scenario's `expect` assertion. Historical
reports without an evidence-kind declaration remain `unspecified_legacy`; the
validator does not promote them into live proof. Keep historical reports intact;
record any operator-reviewed provenance separately.

Reports with status `captured` require before/after evidence and acknowledged
control-mode exit. `fail` and `unsupported` preserve partial artifacts when
available. `validate --portable` additionally rejects private fields and common
local path/credential forms. This is a guard, not a sanitizer or a substitute for
reviewing text and image contents before publication.

Capture exit codes remain 0 for `captured` and 2 for `fail` or `unsupported`;
read the JSON status for the distinction. Validation uses 0 for a valid contract
and 2 for invalid/unreadable evidence. Replay exits 0 only when it demonstrates
both the expected failure and correction. No automatic command setup, fixture
mutation, or live transport runs during replay.
