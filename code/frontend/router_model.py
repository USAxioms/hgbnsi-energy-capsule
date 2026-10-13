"""Reference model of HGBNSIJobRouter's exact checks — a line-by-line transcription of the Solidity."""
import hashlib
WAD = 10**18
WAD_MAX = 2**127 - 1
R_OK, R_LENGTH, R_RANGE, R_BELOW_MIN, R_ABOVE_CAP, R_NON_EXACT, R_DEMAND, R_CEILING = range(8)
REASONS = ["valid", "wrong number of outputs", "output out of range", "running below its minimum",
           "above capacity", "a cost is not exact at 18 decimals", "outputs don't sum exactly to demand",
           "cost above the ceiling"]

def word(n): return (n % (1 << 256)).to_bytes(32, "big")
def packed_hash(arr): return hashlib.sha256(b"".join(word(x) for x in arr)).hexdigest()

def tdiv(a, b):  # Solidity integer division truncates toward zero
    q = abs(a) // abs(b); return q if (a < 0) == (b < 0) else -q
def tmod(a, b):
    r = abs(a) % abs(b); return r if a >= 0 else -r

def validate_spec(s):
    """Returns None if valid, else the BadSpec code."""
    if len(s) < 7: return 1
    if s[2] < 1 or s[2] > 32: return 2
    n = s[2]
    if len(s) != 3 + 4 * n: return 3
    if s[0] <= 0 or s[0] > WAD_MAX: return 4
    if s[1] < 0 or s[1] > WAD_MAX: return 5
    for i in range(n):
        b = 3 + 4 * i
        for k in range(4):
            if s[b + k] < 0 or s[b + k] > WAD_MAX: return 6
        if s[b] == 0 or s[b + 1] > s[b]: return 7
    return None

def check_plan(spec, plan):
    n = spec[2]
    if len(plan) != n: return (R_LENGTH, 0)
    total = cost = 0
    for i in range(n):
        p = plan[i]
        if p < 0 or p > WAD_MAX: return (R_RANGE, 0)
        if p == 0: continue
        b = 3 + 4 * i
        if p < spec[b + 1]: return (R_BELOW_MIN, 0)
        if p > spec[b]: return (R_ABOVE_CAP, 0)
        product = spec[b + 2] * p
        if tmod(product, WAD) != 0: return (R_NON_EXACT, 0)
        total += p
        cost += spec[b + 3] + tdiv(product, WAD)
    if total != spec[0]: return (R_DEMAND, 0)
    if cost > spec[1]: return (R_CEILING, cost)
    return (R_OK, cost)

def gens(spec):
    return [tuple(spec[3 + 4 * i: 7 + 4 * i]) for i in range(spec[2])]
