# Windows Listener Ingress Checkpoint

Status: local implementation and offline verification complete; independent
parent review and approval pending. No commit, push, public acceptance, or live
Minecraft/OBS/native-input trial was performed. Base was clean `main` at
`812bf7e0eea9b8dbc48f11ad28bc0f5958177ce6`; HEAD is unchanged.

## Scope And Contract

Only `lab.py`, `tests/test_lab.py`, `tests/test_listening_socket.py`, `README.md`,
and this receipt changed. The sole changed existing `lab.py` function is
`listening_socket`; AST comparison confirms all 30 other existing function/class
definitions are unchanged. The additions are two native row layouts and one
bounded table reader. No dependencies, software, services, cached ownership,
fallback subprocess, generic networking layer, or runtime monkeypatch was added.

Both IPv4 and IPv6 owner-PID listener tables are required on every check.
Across them, the selected port must have exactly one listener: IPv4 address
`127.0.0.1`, exact positive selected PID. Any competing listener, including IPv6
loopback/mapped/wildcard, or wrong/unknown owner is refused. Other ports are not
candidates. Invalid API results/sizes/counts, truncated rows and unexpected
non-LISTEN states fail closed. Each family permits one sizing call plus at most
three reads, with a 1 MiB buffer cap and strictly increasing resize requests.
Returned counts are bounded by returned size and allocation; spare estimated
capacity is permitted. Ports use network-order lower 16 bits, not host order.
These are allocation/call bounds, not a hard wall-time guarantee for Windows.

