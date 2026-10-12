#!/usr/bin/env python3
"""
HGBNSI energy implementation — reproducibility capsule runner (v2, pure WAD-18).

Builds the zero-float C core, regenerates every test case from integer seeds, reruns every
verification, audits the whole capsule for floating point, compares each result with
code/expected/expected.json, and writes results/. Exit code 0 only if everything matches.

Tiers
  kernel     the C reference kernel and its on-chain transcription
  backend    the pure WAD-18 C core and its Python standard-library wrapper
  client     the Sovereign Axiomatic Front End's logic (JavaScript, BigInt values)
  reference  comparison with ENERGY_R3.py, a floating-point program used only as an external oracle
  audit      zero floating point, proved over every compiled binary and every Python file
"""
import hashlib, json, os, platform, re, shutil, subprocess, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CODE, RES = os.path.join(ROOT, "code"), os.path.join(ROOT, "results")
LOGS = os.path.join(RES, "logs")
EXPECTED = json.load(open(os.path.join(CODE, "expected", "expected.json")))
KERNEL_CFLAGS = "-std=c11 -O2 -Wall -Wextra -Werror -mgeneral-regs-only"

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

def run(name, cmd, cwd):
    t0 = time.monotonic_ns()
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    open(os.path.join(LOGS, name + ".log"), "w").write(p.stdout + (("\n[stderr]\n" + p.stderr) if p.stderr.strip() else ""))
    return p.returncode, p.stdout, (time.monotonic_ns() - t0) // 1000000

def result_json(_rc, stdout):
    lines = [l for l in stdout.splitlines() if l.startswith("RESULT ")]
    return json.loads(lines[-1][7:]) if lines else None

def counts(prefix=""):
    def parse(_rc, stdout):
        m = re.search(prefix + r"passed (\d+), failed (\d+)", stdout)
        return {"passed": int(m.group(1)), "failed": int(m.group(2))} if m else None
    return parse

def kernel_fingerprint(_rc, stdout):
    m = re.search(r"TABLE_SHA256 ([0-9a-f]{64})", stdout)
    table = os.path.join(RES, "build", "decision_table_c.txt")
    return {"decision_table_sha256": m.group(1) if m else None, "lines": sum(1 for _ in open(table)) if os.path.exists(table) else 0}

