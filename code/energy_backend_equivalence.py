"""
Backend tier (pure WAD-18): the C core's energy checks vs an integer transcription of
HGBNSIEnergyR3._holds, including boundary cases one atomic unit (10^-18) either side of
every threshold and values at the edge of the WAD-18 range.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "common")); sys.path.insert(0, os.path.join(ROOT, "code", "backend", "python"))
from intrng import Rng
from hgbnsi import Core
from hgbnsi.core import CONTEXT
W = 10**18; MAX = 2**127 - 1

def holds(dom, c, mask, cond):  # transcription of HGBNSIEnergyR3._holds (Solidity int256 semantics)
    if dom == 0: return c["energyIn"] == c["energyOut"] + c["energyStored"]
    if dom == 1: return c["valueCreated"] >= c["valueDestroyed"]
    if dom == 2: return abs(c["benefitA"] - c["benefitB"]) <= W
    if dom == 3:
        up, tot = c["systemUp"], c["systemTotal"]
        if tot <= 0 or up < 0 or up > tot: return False
        return up * 100 >= tot * 95
    return (cond & mask) == mask

rng = Rng(23); core = Core(); comparisons = mismatches = boundary = 0
AXIOMS = [(0, 0), (1, 0), (1, 0), (2, 0), (3, 0)]
def val():
    k = rng.below(6)
    if k == 0: return rng.randint(-MAX, MAX)                       # anywhere in range
    if k == 1: return rng.choice([MAX, -MAX, MAX - 1, -MAX + 1, 0, 1, -1])
    return rng.randint(-2000, 2000) * 10**rng.randint(15, 18) + rng.randint(-3, 3)
for t in range(25000):
    c = {k: val() for k in CONTEXT}
    e = rng.choice([-1, 0, 1]); kind = rng.below(4)
    if kind == 0:                                                   # conservation, ± 1 atomic unit
        c["energyOut"] = rng.randint(-10**24, 10**24); c["energyStored"] = rng.randint(-10**24, 10**24)
        c["energyIn"] = c["energyOut"] + c["energyStored"] + e; boundary += 1
    elif kind == 1:                                                 # fairness tolerance, ± 1 atomic unit
        c["benefitB"] = rng.randint(-10**24, 10**24); c["benefitA"] = c["benefitB"] + rng.choice([W, -W]) + e; boundary += 1
    elif kind == 2:                                                 # 95 % uptime threshold, ± 1 atomic unit
        tot = rng.randint(1, 10**30); c["systemTotal"] = tot; c["systemUp"] = min(tot, max(0, -(-tot * 95 // 100) + e)); boundary += 1
    c = {k: max(-MAX, min(MAX, v)) for k, v in c.items()}
    mask = rng.randint(0, 2**256 - 1) & rng.randint(0, 2**256 - 1); cond = rng.randint(0, 2**256 - 1) | (mask if rng.chance(1, 2) else 0)
    axioms = AXIOMS + [(4, mask)]
    r = core.round(axioms, c, cond)
    for i, (d, m) in enumerate(axioms):
        comparisons += 1
        mismatches += (((r["verified_mask"] >> i) & 1) == 1) != holds(d, c, m, cond)
print("RESULT " + json.dumps({"suite": "energy_backend_equivalence", "comparisons": comparisons, "mismatches": mismatches,
                              "boundary_contexts": boundary}, sort_keys=True))
