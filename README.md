# HGBNSI Energy Implementation — Reproducibility Capsule v2 (Pure WAD-18)

**Human-Guided Blockchain-Native Safe Superintelligence (HGBNSI)**, energy implementation · Version 2.0 · October 2026
Michael Aaron Russell, Universal Standard Axiom Corporation · ORCID 0009-0001-3360-6709

    bash code/run

Builds the backend, regenerates every test case from integer seeds, reruns every verification, audits the whole capsule for floating point, and checks each result against `code/expected/expected.json`. Expected ending: `CAPSULE PASS: 19 of 19 steps match.` Reference runtime is about 12 seconds.

## Pure WAD-18: zero floating point, proved on every run

The backend computes only with integers counting 10⁻¹⁸ units. Results that cannot be represented exactly are refused, never rounded. This is not a convention; it is checked three independent ways on every run (`code/audit/zero_float.py`):

1. **The compiler forbids it.** Every C program is built with `-mgeneral-regs-only`, which turns any `float` or `double` into a compile error.
2. **The machine code contains none.** Every compiled binary is disassembled and searched for floating-point instructions. Reference run: 5 binaries, 0 floating-point instructions.
3. **The Python contains none.** Every `.py` file is parsed and checked for float literals, `/` division, `float()`, `Decimal`, and the float-producing modules and clocks (`math`, `random`, `decimal`, `statistics`, `time.time`). Reference run: 27 files, 0 violations.

The audit itself is shown to work: it detects the `mulsd`/`addsd` instructions in a float binary and every planted Python violation, and the mutation check (below) confirms a float smuggled into either the C or the Python backend fails the capsule.

**Why C, wrapped in Python.** C is the only common language in which the compiler can *enforce* the absence of floating point. Python's standard library wraps it, so the backend has no third-party dependencies. Values cross between them only as decimal integer text.

## The backend

| Path | What it is |
| --- | --- |
| `code/backend/c/hgbnsi.c`, `hgbnsi.h` | The core: energy axiom checks, round classification, job validation, the exact plan check (256-bit intermediates, so no product ever overflows), merit order, exact optimum, and the heavy solver |
| `code/backend/c/u256.h` | Unsigned 256-bit integer arithmetic |
| `code/backend/c/hgbnsi_core.c` | Line-protocol process the Python side talks to |
| `code/backend/build.sh` | The zero-float build |
| `code/backend/python/hgbnsi/core.py` | Standard-library bridge: integers in, integers out |
| `code/backend/python/hgbnsi/server.py` | Standard-library JSON API on 127.0.0.1 |

Run the API with `cd code/backend/python && python3 -m hgbnsi.server --port 8788`. Quantities travel as decimal strings (`"620.5"`) and the core parses them exactly. A JSON number with a decimal point or exponent is refused before it can become a float, and so is a value with more than 18 decimals.

The heavy solver's first stage emulates analog hardware (noise and 8-bit conversion) using integers only: a xorshift generator and Irwin–Hall noise. Its explicit rounding models what a real 8-bit converter does to a signal; it produces proposals only. Nothing it computes is accepted without the exact check, which never rounds.

## What it reproduces

| Tier | Step | Reference result |
| --- | --- | --- |
| kernel | kernel_fingerprint | C reference kernel v1.1 regenerates SHA-256 `9e180bc9a6aba7bb58813b0ee24e7ae99722786aa655d801aa96bf010ca221b7` over 13,058 lines |
| kernel | kernel_equivalence | On-chain kernel logic vs the C kernel: 12,771 cases, 0 mismatches |
| kernel | wad_equivalence | On-chain WAD-18 multiply and divide vs the C kernel: 40,000 operations, 0 mismatches |
| backend | source_binding | Every implementation agrees with the Solidity text: 60 of 60 checks |
| backend | energy_backend_equivalence | C core vs the contract: 150,000 comparisons, 0 mismatches, 18,712 contexts at a threshold or ±1 atomic unit |
| backend | energy_sample_round | ENERGY_R3.py's sample: 4 of 5 hold (AX_005 fails), Partial; AX_002 and AX_007 refused |
| backend | router_backend_equivalence | C core vs the Python model: 20,000 specs, 15,303 plans, all 8 reasons, 0 mismatches |
| backend | dispatch_benchmark | 600 heavy instances over 5 seeds: 600 exactly valid, 597 optimal, worst 0.63 % above optimum; raw analog answers exactly valid 0 of 14,400; light jobs optimal 200 of 200; worked example 10,057.5 (optimal) |
| client | energy_client_equivalence | Front end vs the pure core at 10⁻¹⁸ resolution: 100,000 agree, 0 disagree |
| client | client_core · job_functions · client_logic · end_to_end | 5,914 · 1,835 · 20 · 28 checks pass |
| reference | energy_reference_equivalence | Pure core vs ENERGY_R3.py: 138,768 of 150,000 agree; all 11,232 others are uptime above 100 %, refused by design; 0 unexplained; the backend's axiom tables match the file exactly |
| audit | zero_float_audit | Certified zero floating point |

