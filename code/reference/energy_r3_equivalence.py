"""
Reference tier: the pure WAD-18 C core vs ENERGY_R3.py's own Axiom.verify().
ENERGY_R3.py computes with floats internally; it is executed here only as an external oracle
and is never part of the backend. This script itself passes integers only.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "common")); sys.path.insert(0, os.path.join(ROOT, "code", "backend", "python"))
from intrng import Rng
from hgbnsi import Core
from load_energy_r3 import load
m = load(); core = Core(); W = 10**18
ax = m.create_energy_axioms()
BITS = {"EV": 1, "EE": 2, "ET": 4}
DOM = {"thermodynamics": 0, "economics": 1, "ethics": 2, "operations": 3}
# The backend tier hard-codes these tables; confirm they are exactly ENERGY_R3.py's definitions.
grounding = {aid: sum(BITS[g] for g in a.grounds_to_meta if g in BITS) for aid, a in ax.items()}
domain = {aid: DOM[a.domain] for aid, a in ax.items()}
tables_match = grounding == {"AX_001": 3, "AX_002": 1, "AX_003": 5, "AX_004": 6, "AX_005": 5, "AX_006": 7, "AX_007": 4} and \
               domain == {"AX_001": 0, "AX_002": 0, "AX_003": 1, "AX_004": 1, "AX_005": 2, "AX_006": 3, "AX_007": 3}
registrable = [aid for aid in ax if core.grounding_ok(grounding[aid])]
KEYS = ["energy_in", "energy_out", "energy_stored", "value_created", "value_destroyed", "benefit_a", "benefit_b", "system_up", "system_total"]
MAP = dict(zip(KEYS, ["energyIn", "energyOut", "energyStored", "valueCreated", "valueDestroyed", "benefitA", "benefitB", "systemUp", "systemTotal"]))
rng = Rng(3); agree = deliberate = other = 0
for _ in range(30000):
    c = {k: rng.randint(-50, 1200) for k in KEYS}
    if rng.chance(3, 10): c["energy_in"] = c["energy_out"] + c["energy_stored"]
    if rng.chance(3, 10): c["system_up"] = c["system_total"] * rng.choice([95, 96, 94, 100, 101]) // 100
    r = core.round([(domain[a], 0) for a in registrable], {MAP[k]: v * W for k, v in c.items()})
    for i, aid in enumerate(registrable):
        a = ax[aid]; a.verification_notes = []
        exact = ((r["verified_mask"] >> i) & 1) == 1
        if (a.verify(c) == 1) == exact: agree += 1
        elif aid == "AX_006" and c["system_up"] > c["system_total"]: deliberate += 1
        else: other += 1
print("RESULT " + json.dumps({"suite": "energy_reference_equivalence", "comparisons": agree + deliberate + other, "agree": agree,
                              "deliberate_uptime_over_100": deliberate, "unexplained": other, "tables_match_energy_r3": tables_match}, sort_keys=True))
