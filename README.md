# SovereigNet Energy — Reproducibility Capsule v2 (Pure WAD-18)

**Human-Guided Blockchain-Native Safe Superintelligence (HGBNSI)**, energy implementation · Version 2.0 · October 2026  
*Michael Aaron Russell, Universal Standard Axiom Corporation*  
**ORCID:** [0009-0001-3360-6709](https://orcid.org/0009-0001-3360-6709)  
**Code Ocean Capsule:** [doi:10.24433/CO.1971294.v1](https://doi.org/10.24433/CO.1971294.v1)  
**Zenodo Archive:** [doi:10.5281/zenodo.23697270](https://doi.org/10.5281/zenodo.23697270)  

```bash
bash code/run
```

Builds the backend, regenerates every test case from integer seeds, reruns every verification, audits the entire capsule for floating-point operations, and checks each result against `code/expected/expected.json`. Expected ending: `CAPSULE PASS: 19 of 19 steps match.` Reference runtime is approximately 12 seconds.

---

## Pure WAD-18: Zero Floating Point, Proved on Every Run

The backend computes exclusively with integers counting $10^{-18}$ units. Results that cannot be represented exactly are refused—never rounded. This is not merely a convention; it is enforced and verified in three independent ways on every run via `code/audit/zero_float.py`:

1. **Compiler Enforcement:** Every C program is built with `-mgeneral-regs-only`, rendering any `float` or `double` usage a compile-time error.
2. **Machine-Code Inspection:** Every compiled binary is disassembled and searched for floating-point instructions. *Reference run: 5 binaries, 0 floating-point instructions.*
3. **AST Static Analysis:** Every `.py` file is parsed to verify zero float literals, `/` division, `float()`, `Decimal`, or float-producing modules/clocks (`math`, `random`, `decimal`, `statistics`, `time.time`). *Reference run: 27 files, 0 violations.*

The audit harness itself is validated: it successfully detects `mulsd`/`addsd` instructions in test float binaries as well as all planted Python violations. Furthermore, mutation testing confirms that smuggling a floating-point operation into either backend fails the capsule suite.

> **Why C Wrapped in Python?**  
> C is the primary common language where the compiler can directly *enforce* the absence of floating-point registers. Python's standard library wraps the C core, providing a zero-dependency architecture. Values cross between processes strictly as decimal integer string representations.

---

## Architecture & Directory Layout

| Path | Description |
| :--- | :--- |
| `code/backend/c/hgbnsi.c`, `hgbnsi.h` | Core logic: energy axiom checks, round classification, job validation, exact plan checks (256-bit intermediate arithmetic to prevent product overflow), merit order, exact optima, and heavy solver |
| `code/backend/c/u256.h` | Unsigned 256-bit integer arithmetic engine |
| `code/backend/c/hgbnsi_core.c` | Line-protocol process interface for Python orchestration |
| `code/backend/build.sh` | Zero-float enforced build pipeline |
| `code/backend/python/hgbnsi/core.py` | Standard-library bridge: pure integer interface |
| `code/backend/python/hgbnsi/server.py` | Standard-library JSON API server on `127.0.0.1` |

### Running the Local API
```bash
cd code/backend/python && python3 -m hgbnsi.server --port 8788
```
Quantities transfer as decimal string literals (e.g., `"620.5"`), which the core parses with bit-exact precision. JSON numbers containing explicit decimal points, exponents, or precision exceeding 18 decimal places are rejected before reaching a float conversion stage.

*Note on Heavy Solver:* The initial stage emulates analog hardware (noise and 8-bit conversion) using integer-only primitives (xorshift generator and Irwin–Hall noise). Explicit rounding mimics 8-bit converter dynamics to formulate candidate proposals. Proposals are accepted strictly through exact checks that do not perform rounding.

---

## Verification & Reproducibility Matrix

| Tier | Step | Reference Result |
| :--- | :--- | :--- |
| **kernel** | `kernel_fingerprint` | C reference kernel v1.1 regenerates SHA-256 `9e180bc9a6aba7bb58813b0ee24e7ae99722786aa655d801aa96bf010ca221b7` over 13,058 lines |
| **kernel** | `kernel_equivalence` | On-chain kernel logic vs. C kernel: 12,771 cases, 0 mismatches |
| **kernel** | `wad_equivalence` | On-chain WAD-18 multiply/divide vs. C kernel: 40,000 operations, 0 mismatches |
| **backend** | `source_binding` | Cross-implementation verification against Solidity source: 60/60 checks pass |
| **backend** | `energy_backend_equivalence` | C core vs. contract: 150,000 comparisons, 0 mismatches (18,712 boundary contexts at exact threshold or $\pm 1$ atomic unit) |
| **backend** | `energy_sample_round` | `ENERGY_R3.py` sample verification: 4/5 hold (`AX_005` fails), Partial status; `AX_002` and `AX_007` refused |
| **backend** | `router_backend_equivalence` | C core vs. Python model: 20,000 specs, 15,303 plans, all 8 refusal reasons verified, 0 mismatches |
| **backend** | `dispatch_benchmark` | 600 heavy instances over 5 seeds: 600 valid, 597 optimal (worst case $0.63\%$ above optimum); raw analog proposals valid 0/14,400; light jobs optimal 200/200; worked example 10,057.5 (optimal) |
| **client** | `energy_client_equivalence` | Front-end vs. pure core at $10^{-18}$ resolution: 100,000 agree, 0 disagree |
| **client** | `client_core` · `job_functions` · `client_logic` · `end_to_end` | Verification passes across 5,914 · 1,835 · 20 · 28 checks respectively |
| **reference** | `energy_reference_equivalence` | Pure core vs. `ENERGY_R3.py`: 138,768/150,000 agree; remaining 11,232 represent uptime $>100\%$, rejected by design; 0 unexplained mismatches |
| **audit** | `zero_float_audit` | Certified zero floating-point operations across codebase |

### Source Binding Guardrails
Source binding addresses contract non-execution in local environments. It parses `.sol` contract sources and mandates absolute equivalence across the C backend, Python models, and JavaScript clients concerning constants, comparison operators, boundary thresholds, decision sequencing, lifecycle state machines, and function access modifiers (`code/binding/access_control.lock.json`). Unsynchronized modifications to contract sources or off-chain implementations cause capsule failure.

---

## Fault Injection & Mutation Testing

Run the automated fault injection suite:
```bash
python3 code/run_mutations.py
```
This suite systematically introduces 12 targeted faults into isolated code copies. *Reference result: 12 of 12 faults detected.*

| Planted Fault | Caught By |
| :--- | :--- |
| C kernel permits stale attestations | `kernel_fingerprint`, `kernel_equivalence` |
| C backend uptime threshold changed to strict (`>=` $\rightarrow$ `>`) | `energy_backend_equivalence`, `source_binding` |
| C backend rejects minimum output bound (`<` $\rightarrow$ `<=`) | `router_backend_equivalence`, `source_binding` |
| C backend introduces floating-point operation | `backend_build` (Compiler refusal) |
| Python backend introduces float constant | `zero_float_audit` |
| JavaScript client doubles fairness tolerance threshold | `energy_client_equivalence`, `source_binding` |
| Python model accepts over-supply state | `router_backend_equivalence`, `job_functions` |
| Solidity router rejects minimum output bound | `source_binding` |
| Solidity energy module permits ratification during Safe Stop | `source_binding` |
| Solidity energy module lowers uptime threshold to $90\%$ | `source_binding` |
| Solidity kernel permit drops "not revoked" requirement | `source_binding` |
| C backend exact refinement disabled | `dispatch_benchmark` |

---

## Key Changes from v1

- **C Backend Rewrite:** Complete C refactor under a strict compiler float ban, with standard-library Python wrapping. Removed legacy Python float solver.
- **System-Wide Float Elimination:** Test generators converted to integer PRNGs; execution timing converted to integer nanoseconds; percentages converted to exact fractions.
- **Source Binding & Expanded Mutation Suite:** Added static source binding for Solidity contract texts and expanded mutation coverage from 3 to 12 planted faults.
- **Multi-Seed Benchmarking:** Expanded benchmark matrix to 5 seeds. Uncovered a worst-case $32.98\%$ gap above optimum; implemented exact swap moves during refinement to bound worst-case deviation to $0.63\%$.
- **Superseded Test Figures:** Updated reference figures due to integer PRNG adoption. Legacy v1 metrics are fully superseded by the current matrix.

---

## Scope of Zero-Float Certification

**Certified In Scope:** C backend, C kernel, C test harnesses, and all Python components in `code/`.

**Explicitly Out of Scope:**
- `ENERGY_R3.py` (`data/`): Floating-point reference oracle used purely for comparative reference in the reference tier. Excluded from the execution backend.
- **JavaScript Client:** Standardizes state representation via `BigInt`. Standard IEEE 754 doubles are restricted to minor internal loop counters. Complete float elimination on the client tier requires WebAssembly compilation of the C core.

---

## Capsule Boundaries & Non-Verified Domain

- Solidity contracts are verified structurally via source binding and logical equivalence rather than direct execution on an EVM instance. Deployments require Solidity `0.8.24` compilation and formal EVM auditing.
- End-to-end execution utilizes a Python state model in place of a full EVM execution node.
- Photonic hardware integration is emulated with respect to integer precision and noise dynamics.
- Verification covers correctness and operational validity; optimization performance is evaluated separately in the benchmark suite.

---

## Execution Environment & Requirements

### System Dependencies
- Python $\ge$ 3.9 (Standard library only)
- GCC with C11 support
- `binutils` (`objdump`)
- Node.js $\ge$ 18
- Isolated environment (No network access required)

### Platform Verification Status
- **Verified:** Complete execution verified on x86-64 Linux with Python 3.12, GCC 13, and Node 22. Python codebase syntax verified against Python 3.9 AST.
- **Unverified Platforms:** Native runs on Python 3.9–3.11 and AArch64 (ARM) architectures. *AArch64 note:* While GCC supports `-mgeneral-regs-only` on ARM, machine-code disassembly regex patterns are tailored for x86-64 instruction sets.

### Containerized Execution
```bash
docker build -t hgbnsi-energy -f environment/Dockerfile .
docker run --rm -v "$PWD/results:/capsule/results" hgbnsi-energy
```

---

## Provenance & Citations

- **ORCID:** [0009-0001-3360-6709](https://orcid.org/0009-0001-3360-6709)
- **Code Ocean DOI:** [10.24433/CO.1971294.v1](https://doi.org/10.24433/CO.1971294.v1)
- **Zenodo DOI:** [10.5281/zenodo.23697270](https://doi.org/10.5281/zenodo.23697270)
- **Reference Kernel:** `ssi-verification-kernel v1.1` (Decision-table SHA-256: `9e180bc9…`)
- **Integrity Manifests:** File-level hashes are recorded in `results/summary.json`. Output artifacts and generated test vectors are fingerprinted in `results/MANIFEST.sha256`. Reference execution outputs reside in `data/reference_results/`.
- **Architectural Credit:** Architecture and technical direction by Michael Aaron Russell. Code, verification suites, and documentation generated with AI assistance under direct supervision; all reported empirical metrics are derived directly from reproducible execution runs.

**Licensing:** All rights reserved. Unlicensed for external redistribution or commercial reuse pending explicit open-source license declaration (e.g., Apache 2.0 / MIT).