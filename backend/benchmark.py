"""
Backend tier (pure WAD-18): the integer analog emulator behind the exact gate, on heavy dispatch
instances across 5 independent seeds, compared with the exhaustive exact optimum. Every gap is an
exact fraction; percentages are formatted from integers.
"""
import json, os, sys
from fractions import Fraction
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "common")); sys.path.insert(0, os.path.join(HERE, "python"))
from intrng import Rng
from hgbnsi import Core
W = 10**18; U = 10**15
core = Core()

def pct(fr):                        # exact fraction → "x.xx %", rounded down, integers only
    bp = fr.numerator * 10000 // fr.denominator
    return f"{bp // 100}.{bp % 100:02d} %"

def instance(rng, n, heavy=True):
    g = []
    for _ in range(n):
        cap = rng.randint(50, 400) * W
        mn = (rng.randint(0, 40) * cap // 100) // U * U if heavy else 0
        g += [cap, mn, rng.randint(1000, 8000) * 10**16, rng.randint(0, 500) * W if heavy else 0]
    total = sum(g[0::4])
    return [(rng.randint(30, 80) * total // 100) // U * U, 10**12 * W, n] + g

per_seed = []; gaps = []; agg = {"instances": 0, "valid": 0, "optimal": 0, "raw_valid": 0, "proposals": 0}
for seed in (42, 1, 2, 3, 4):
    rng = Rng(seed); s = {"seed": seed, "instances": 0, "valid": 0, "optimal": 0}
    while s["instances"] < 120:
        spec = instance(rng, rng.randint(4, 11))
        opt = core.optimum(spec)
        if opt is None: continue
        s["instances"] += 1
        r = core.solve(spec, seed=seed * 100000 + s["instances"], restarts=24)
        agg["proposals"] += r["proposals"]; agg["raw_valid"] += r["raw_exact_valid"]
        if r["plan"] is None: continue
        assert core.check(spec, r["plan"]) == (0, r["cost"])            # every answer exactly valid
        s["valid"] += 1; s["optimal"] += r["cost"] == opt[0]
        gaps.append(Fraction(r["cost"] - opt[0], opt[0]))
    per_seed.append(s)
    for k in ("instances", "valid", "optimal"): agg[k] += s[k]
gaps.sort()
rng = Rng(7); light = 0
for _ in range(200):
    spec = instance(rng, rng.randint(2, 9), heavy=False)
    p = core.merit(spec); opt = core.optimum(spec)
    light += core.check(spec, p) == (0, opt[0])
D = lambda x: Fraction(x).numerator * W // Fraction(x).denominator
ex = [D("620"), D("30000"), 6] + [D(v) for g in [("200", "40", "12.5", "300"), ("150", "0", "2", "0"), ("120", "30", "68", "450"),
                                                ("250", "100", "31.25", "900"), ("80", "0", "1.5", "0"), ("60", "10", "45", "50")] for v in g]
er = core.solve(ex, seed=1, restarts=24); eo = core.optimum(ex)
for s in per_seed: print(f"seed {s['seed']:>2}: {s['valid']}/{s['instances']} exactly valid, {s['optimal']} optimal")
print(f"all seeds: {agg['valid']}/{agg['instances']} valid, {agg['optimal']} optimal; median gap {pct(gaps[len(gaps) // 2])}, worst {pct(gaps[-1])}; "
      f"raw analog answers exactly valid {agg['raw_valid']} of {agg['proposals']}; light optimal {light}/200; evening peak {core.format(er['cost'])}")
print("RESULT " + json.dumps({"suite": "dispatch_benchmark", "seeds": 5, "heavy_instances": agg["instances"], "heavy_valid": agg["valid"],
      "heavy_optimal": agg["optimal"], "seed42_optimal": per_seed[0]["optimal"], "median_gap": pct(gaps[len(gaps) // 2]), "worst_gap": pct(gaps[-1]),
      "raw_analog_valid": agg["raw_valid"], "raw_analog_proposals": agg["proposals"], "light_optimal": light,
      "evening_peak_cost": core.format(er["cost"]), "evening_peak_optimal": er["cost"] == eo[0]}, sort_keys=True))
