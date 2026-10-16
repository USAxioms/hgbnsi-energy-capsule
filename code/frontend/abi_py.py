"""Minimal ABI encoding/decoding (static types and arrays of static types), independent of the JS core."""
import json, os
from keccak import keccak256
ABI = json.load(open(os.path.join(os.path.dirname(__file__), "abi.json")))
M256 = 1 << 256
def w(n): return (int(n) % M256).to_bytes(32, "big")
def types_of(sig):
    inner = sig[sig.index("(") + 1: sig.rindex(")")]
    return [t for t in inner.split(",") if t] if inner else []
def enc_one(t, v):
    if t == "address": return w(int(v, 16))
    if t == "bytes32": return bytes.fromhex(v[2:])
    if t == "bool": return w(1 if v else 0)
    return w(v)
def encode(types, vals):
    head_size = 32 * len(types); heads = b""; tails = b""
    for t, v in zip(types, vals):
        if t.endswith("[]"):
            heads += w(head_size + len(tails))
            tails += w(len(v)) + b"".join(enc_one(t[:-2], x) for x in v)
        else: heads += enc_one(t, v)
    return heads + tails
def call_data(contract, name, args):
    f = ABI[contract]["functions"][name]
    return "0x" + bytes.fromhex(f["selector"][2:]).hex() + encode(types_of(f["sig"]), args).hex()
def to_int(x): return x - M256 if x >= 1 << 255 else x
def decode(types, hexdata):
    b = bytes.fromhex(hexdata[2:] if hexdata.startswith("0x") else hexdata)
    ws = [int.from_bytes(b[i:i+32], "big") for i in range(0, len(b) - len(b) % 32, 32)]
    out = []; k = 0
    for t in types:
        if t.endswith("[]"):
            off = ws[k] // 32; k += 1; n = ws[off]; el = ws[off + 1: off + 1 + n]
            out.append([to_int(x) for x in el] if t.startswith("int") else el)
        else:
            x = ws[k]; k += 1
            out.append("0x" + x.to_bytes(32, "big")[12:].hex() if t == "address" else
                       "0x" + x.to_bytes(32, "big").hex() if t == "bytes32" else
                       to_int(x) if t.startswith("int") else x)
    return out
def event_types(contract, name, indexed=False):
    e = ABI[contract]["events"][name]
    return [t for t, ix in zip(types_of(e["sig"]), e["indexed"]) if ix == indexed]
