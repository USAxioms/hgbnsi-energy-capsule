"""Regenerates 20,000 energy measurements (integer seed 11), including values one atomic unit (10^-18) either side of
every threshold, each labelled by the pure WAD-18 C core. The client must agree exactly."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "common")); sys.path.insert(0, os.path.join(ROOT, "code", "backend", "python"))
from intrng import Rng
from hgbnsi import Core
from hgbnsi.core import CONTEXT
W = 10**18; rng = Rng(11); core = Core(); cases = []
IDS = ["AX_001", "AX_003", "AX_004", "AX_005", "AX_006"]; DOMS = [0, 1, 1, 2, 3]
for _ in range(20000):
    c = {k: rng.randint(-40, 1100) * W + (rng.randint(-5, 5) if rng.chance(1, 3) else 0) for k in CONTEXT}
    kind = rng.below(4); e = rng.choice([-1, 0, 1])
    if kind == 0: c["energyIn"] = c["energyOut"] + c["energyStored"] + e
    elif kind == 1: c["benefitA"] = c["benefitB"] + rng.choice([W, -W]) + e
    elif kind == 2:
        tot = rng.randint(1, 10**24); c["systemTotal"] = tot; c["systemUp"] = min(tot, max(0, -(-tot * 95 // 100) + e))
    r = core.round(list(zip(DOMS, [0] * 5)), c)
    cases.append({"c": {k: str(v) for k, v in c.items()}, "exact": {a: bool((r["verified_mask"] >> i) & 1) for i, a in enumerate(IDS)}})
json.dump(cases, open(os.path.join(ROOT, "code", "frontend", "tests", "energy_cases.json"), "w"))
print("generated", len(cases), "energy measurements")
