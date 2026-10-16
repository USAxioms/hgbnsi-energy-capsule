"""
Backend tier (pure WAD-18): ENERGY_R3.py's own sample measurement, classified by the C core,
and the grounding rule applied to the seven axioms. ENERGY_R3.py is read as text, never run.
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "backend", "python"))
from hgbnsi import Core
core = Core(); W = 10**18
src = open(os.path.join(ROOT, "data", "ENERGY_R3.py")).read()
sample = {"energy_in": 100, "energy_out": 85, "energy_stored": 15, "value_created": 100, "value_destroyed": 90,
          "benefit_a": 50, "benefit_b": 48, "system_up": 950, "system_total": 1000}
for k, v in sample.items():
    assert re.search(r"['\"]" + k + r"['\"]\s*:\s*" + str(v) + r"\b", src), "sample value not found in ENERGY_R3.py: " + k
ctx = {"energyIn": 100 * W, "energyOut": 85 * W, "energyStored": 15 * W, "valueCreated": 100 * W, "valueDestroyed": 90 * W,
       "benefitA": 50 * W, "benefitB": 48 * W, "systemUp": 950 * W, "systemTotal": 1000 * W}
# Grounding bits EV=1, EE=2, ET=4 for each axiom, as defined in ENERGY_R3.py (confirmed in the reference tier).
GROUNDING = {"AX_001": 3, "AX_002": 1, "AX_003": 5, "AX_004": 6, "AX_005": 5, "AX_006": 7, "AX_007": 4}
DOMAIN = {"AX_001": 0, "AX_002": 0, "AX_003": 1, "AX_004": 1, "AX_005": 2, "AX_006": 3, "AX_007": 3}
refused = [a for a, g in GROUNDING.items() if not core.grounding_ok(g)]
registrable = [a for a in GROUNDING if a not in refused]
r = core.round([(DOMAIN[a], 0) for a in registrable], ctx)
failed = [a for i, a in enumerate(registrable) if not (r["verified_mask"] >> i) & 1]
print("RESULT " + json.dumps({"suite": "energy_sample_round", "verified": r["verified"], "total": r["total"],
                              "status": r["status"], "failed": failed, "refused_at_registration": refused}, sort_keys=True))