**Source binding** closes the gap that the contracts cannot be executed here. It reads the `.sol` files and requires the C backend, the Python models and the JavaScript client to match them on every constant, the comparison operator at every acceptance threshold, the order of refusal checks, the kernel's decision order and lifecycle transitions, and which modifiers guard each function (`code/binding/access_control.lock.json`). Editing a contract without updating the implementations, or the reverse, fails the capsule.

## It can fail

    python3 code/run_mutations.py

plants twelve realistic faults, one at a time, in a scratch copy. Reference result: **12 of 12 detected**.

| Planted fault | Caught by |
| --- | --- |
| C kernel permits stale attestations | kernel_fingerprint, kernel_equivalence |
| C backend uptime threshold made strict (`>=` → `>`) | energy_backend_equivalence, source_binding |
| C backend refuses output exactly at minimum (`<` → `<=`) | router_backend_equivalence, source_binding |
| C backend gains a floating-point computation | backend_build (the compiler refuses it) |
| Python backend gains a float constant | zero_float_audit |
| JavaScript client doubles the fairness tolerance | energy_client_equivalence, source_binding |
| Python model accepts over-supply | router_backend_equivalence, job_functions |
| Solidity router refuses output exactly at minimum | source_binding |
| Solidity energy module allows ratification during Safe Stop | source_binding |
| Solidity energy module lowers uptime to 90 % | source_binding |
| Solidity kernel permit stops requiring "not revoked" | source_binding |
| C backend exact refinement disabled | dispatch_benchmark |

## Changes from v1

- **Backend rewritten in C** under a compiler ban on floating point, with a Python standard-library wrapper and API. The Python float solver was removed.
- **Floats removed everywhere else:** test generators use an integer random generator; timing uses integer nanoseconds; percentages are exact fractions.
- **Source binding** to the Solidity text (new), and **12 planted faults** (was 3). Building the mutation check found a flaw in the binding check itself, which was comparing the wrong line for one energy domain; it was fixed.
- **Five-seed benchmark** (was one). It exposed a worst case 32.98 % above optimum that one seed had not contained; adding exact swap moves to the refinement reduced the worst case to 0.63 %.
- **Numbers changed** because random cases now come from the integer generator. v1 figures (for example "1 of 2,880 raw answers valid", "113 of 120 optimal") are superseded by the table above; documents quoting v1 figures should be updated.

## Scope of the zero-float certification

Certified: the C backend, the C kernel, every C test harness, and every Python file in `code/`. Two things are outside it, by design:

- **ENERGY_R3.py** (`data/`) is a floating-point program. It runs only in the reference tier, as an external oracle to compare against, and is never part of the backend. The pure tiers read it as text only.
- **The JavaScript client** keeps every quantity as a `BigInt`, but JavaScript's only other number type is an IEEE double, used for small counters. A strictly float-free client would compile this C core to WebAssembly.

## What this capsule does not verify

- The Solidity contracts are not compiled or executed; source binding and equivalence testing cover their logic, not their behaviour on the Ethereum Virtual Machine. Compile with Solidity 0.8.24, deploy to a testnet, and have them audited.
- The end-to-end step uses a Python model of the chain, not the EVM.
- The photonic processor is emulated (precision and noise only).
- The contracts and solver check validity, not optimality; the benchmark measures optimality separately.

## Code Ocean

The capsule uses Code Ocean's layout: everything it needs is inside `code/` and `data/`, it writes only to `results/`, and the entry point is `code/run`. Configure the environment in Code Ocean's interface with GCC, binutils, Python 3 and Node.js 18 or newer; `environment/Dockerfile` is the equivalent for running locally.

## Requirements

Python 3.9 or newer (standard library only), GCC with C11, binutils (`objdump`), Node.js 18 or newer. No network access.

**What has been verified:** the full run on x86-64 Linux with Python 3.12, GCC 13 and Node 22. Every Python file also parses under the Python 3.9 grammar. **Not yet verified:** a full run on Python 3.9 to 3.11, and on AArch64 (ARM). GCC supports `-mgeneral-regs-only` on AArch64, but the machine-code audit's instruction patterns were written and tested for x86-64, so on ARM treat its result as unconfirmed until it is tested there. Or: `docker build -t hgbnsi-energy -f environment/Dockerfile .` then `docker run --rm -v "$PWD/results:/capsule/results" hgbnsi-energy`.

## Provenance

Reference kernel: ssi-verification-kernel v1.1 (decision-table SHA-256 `9e180bc9…`). `results/summary.json` records the SHA-256 of every source file; `results/MANIFEST.sha256` fingerprints every output and regenerated test case; `data/reference_results/` holds the reference run.

The architecture and direction of this work are by Michael Aaron Russell. Code, tests and documentation were produced with AI assistance under his direction; every number above is produced by the run itself.

**License:** none is declared yet, so by default all rights are reserved and others may read but not reuse this code. If you intend it to be open source, add a license file (for example Apache 2.0 or MIT) before publishing.