def main():
    record = "--record" in sys.argv
    os.makedirs(RES, exist_ok=True)                 # on Code Ocean /results is a mount point: empty it, never remove it
    for entry in os.listdir(RES):
        p = os.path.join(RES, entry)
        shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
    os.makedirs(LOGS); os.makedirs(os.path.join(RES, "build"))
    env = {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()}
    for tool, args in (("gcc", ["gcc", "--version"]), ("node", ["node", "--version"]), ("objdump", ["objdump", "--version"])):
        if not shutil.which(tool): sys.exit(f"Missing required tool: {tool}. See README.md.")
        env[tool] = subprocess.run(args, capture_output=True, text=True).stdout.splitlines()[0]
    if int(env["node"].lstrip("v").split(".")[0]) < 18: sys.exit(f"Node 18 or newer is required (found {env['node']}).")
    json.dump(env, open(os.path.join(RES, "environment.json"), "w"), indent=2)

    K, EQ, EN = os.path.join(CODE, "kernel_c"), os.path.join(CODE, "equivalence"), os.path.join(CODE, "energy")
    B, G, F = os.path.join(CODE, "backend"), os.path.join(CODE, "generators"), os.path.join(CODE, "frontend")
    table = os.path.join(RES, "build", "decision_table_c.txt")
    kernel_cmd = (f'gcc {KERNEL_CFLAGS} -I"{K}/include" "{K}/src/wad18.c" "{K}/src/sha256.c" "{K}/src/ssi.c" "{K}/src/tables.c" '
                  f'-o "{RES}/build/tables" && "{RES}/build/tables" "{ROOT}/data/wad_literals.txt" > "{table}" 2> "{RES}/build/table_hash.txt"; '
                  f'cat "{RES}/build/table_hash.txt"')
    steps = [
        ("kernel", "kernel_fingerprint", ["sh", "-c", kernel_cmd], K, kernel_fingerprint,
         "The C reference kernel regenerates its published decision-table fingerprint"),
        ("kernel", "kernel_equivalence", ["python3", "kernel_equivalence.py"], EQ, result_json,
         "On-chain kernel logic agrees with the C kernel on every decision case"),
        ("kernel", "wad_equivalence", ["python3", "wad_equivalence.py"], EQ, result_json,
         "On-chain WAD-18 multiply and divide agree with the C kernel"),
        ("backend", "backend_build", ["sh", "build.sh"], B, None,
         "Build the pure WAD-18 C core with floating point forbidden by the compiler"),
        ("backend", "source_binding", ["python3", "binding/source_binding.py"], CODE, result_json,
         "Every implementation agrees with the Solidity source: constants, operators, order, access"),
        ("backend", "energy_backend_equivalence", ["python3", "energy_backend_equivalence.py"], EN, result_json,
         "C core energy checks vs the contract, including ±1 atomic unit at every threshold"),
        ("backend", "energy_sample_round", ["python3", "energy_sample_round.py"], EN, result_json,
         "ENERGY_R3.py's sample measurement: Partial, awaiting the human guide"),
        ("backend", "router_backend_equivalence", ["python3", "router_equivalence.py"], B, result_json,
         "C core job checks vs the independent Python model, including 256-bit extremes"),
        ("backend", "dispatch_benchmark", ["python3", "benchmark.py"], B, result_json,
         "Integer analog emulator behind the exact gate, five seeds, vs the exact optimum"),
        ("client", "generate_core_cases", ["python3", "gen_core_cases.py"], G, None, "Regenerate client core cases (integer seed 7)"),
        ("client", "generate_job_cases", ["python3", "gen_job_cases.py"], G, None, "Regenerate job cases (integer seed 5)"),
        ("client", "generate_energy_cases", ["python3", "gen_energy_cases.py"], G, None, "Regenerate energy cases (integer seed 11)"),
        ("client", "energy_client_equivalence", ["node", "tests/energy.test.js"], F, result_json,
         "Front-end energy checks agree with the pure core at 10^-18 resolution"),
        ("client", "client_core", ["node", "tests/core.test.js"], F, counts(),
         "Front-end core: SHA-256, WAD-18 parsing vs C, encoding, ledger rebuild"),
        ("client", "job_functions", ["node", "tests/jobs.test.js"], F, counts("jobs: "),
         "Front-end job functions vs the independent Python model"),
        ("client", "client_logic", ["node", "tests/app.test.js"], F, counts(),
         "Front-end application logic against a mock node"),
        ("client", "end_to_end", ["node", "tests/e2e.test.js"], F, counts("e2e: "),
         "Guide, verifier, chain model and the pure-core processor, end to end"),
        ("reference", "energy_reference_equivalence", ["python3", "energy_r3_equivalence.py"], os.path.join(CODE, "reference"), result_json,
         "The pure core agrees with ENERGY_R3.py (a float program, used only as an oracle)"),
        ("audit", "zero_float_audit", ["python3", "zero_float.py"], os.path.join(CODE, "audit"), result_json,
         "Zero floating point: compiler-enforced C, clean machine code, clean Python"),
    ]
    rows, ok_all = [], True
    for tier, name, cmd, cwd, parse, title in steps:
        rc, out, ms = run(name, cmd, cwd)
        if parse is None:
            got, exp, good = None, None, rc == 0
        else:
            got, exp = parse(rc, out), EXPECTED.get(name, {})
            good = got is not None and bool(exp) and all(got.get(k) == v for k, v in exp.items())
            if record: good = got is not None
        ok_all &= good
        rows.append({"tier": tier, "step": name, "description": title, "ok": good, "milliseconds": ms, "result": got, "expected": exp})
        print(f"{'PASS' if good else 'FAIL'}  {tier:9s} {name:30s} {ms // 1000:>3}.{ms % 1000 // 100}s  {title}", flush=True)
        if record and got is not None: print("        recorded:", json.dumps(got, sort_keys=True))

    fps = {}
    for d in ("code/contracts", "code/backend/c", "code/backend/python/hgbnsi", "code/kernel_c/src", "code/frontend"):
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            p = os.path.join(ROOT, d, f)
            if os.path.isfile(p) and f.endswith((".sol", ".c", ".h", ".py", ".js")): fps[f"{d}/{f}"] = sha(p)
    for f in ("data/ENERGY_R3.py", "data/wad_literals.txt"): fps[f] = sha(os.path.join(ROOT, f))
    summary = {"capsule": "HGBNSI energy implementation v2 (pure WAD-18)", "status": "PASS" if ok_all else "FAIL",
               "environment": env, "steps": rows, "source_fingerprints": fps}
    json.dump(summary, open(os.path.join(RES, "summary.json"), "w"), indent=2)
    with open(os.path.join(RES, "summary.md"), "w") as f:
        f.write(f"# HGBNSI energy capsule v2: {summary['status']}\n\n| Tier | Step | Result | What it shows |\n| --- | --- | --- | --- |\n")
        for r in rows: f.write(f"| {r['tier']} | {r['step']} | {'PASS' if r['ok'] else 'FAIL'} | {r['description']} |\n")
    with open(os.path.join(RES, "MANIFEST.sha256"), "w") as f:
        for d, _, files in sorted(os.walk(RES)):
            for fn in sorted(files):
                p = os.path.join(d, fn)
                if fn != "MANIFEST.sha256" and os.sep + "build" not in p: f.write(f"{sha(p)}  {os.path.relpath(p, RES)}\n")
        tdir = os.path.join(F, "tests")
        for fn in sorted(os.listdir(tdir)):
            if fn.endswith(".json"): f.write(f"{sha(os.path.join(tdir, fn))}  ../code/frontend/tests/{fn}\n")
    print(f"\nCAPSULE {summary['status']}: {sum(r['ok'] for r in rows)} of {len(rows)} steps match. See results/summary.md")
    sys.exit(0 if ok_all else 1)

if __name__ == "__main__":
    main()
