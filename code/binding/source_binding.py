"""
Source binding: ties every implementation to the Solidity contracts as written.

The capsule cannot execute Solidity, so its equivalence tests run against transcriptions. This
check closes that gap from the other side: it reads the .sol files and requires the C backend,
the Python models and the JavaScript client to agree with them on

  - every constant (reason codes, tolerances, thresholds, limits, permit masks);
  - the comparison operator at every acceptance threshold (< vs <=, > vs >=, == vs !=);
  - the order in which refusal reasons are checked;
  - the kernel's decision order and its legal lifecycle transitions;
  - who may call each function (an access-control lock reviewed with the contracts).

Editing a contract without updating the implementations, or the reverse, fails this step.
"""
import ast, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CODE = os.path.join(ROOT, "code")
read = lambda *p: open(os.path.join(CODE, *p)).read()
SOL_K, SOL_E, SOL_R = read("contracts", "SSIVerificationKernel.sol"), read("contracts", "HGBNSIEnergyR3.sol"), read("contracts", "HGBNSIJobRouter.sol")
C_H, C_C = read("backend", "c", "hgbnsi.h"), read("backend", "c", "hgbnsi.c")
PY_R, PY_K = read("frontend", "router_model.py"), read("equivalence", "kernel_equivalence.py")
JS = read("frontend", "core.js")
checks = []

def check(name, ok, detail=""):
    checks.append({"check": name, "ok": bool(ok), "detail": detail})

def body(src, start, end_pat=r"\n    }\n"):
    i = src.index(start); m = re.compile(end_pat).search(src, i)
    return src[i:m.end() if m else len(src)]

def op_of(cond):
    cond = cond.replace("!==", "!=").replace("===", "==")
    m = re.search(r"u256_cmp\([^;]*?\)\s*(<=|>=|!=|==|<|>)\s*0", cond)
    if m: return m.group(1)
    m = re.search(r"(<=|>=|!=|==|<|>)", cond)
    return m.group(1) if m else None

# ------------------------------------------------------------------ router: constants
sol_r = {k: int(v) for k, v in re.findall(r"uint8 public constant (R_[A-Z_]+) = (\d+);", SOL_R)}
c_r = {k.replace("HG_", ""): int(v) for k, v in re.findall(r"(HG_R_[A-Z_]+) = (\d+)", C_H)}
py_names = re.search(r"R_OK, R_LENGTH[^=]*= range\(8\)", PY_R).group(0).split("=")[0].replace(" ", "").split(",")
py_r = {k: i for i, k in enumerate(py_names)}
check("router reason codes: C == Solidity", c_r == sol_r, f"{c_r} vs {sol_r}")
check("router reason codes: Python model == Solidity", py_r == sol_r)
js_reasons = re.search(r"const PLAN_REASONS = \[(.*?)\];", JS, re.S).group(1).count('"') // 2
check("router reason count: JavaScript == Solidity", js_reasons == len(sol_r), f"{js_reasons} vs {len(sol_r)}")
mg = int(re.search(r"MAX_GENERATORS = (\d+);", SOL_R).group(1))
check("max generators: C == Python == JavaScript == Solidity",
      int(re.search(r"HG_MAX_GENERATORS\s+(\d+)", C_H).group(1)) == mg and "s[2] > 32" in PY_R and "s[2] > 32n" in JS, f"Solidity {mg}")

# ------------------------------------------------------------------ router: operators and order
def reason_ops(text, pat):
    out = []
    for line in text.splitlines():
        m = re.search(pat, line)
        if m: out.append((m.group("r"), op_of(line.split("return")[0])))
    return out
inv = {v: k for k, v in sol_r.items()}
sol_seq = reason_ops(body(SOL_R, "function checkPlan"), r"return \((?P<r>R_[A-Z_]+), ")
c_seq = [(r.replace("HG_", ""), o) for r, o in reason_ops(body(C_C, "int hg_check_plan", r"\n}\n"), r"return (?P<r>HG_R_[A-Z_]+)")]
py_seq = reason_ops(body(PY_R, "def check_plan", r"\n\ndef |\Z"), r"return \((?P<r>R_[A-Z_]+), ")
js_seq = [(inv[int(r)], o) for r, o in reason_ops(body(JS, "function checkPlan", r"\n  }\n"), r"return \{ reason: (?P<r>\d+), ")]
for name, seq in (("C backend", c_seq), ("Python model", py_seq), ("JavaScript client", js_seq)):
    check(f"plan check: {name} tests reasons in Solidity's order", [r for r, _ in seq] == [r for r, _ in sol_seq],
          f"{[r for r, _ in seq]} vs {[r for r, _ in sol_seq]}")
    for r in ("R_BELOW_MIN", "R_ABOVE_CAP", "R_DEMAND", "R_CEILING"):
        a, b = dict(seq).get(r), dict(sol_seq).get(r)
        check(f"plan check: {name} uses Solidity's operator for {r}", a == b, f"{a} vs {b}")

# ------------------------------------------------------------------ energy: constants, operators, thresholds
fair = re.search(r"FAIRNESS_TOLERANCE = (1e18|\d+);", SOL_E).group(1)
check("fairness tolerance: Solidity is 1e18", fair == "1e18")
check("fairness tolerance: C == JavaScript == 1e18", "HG_FAIRNESS_TOLERANCE HG_WAD" in C_H and "FAIRNESS_TOLERANCE = WAD;" in JS)
num, den = int(re.search(r"UPTIME_NUMERATOR = (\d+)", SOL_E).group(1)), int(re.search(r"UPTIME_DENOMINATOR = (\d+)", SOL_E).group(1))
check("uptime threshold: C == Solidity", f"HG_UPTIME_NUMERATOR   {num}" in C_H and f"HG_UPTIME_DENOMINATOR {den}" in C_H, f"{num}/{den}")
check("uptime threshold: JavaScript == Solidity", f"c.systemUp * {den}n >= c.systemTotal * {num}n" in JS)

