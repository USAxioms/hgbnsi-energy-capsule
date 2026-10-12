"""Regenerates the client core test cases from seed 7: WAD literals (answered by the C parser), a 25-entry ledger, encoding references."""
import os, sys, json, hashlib, subprocess
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "code", "equivalence")); sys.path.insert(0, os.path.join(ROOT, "code", "frontend", "processor"))
from common import compile_c, KC
from keccak import keccak256
from intrng import Rng
T = os.path.join(ROOT, "code", "frontend", "tests")
exe = compile_c("parse_harness", os.path.join(HERE, "parse.c"), os.path.join(KC, "src", "wad18.c"))
random = Rng(7)
lits = [l.rstrip("\n") for l in open(os.path.join(ROOT, "data", "wad_literals.txt"))]
for _ in range(3000):
    i = str(random.randint(0, 10**random.randint(0, 22))); f = "".join(random.choice("0123456789") for _ in range(random.randint(0, 20)))
    lits.append(("-" if random.chance(2, 5) else "") + i + ("." + f if f or random.chance(1, 10) else ""))
lits = [l for l in lits if "\n" not in l]
c = subprocess.run([exe], input="\n".join(lits) + "\n", capture_output=True, text=True, check=True).stdout.split("\n")
json.dump({"lits": lits, "c": c[:len(lits)]}, open(os.path.join(T, "parse_cases.json"), "w"))
def w(n): return n.to_bytes(32, "big")
def b32(s): return s.encode().ljust(32, b"\0")
chain = 0x2a; addr = bytes.fromhex("5fbdb2315678afecb367f032d93f642f64180aa3")
head = hashlib.sha256(b32("SSI.GENESIS") + w(chain) + addr).digest()
logs = []; block = 10; prev = None; idx = 0
for seq in range(25):
    tag = b32(random.choice(["SSI.KERNEL", "SSI.AGENT", "SSI.ACTION", "SSI.ATTEST"])); sub = random.randbytes(32); dat = random.randbytes(32)
    block += random.randint(0, 2)
    idx = idx + 1 if block == prev else 0; prev = block
    e = hashlib.sha256(head + w(seq) + tag + sub + dat + w(block)).digest()
    logs.append({"blockNumber": hex(block), "logIndex": hex(idx), "topics": ["0x" + "68" * 32, "0x" + w(seq).hex(), "0x" + e.hex(), "0x" + tag.hex()],
                 "data": "0x" + sub.hex() + dat.hex()})
    head = e
kaddr = bytes.fromhex("e7f1725e7734ce288f8367e1bb143e90bb3f0512")
eg = hashlib.sha256(b32("HGBNSI.ENERGY.GENESIS") + w(chain) + addr + kaddr).hexdigest()
json.dump({"chain": chain, "addr": "0x" + addr.hex(), "kaddr": "0x" + kaddr.hex(), "logs": logs, "head": "0x" + head.hex(), "egenesis": "0x" + eg},
          open(os.path.join(T, "ledger_case.json"), "w"))
def sel(s): return keccak256(s.encode())[:4].hex()
def i256(n): return (n % (1 << 256)).to_bytes(32, "big").hex()
refs = {"registerAxiom": "0x" + sel("registerAxiom(bytes32,bytes32,uint8,uint8,uint256,int256)") + b32("AX_001").hex() + ("ab" * 32) + i256(0) + i256(3) + i256(0) + i256(9800000000000000000),
        "evaluate": "0x" + sel("evaluate((int256,int256,int256,int256,int256,int256,int256,int256,int256,uint256))") + "".join(i256(x) for x in [100 * 10**18, -85 * 10**18, 15, 0, -1, 2**127 - 1, -(2**127 - 1), 950, 1000, 5]),
        "setVerifier": "0x" + sel("setVerifier(address,bool)") + ("00" * 12) + "e7f1725e7734ce288f8367e1bb143e90bb3f0512" + i256(1)}
json.dump(refs, open(os.path.join(T, "abi_refs.json"), "w"))
print("generated core cases:", len(lits), "literals, 25 ledger entries, 3 encoding references")
