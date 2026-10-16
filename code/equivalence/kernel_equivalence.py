"""Kernel decision logic: SSIVerificationKernel.sol (transcribed) vs the compiled C reference kernel, exhaustively."""
import os, subprocess
from common import compile_c, emit, KC
HERE = os.path.dirname(os.path.abspath(__file__))
exe = compile_c("kernel_harness", os.path.join(HERE, "harness.c"), *[os.path.join(KC, "src", f) for f in ("ssi.c", "sha256.c", "wad18.c")])
c_out = subprocess.run([exe], capture_output=True, text=True, check=True).stdout.splitlines()

# ---- transcription of library SSIKernelLogic in SSIVerificationKernel.sol
PERMIT_MASK, PERMIT_REQUIRED = 0x1FFF, 0x1BFF
def vs(mask, count):
    if count == 0: return False
    need = (1 << count) - 1; return (mask & need) == need
def permit(b): return (b & PERMIT_MASK) == PERMIT_REQUIRED
def decide(a, v, p):
    if not a: return 3
    if v == 2: return 2
    if v == 1: return 1
    if not p: return 1
    return 0
def mediate(k, p): return False if k > 9 else p
def csl(s, r, u, n, e): return s and not r and n <= u and e
def directive(s, i, e, r, n, c, sc): return s and i <= n and n <= e and c <= r and sc
def cap(n, a, g): return ((n & ~a) & 0xFFFFFFFF) == 0 or g
def nonreg(b, a, c): need = (1 << c) - 1; return (b & ~a & need) == 0
def adopt6(*x):
    for i, v in enumerate(x):
        if not v: return i + 1
    return 0
def trans(f, t): return (f, t) in {(0, 1), (0, 5), (1, 2), (2, 3), (3, 2), (3, 4), (2, 4)}
def verify(c):
    for i in range(11):
        if ((c >> i) & 1) == 0: return i + 1
    return 0
NAMES = ["PASS", "TYPE_VALID", "WAD18_VALID", "KERNEL_VALID", "CSL_VALID", "AUTHORIZATION_VALID", "SAFETY_INVARIANTS_VALID",
         "CAPABILITY_VALID", "CERTIFICATE_VALID", "CERTIFICATE_BINDS_TO", "PROVENANCE_VALID", "SUPERINTELLIGENCE_CRITERION"]
def ttmask(x):
    m = 0
    for i in range(3):
        if x % 3 == 0: m |= 1 << i
        x //= 3
    return m
B = lambda v: int(bool(v))
mism = n = 0
for line in c_out:
    t = line.split(); k = t[0]; a = t[1:]
    if k == "Y": got, exp = NAMES[verify(int(a[0]))], a[1]
    else:
        a = list(map(int, a)); exp = a[-1]; a = a[:-1]
        if k == "P": got = B(permit(a[0]))
        elif k == "D": got = decide(*a)
        elif k == "T": got = B(trans(*a))
        elif k == "A": m = a[0]; got = adopt6(*[(m >> i) & 1 for i in range(6)]); got, exp = B(got == 0), exp
        elif k == "M": got = B(mediate(255 if a[0] < 0 else a[0], a[1]))
        elif k == "C": got = B(cap(*a))
        elif k == "N": got = B(nonreg(ttmask(a[0]), ttmask(a[1]), 3))
        elif k == "V": got = B(vs(ttmask(a[1]), a[0]))
        elif k == "R": got = B(directive(*a))
        elif k == "L": got = B(csl(*a))
    n += 1; mism += got != exp
emit({"suite": "kernel_equivalence", "cases": n, "mismatches": mism})
