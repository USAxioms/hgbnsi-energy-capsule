"""
Zero-floating-point audit, run on every capsule execution. Three independent checks:

 1. Compiler enforcement: every C build in the capsule uses -mgeneral-regs-only, which makes any
    float or double a compile error.
 2. Machine code: every compiled binary is disassembled and searched for floating-point and SIMD
    instructions (x87, SSE, AVX register use and conversions).
 3. Python source: every .py file under code/ is parsed and checked for float literals, true
    division (/), float(), complex(), Decimal, and the float-producing modules and clocks
    (math, cmath, statistics, random, decimal, time.time, time.perf_counter, time.monotonic).

Scope: the backend and every test program. Not in scope, and stated in the report: data/ENERGY_R3.py
(the float reference oracle, run only in the reference tier) and the JavaScript client, whose
values are BigInt but whose language has only one number type, an IEEE double.
"""
import ast, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CODE = os.path.join(ROOT, "code")
FLOAT_INSN = re.compile(r"%[xyz]mm\d|\bf(ld|st|add|sub|mul|div|ild|ist|comi?|ucomi?)\w*\b|cvt\w*s[sd]|\b\w+s[sd]\s|\bmov(ap|up)[sd]\b")
BANNED_MODULES = {"math", "cmath", "statistics", "random", "decimal"}
BANNED_ATTRS = {("time", "time"), ("time", "perf_counter"), ("time", "monotonic"), ("time", "process_time")}

def python_violations(path):
    out = []
    tree = ast.parse(open(path).read(), path)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, (float, complex)):
            out.append((line, "float literal " + repr(node.value)))
        elif isinstance(node, (ast.BinOp, ast.AugAssign)) and isinstance(node.op, ast.Div):
            out.append((line, "true division (/)"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("float", "complex", "Decimal"):
            out.append((line, node.func.id + "()"))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in BANNED_MODULES: out.append((line, "import " + a.name))
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in BANNED_MODULES:
            out.append((line, "from " + node.module + " import"))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and (node.value.id, node.attr) in BANNED_ATTRS:
            out.append((line, node.value.id + "." + node.attr))
    return out

def main():
    report = {"python_files": 0, "python_violations": [], "c_builds_enforced": [], "binaries": [], "float_instructions": 0}
    for d, _, files in os.walk(CODE):
        for f in sorted(files):
            if f.endswith(".py"):
                p = os.path.join(d, f); report["python_files"] += 1
                for line, what in python_violations(p):
                    report["python_violations"].append(f"{os.path.relpath(p, ROOT)}:{line}: {what}")
    build_sh = open(os.path.join(CODE, "backend", "build.sh")).read()
    common = open(os.path.join(CODE, "equivalence", "common.py")).read()
    runner = open(os.path.join(CODE, "run_all.py")).read()
    report["c_builds_enforced"] = [name for name, src in (("backend/build.sh", build_sh), ("equivalence/common.py", common), ("run_all.py kernel build", runner))
                                   if "-mgeneral-regs-only" in src]
    bins = [os.path.join(CODE, "backend", "bin", "hgbnsi_core")]
    bdir = os.path.join(ROOT, "results", "build")
    if os.path.isdir(bdir): bins += [os.path.join(bdir, f) for f in sorted(os.listdir(bdir)) if os.access(os.path.join(bdir, f), os.X_OK) and not f.endswith(".txt")]
    for b in bins:
        if not os.path.exists(b): continue
        dis = subprocess.run(["objdump", "-d", "--no-show-raw-insn", b], capture_output=True, text=True).stdout
        hits = [l.strip() for l in dis.splitlines() if "\t" in l and FLOAT_INSN.search(l.split("\t", 1)[1])]
        report["binaries"].append({"binary": os.path.relpath(b, ROOT), "instructions": sum(1 for l in dis.splitlines() if "\t" in l), "float_instructions": len(hits), "examples": hits[:3]})
        report["float_instructions"] += len(hits)
    report["certified_zero_float"] = (not report["python_violations"] and len(report["c_builds_enforced"]) == 3
                                      and report["float_instructions"] == 0 and len(report["binaries"]) >= 1)
    for v in report["python_violations"]: print("VIOLATION", v)
    for b in report["binaries"]: print(f"binary {b['binary']}: {b['instructions']} instructions, {b['float_instructions']} floating-point")
    print(f"python files scanned: {report['python_files']}, violations: {len(report['python_violations'])}; "
          f"C builds with -mgeneral-regs-only: {len(report['c_builds_enforced'])} of 3")
    print("RESULT " + json.dumps({"suite": "zero_float_audit", "certified_zero_float": report["certified_zero_float"],
                                  "python_files": report["python_files"], "python_violations": len(report["python_violations"]),
                                  "binaries": len(report["binaries"]), "float_instructions": report["float_instructions"]}, sort_keys=True))
    json.dump(report, open(os.path.join(ROOT, "results", "zero_float_audit.json"), "w"), indent=2) if os.path.isdir(os.path.join(ROOT, "results")) else None
    sys.exit(0 if report["certified_zero_float"] else 1)

if __name__ == "__main__":
    main()