def domain_ops(text, markers):
    out = {}
    for i, mk in enumerate(markers):
        seg = text[text.index(mk): text.index(markers[i + 1]) if i + 1 < len(markers) else len(text)]
        rets = [l for l in seg.splitlines() if "return" in l and "return false" not in l and "return 0;" not in l]
        if i == len(markers) - 1: rets = rets[:1]          # the generic domain: its single return
        out[i] = op_of(rets[-1].split("return", 1)[1]) if rets else None
    return out
sol_h = body(SOL_E, "function _holds")
c_h = body(C_C, "int hg_energy_holds", r"\n}\n")
js_h = body(JS, "function axiomHolds", r"\n  }\n")
sol_d = domain_ops(sol_h, ["Domain.THERMODYNAMICS", "Domain.ECONOMICS", "Domain.ETHICS", "Domain.OPERATIONS", "return (c.conditions"])
c_d = domain_ops(c_h, ["case HG_THERMODYNAMICS", "case HG_ECONOMICS", "case HG_ETHICS", "case HG_OPERATIONS", "default:"])
js_d = domain_ops(js_h, ["case 0:", "case 1:", "case 2:", "case 3:", "default:"])
names = ["thermodynamics", "economics", "ethics", "operations", "generic"]
OPERATORS = {n: (sol_d[i], c_d[i], js_d[i]) for i, n in enumerate(names)}
for i, n in enumerate(names):
    check(f"energy {n}: C uses Solidity's operator", c_d[i] == sol_d[i], f"{c_d[i]} vs {sol_d[i]}")
    check(f"energy {n}: JavaScript uses Solidity's operator", js_d[i] == sol_d[i], f"{js_d[i]} vs {sol_d[i]}")
check("grounding: Solidity refuses fewer than 2 components", "_popcount3(grounding) < 2" in SOL_E)
check("grounding: C and JavaScript require at least 2", ">= 2;" in body(C_C, "int hg_grounding_ok", r"\n}\n") and "registrable: groundingCount(grounding) >= 2" in JS)
check("round classification: Partial at half, everywhere", "uint256(count) * 2 >= uint256(total)" in SOL_E and "verified * 2 >= total" in C_C and "count * 2 >= total" in JS)

# ------------------------------------------------------------------ kernel: permit masks, decision order, transitions
pm = re.search(r"PERMIT_MASK, PERMIT_REQUIRED = (0x[0-9A-Fa-f]+), (0x[0-9A-Fa-f]+)", PY_K)
for i, k in enumerate(("PERMIT_MASK", "PERMIT_REQUIRED")):
    s_val = re.search(k + r" = (0x[0-9A-Fa-f]+);", SOL_K).group(1); p_val = pm.group(i + 1)
    check(f"kernel {k}: transcription == Solidity", int(s_val, 16) == int(p_val, 16), f"{p_val} vs {s_val}")
dec = re.search(r"enum Decision \{([^}]*)\}", SOL_K).group(1).replace(" ", "").split(",")
sol_dec = [dec.index(x) for x in re.findall(r"return Decision\.([A-Z_]+);", body(SOL_K, "function decide("))]
py_dec = [int(x) for x in re.findall(r"return (\d)", body(PY_K, "def decide", r"\ndef "))]
check("kernel decision order: transcription == Solidity", py_dec == sol_dec, f"{py_dec} vs {sol_dec}")
st = re.search(r"enum AssetStatus \{([^}]*)\}", SOL_K).group(1).replace(" ", "").split(",")
sol_t = {(st.index(a), st.index(b)) for a, b in re.findall(r"f == AssetStatus\.(\w+) && t == AssetStatus\.(\w+)", SOL_K)}
py_t = set(ast.literal_eval(re.search(r"return \(f, t\) in (\{[^}]*\})", PY_K).group(1)))
check("kernel lifecycle transitions: transcription == Solidity", py_t == sol_t, f"{sorted(py_t)} vs {sorted(sol_t)}")

# ------------------------------------------------------------------ access-control lock
GUARDS = ("onlyOwner", "onlyVerifier", "onlyHumanGuide", "notStopped")
def access(src):
    out = {}
    for m in re.finditer(r"function (\w+)\([^)]*\)([^{;]*)\{", src, re.S):
        mods = [g for g in GUARDS if re.search(r"\b" + g + r"\b", m.group(2))]
        if "external" in m.group(2) or "public" in m.group(2): out[m.group(1)] = mods
    return out
current = {"SSIVerificationKernel": access(SOL_K), "HGBNSIEnergyR3": access(SOL_E), "HGBNSIJobRouter": access(SOL_R)}
lock = json.load(open(os.path.join(HERE, "access_control.lock.json")))
for contract, fns in lock.items():
    for fn, mods in fns.items():
        now = current[contract].get(fn)
        check(f"access control: {contract}.{fn} guarded by {'+'.join(mods) or 'no modifier'}", now == mods, f"now {now}")

failed = [c for c in checks if not c["ok"]]
for c in failed: print("MISMATCH", c["check"], "|", c["detail"])
print("energy operators (Solidity, C, JavaScript):", OPERATORS)
print(f"source binding: {len(checks) - len(failed)} of {len(checks)} checks agree with the Solidity source")
print("RESULT " + json.dumps({"suite": "source_binding", "checks": len(checks), "mismatches": len(failed)}, sort_keys=True))
sys.exit(1 if failed else 0)
