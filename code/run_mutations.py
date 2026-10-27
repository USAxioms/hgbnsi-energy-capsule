#!/usr/bin/env python3
"""
Sensitivity check: plants one realistic fault at a time in a scratch copy of the capsule and
confirms the capsule detects it, in the step that should. A capsule that cannot fail proves nothing.
Twelve faults across every tier, including edits to the Solidity source and attempts to smuggle in
floating point.
"""
import json, os, shutil, subprocess, sys, tempfile
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MUTATIONS = [
    ("C kernel: stale attestations permitted (freshness dropped)", "code/kernel_c/src/ssi.c",
     "!c->revoked && c->within_scope && c->fresh;", "!c->revoked && c->within_scope;", {"kernel_fingerprint", "kernel_equivalence"}),
    ("C backend: uptime threshold made strict (>= becomes >)", "code/backend/c/hgbnsi.c",
     "HG_UPTIME_NUMERATOR)) >= 0;", "HG_UPTIME_NUMERATOR)) > 0;", {"energy_backend_equivalence", "source_binding"}),
    ("C backend: running exactly at minimum refused (< becomes <=)", "code/backend/c/hgbnsi.c",
     "if (p.v < spec[4 + 4 * i].v) return HG_R_BELOW_MIN;", "if (p.v <= spec[4 + 4 * i].v) return HG_R_BELOW_MIN;",
     {"router_backend_equivalence", "source_binding"}),
    ("C backend: a floating-point computation added", "code/backend/c/hgbnsi.c",
     "int hg_classify_round(int verified, int total) {",
     "int hg_classify_round(int verified, int total) {\n    if (verified < 0) { volatile double r = verified * 0.5; (void)r; }", {"backend_build"}),
    ("Python backend: a float constant added", "code/backend/python/hgbnsi/core.py",
     "REASONS = [", "THRESHOLD = 0.95\nREASONS = [", {"zero_float_audit"}),
    ("JavaScript client: fairness tolerance doubled", "code/frontend/core.js",
     "const FAIRNESS_TOLERANCE = WAD;", "const FAIRNESS_TOLERANCE = WAD * 2n;", {"energy_client_equivalence", "source_binding"}),
    ("Python model: plans that over-supply demand accepted", "code/frontend/router_model.py",
     "if total != spec[0]: return (R_DEMAND, 0)", "if total < spec[0]: return (R_DEMAND, 0)", {"router_backend_equivalence", "job_functions"}),
    ("Solidity router: running exactly at minimum refused", "code/contracts/HGBNSIJobRouter.sol",
     "if (p < spec[b + 1]) return (R_BELOW_MIN, 0);", "if (p <= spec[b + 1]) return (R_BELOW_MIN, 0);", {"source_binding"}),
    ("Solidity energy: ratification allowed during Safe Stop", "code/contracts/HGBNSIEnergyR3.sol",
     "bytes32 rationaleHash) external onlyHumanGuide notStopped {", "bytes32 rationaleHash) external onlyHumanGuide {", {"source_binding"}),
    ("Solidity energy: uptime threshold lowered to 90 %", "code/contracts/HGBNSIEnergyR3.sol",
     "UPTIME_NUMERATOR = 95;", "UPTIME_NUMERATOR = 90;", {"source_binding"}),
    ("Solidity kernel: permit no longer requires 'not revoked'", "code/contracts/SSIVerificationKernel.sol",
     "PERMIT_REQUIRED = 0x1BFF;", "PERMIT_REQUIRED = 0x1FFF;", {"source_binding"}),
    ("C backend: exact refinement disabled", "code/backend/c/hgbnsi.c",
     "if (check_wad(spec, plan, &c) == HG_R_OK) refine(spec, plan);", "if (0) refine(spec, plan);", {"dispatch_benchmark"}),
]
detected = 0; report = []
only = [int(a) for a in sys.argv[1:] if a.isdigit()]
SELECTED = [m for i, m in enumerate(MUTATIONS, 1) if not only or i in only]
for title, rel, old, new, must_fail in SELECTED:
    tmp = tempfile.mkdtemp(prefix="hgbnsi-mutant-"); dst = os.path.join(tmp, "capsule")
    # Copy only the capsule's own folders. On Code Ocean the capsule root is "/", so never copy ROOT itself.
    os.makedirs(dst)
    for part in ("code", "data"):
        shutil.copytree(os.path.join(ROOT, part), os.path.join(dst, part),
                        ignore=shutil.ignore_patterns("reference_results", "__pycache__", "bin"))
    os.makedirs(os.path.join(dst, "results"))
    p = os.path.join(dst, rel); src = open(p).read()
    assert src.count(old) == 1, "mutation target not found: " + rel
    open(p, "w").write(src.replace(old, new))
    
    subprocess.run([sys.executable, os.path.join(dst, "code", "run_all.py")], capture_output=True, text=True)
    
    summary_path = os.path.join(dst, "results", "summary.json")
    if os.path.exists(summary_path):
        s = json.load(open(summary_path))
        failed = {r["step"] for r in s["steps"] if not r["ok"]}
        caught = s["status"] == "FAIL" and must_fail <= failed
    else:
        s = {"status": "FAIL", "steps": []}
        failed = {"execution_crash"}
        caught = False

    detected += caught
    report.append({"mutation": title, "file": rel, "expected_to_fail": sorted(must_fail), "failed_steps": sorted(failed), "detected": caught})
    shown = sorted(failed) if len(failed) <= 4 else sorted(must_fail & failed) + [f"+{len(failed - must_fail)} downstream"]
    print(f"{'DETECTED' if caught else 'MISSED  '}  {title}\n          failing: {', '.join(shown)}", flush=True)
    shutil.rmtree(tmp)
print(f"\nMUTATIONS DETECTED: {detected} of {len(SELECTED)}")
print("RESULT " + json.dumps({"suite": "mutation_check", "detected": detected, "planted": len(SELECTED), "report": report}))
sys.exit(0 if detected == len(SELECTED) else 1)