Verified before implementation against Microsoft primary documentation:
[API](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable),
[table class](https://learn.microsoft.com/en-us/windows/win32/api/iprtrmib/ne-iprtrmib-tcp_table_class),
[IPv4 row](https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcprow_owner_pid),
[IPv6 row](https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcp6row_owner_pid),
[IPv4 table](https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcptable_owner_pid),
[IPv6 table](https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcp6table_owner_pid),
[port-bit convention](https://learn.microsoft.com/en-us/windows/win32/api/tcpmib/ns-tcpmib-mib_tcprow_w2k).
Natural ctypes alignment supplies header offset 4 and row strides 24/56;
tests independently pack the documented bytes and verify field offsets and ABI.

## Verification Receipt

Windows 10 build 19045, AMD64 Python 3.11.9, existing dependencies only.
`python -m unittest discover -s tests -p test_listening_socket.py -v`: 22 passed,
zero skips, 0.103s. Coverage includes actual functions with injected WinAPI
responses, resize/count/truncation bounds, errors in either family, byte order,
single/external/IPv6/multiple/unknown-PID refusals, no caching or fallback,
pre-HTTP framebuffer/screen/status rejection, and an actual owned Python listener.

Full discovery through `unittest.defaultTestLoader.discover('tests')` and
`TextTestRunner`, equivalent to `python -m unittest discover -s tests -q`:
325 tests, zero failures/errors, 3 skips, 24.466397s. The same baseline 3 skips
are unavailable Windows symlink privileges in GameTest ancestor, fixture copy,
and scenario mods-directory tests. Baseline: 303 tests, 3 skips, 23.852s.
The printed startup-failure JSON is an existing negative-test stub result.
Pre/post-run hashes agreed for all six files listed below, in both the full
suite and latency run; no source mutation occurred during either run.

`python scripts/check_release.py`: passed, 136 tracked files / 97 package files,
schemas/manifest/skill/examples/secrets/portable paths/allowlist. New untracked
test and receipt were separately publication-audited before handoff. Two temporary
packages were byte-identical, contained the exact reviewed allowlist and normalized
working `lab.py`/README bytes, and were removed afterward. Package SHA-256:
`c8228e09073f5569a726907db0ec4574d7403ef334b76036429bf41e7c9714ef`.
`git diff --check` passed; only local Git LF/CRLF notices were emitted.

## Local Latency And Binding Receipt

Run began `2026-10-01T05:41:56.077233+00:00` (September 30 Honolulu).
Unprivileged Python (`IsUserAnAdmin=0`) owned one exclusive, disposable
`127.0.0.1:60868` listener, PID `30984`. No connections or HTTP requests were
sent. Each of five batches performed 20 actual `lab.listening_socket(pid, port)`
calls, then native row readback and the original PowerShell subprocess reference:

```powershell
@(Get-NetTCPConnection -State Listen -LocalPort 60868 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess) | ConvertTo-Json -Compress
```

Reference used `-NoProfile`, capture-output and the existing 10s timeout.
All five native/PowerShell readbacks were exactly one IPv4 LISTEN row at
`127.0.0.1:60868`, owner `30984`, with no IPv6 row at that port. Native checks
and reference checks all accepted. Wrong PID `30985` was refused. The owned
socket was closed (`fileno=-1`); subsequent native row readback was empty and
the actual check refused it. No listener or helper process remains owned.

| Path | Samples | First ms | Min ms | Median ms | Max ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Native (fresh enumeration each call) | 100 | 1.440800 | 0.835700 | 1.028550 | 2.629900 |
| Original PowerShell reference | 5 | 1233.884700 | 1122.158100 | 1127.555500 | 1233.884700 |

PowerShell samples in order, ms: 1233.884700, 1122.966700, 1122.158100,
1185.516100, 1127.555500. Timings use `perf_counter`; shown values are rounded.
This measures local ownership checks, not broker RPCs or future freshness.

## Hash Binding And Limits

SHA-256 values are exact working-file bytes used for both test and latency receipts:

| File | SHA-256 |
| --- | --- |
| `lab.py` | `f0abd7bc5150835f1c2685caaef134ab204b12e9e1737b6f74c5f210d4d81526` |
| `tests/test_lab.py` | `32400175b51e3d70edff5a75956a1667760b004dfb2936b4cd99870a1017baa9` |
| `tests/test_listening_socket.py` | `9c21e7b2e2ce97fe462db2cad1b9361e41ba5e8552c91920982488e89717b2a9` |
| `README.md` | `c2fd914d769a1c72bca72f5b7a0b8ceb4172f3c8832f56806698573f96bf7bfa` |
| `survival_input.py` (unchanged) | `0ef0928564e4652f7e3cde1ba41d2e6e9ed6cc7e8280e6ee18fe1ad3a4e9e86c` |
| `survival_actor.py` (unchanged) | `c6250e43ece67540ab0557f62545057f9721305371d6c8adc803d95d9be4cc40` |

Capture-start timestamps, 2s freshness, 60s actor intent, contexts/anchors,
identity/deadlines/hashes/consumed-ID security are unchanged. Survival, scenario,
runtime, bridge, contracts, package allowlist and dependency files have no diff.
No Aura source, actor, current profile, secret, or historical failure record was
written. The previous GUI refusal cause is still unproven and its inconclusive
gameplay disposition is unchanged. Private broker diagnostics remain separate
parent work. Independent parent review and checkpoint approval must precede any
commit/public push; eventual author and committer must both be Tim Osterhus
`<tim@millrace.ai>`. This receipt's own digest is supplied separately at handoff.

## Parent Acceptance

Parent independently reviewed and approved the native helper, test ABI, strict
ownership/security semantics, Microsoft API contract and IPv6 row documentation.
Parent full suite: 325 tests, PASS, 23.830s, with the 3 existing skips. The actual
disposable-listener test passed. Parent `check_release.py`: PASS, 136 tracked
files / 97 package files. The negative startup-FAIL JSON is an expected test
stub, not a test failure. Reviewed code/tests/README hashes above are unchanged;
this acceptance section is the only post-review content addition.

Parent authorized committing and pushing only the five owned files to `main`
through the existing remote, authenticated as `tim-osterhus`, with both author
and committer Tim Osterhus `<tim@millrace.ai>`. This accepts the bounded public
tool checkpoint, not gameplay or a historical GUI-refusal reclassification.
No MC/OBS/native input is authorized here. Parent will rebind private NativeV4
provenance to the resulting public tool revision before the sole live lease.
