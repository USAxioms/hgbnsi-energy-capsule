"""Regenerates 400 random job specifications and plans (integer seed 5), answered by the independent Python model and encoder.
Plans for half the valid specs come from the pure WAD-18 C solver."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", "..")); F = os.path.join(ROOT, "code", "frontend")
for p in (os.path.join(F, "processor"), F, os.path.join(ROOT, "code", "common"), os.path.join(ROOT, "code", "backend", "python")): sys.path.insert(0, p)
from abi_py import call_data
from router_model import check_plan, validate_spec, packed_hash, WAD
from intrng import Rng
from hgbnsi import Core
rng = Rng(5); core = Core(); cases = []
for t in range(400):
    n = rng.randint(1, 9)
    spec = [rng.randint(1, 900) * 10**rng.choice([15, 16, 17, 18]), rng.randint(0, 10**6) * WAD, n]
    for _ in range(n):
        cap = rng.randint(1, 300) * WAD
        spec += [cap, rng.choice([0, cap // rng.randint(2, 9)]), rng.randint(0, 9000) * 10**rng.choice([14, 16, 17]), rng.choice([0, rng.randint(0, 500) * WAD])]
    if rng.chance(1, 10): spec[2] = rng.choice([0, 33, n + 1])
    if rng.chance(1, 20): spec[3] = -1
    plan = [rng.choice([0, rng.randint(0, 300) * 10**rng.choice([15, 17, 18]), rng.randint(0, 10**20)]) for _ in range(max(0, n + rng.choice([0, 0, 0, 1, -1])))]
    if validate_spec(spec) is None and rng.chance(1, 2):
        r = core.solve(spec, seed=t, restarts=3); plan = r["plan"] or plan
    r = check_plan(spec, plan) if validate_spec(spec) is None else None
    cases.append({"spec": [str(x) for x in spec], "plan": [str(x) for x in plan], "valid_spec": validate_spec(spec),
                  "check": None if r is None else [r[0], str(r[1])], "hash": "0x" + packed_hash(spec),
                  "calldata": call_data("router", "submitResult", [7, spec, plan]) if validate_spec(spec) is None else None})
json.dump(cases, open(os.path.join(F, "tests", "job_cases.json"), "w"))
print("generated", len(cases), "job cases")
