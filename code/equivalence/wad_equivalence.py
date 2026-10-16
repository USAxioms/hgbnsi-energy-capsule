"""WAD-18 multiply and divide: the contract's WAD18 library (transcribed) vs the C kernel's wad_mul / wad_div."""
import os, subprocess
from common import compile_c, emit, KC
from intrng import Rng
HERE = os.path.dirname(os.path.abspath(__file__))
exe = compile_c("wad_harness", os.path.join(HERE, "wadh.c"), os.path.join(KC, "src", "wad18.c"))
random = Rng(18)
S = 10**18; MAX = 2**127 - 1; MIN = -MAX
def tdiv(a, b): q = abs(a) // abs(b); return q if (a < 0) == (b < 0) else -q
def tmod(a, b): r = abs(a) % abs(b); return r if a >= 0 else -r
def inr(x): return MIN <= x <= MAX
def mul(a, b):  # WAD18.mul: overflow checked before exactness
    p = a * b; q = tdiv(p, S)
    if not inr(q): return ("OVERFLOW", None)
    if tmod(p, S) != 0: return ("NON_EXACT", None)
    return ("OK", q)
def div(a, b):  # WAD18.div
    if b == 0: return ("DIV_ZERO", None)
    n = a * S; q = tdiv(n, b)
    if not inr(q): return ("OVERFLOW", None)
    if tmod(n, b) != 0: return ("NON_EXACT", None)
    return ("OK", q)
CERR = {0: "OK", 1: "OVERFLOW", 2: "DIV_ZERO", 3: "NON_EXACT"}
gens = [lambda: random.randint(-10**6, 10**6) * S, lambda: random.randint(-10**3, 10**3) * S // random.choice([1, 2, 4, 5, 8, 10, 20, 25, 100]),
        lambda: random.randint(MIN, MAX), lambda: random.choice([0, 1, -1, S, -S, MAX, MIN, MAX // S, 2 * S, S // 2]),
        lambda: random.randint(-10**24, 10**24)]
pairs = [(random.choice(gens)(), random.choice(gens)()) for _ in range(20000)]
out = subprocess.run([exe], input="\n".join(f"{a} {b}" for a, b in pairs), capture_output=True, text=True, check=True).stdout.split("\n")
mm = 0; kinds = {}
for (a, b), line in zip(pairs, out):
    t = line.split(); cm = (CERR[int(t[0])], None if t[1] == '-' else int(t[1])); cd = (CERR[int(t[2])], None if t[3] == '-' else int(t[3]))
    for c, s in ((cm, mul(a, b)), (cd, div(a, b))):
        kinds[s[0]] = kinds.get(s[0], 0) + 1; mm += c != s
emit({"suite": "wad_equivalence", "operations": 2 * len(pairs), "mismatches": mm, "outcomes": kinds})
