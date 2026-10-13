#!/usr/bin/env python3
"""
Mock Ethereum JSON-RPC node for end-to-end tests. It implements the SSI kernel's role
getters and HGBNSIJobRouter's full logic (a transcription of the Solidity), with events
and custom-error refusals. Not a blockchain: no consensus, no signatures; accounts are
"unlocked" like a development node.
"""
import copy, hashlib, json, os, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "processor"))
sys.path.insert(0, os.path.dirname(__file__))
from abi_py import ABI, decode, encode, types_of, w
from router_model import check_plan, validate_spec, packed_hash

GUIDE = "0x" + "a1" * 20
VERIFIER = "0x" + "b2" * 20
PROCESSOR = "0x" + "d4" * 20
STRANGER = "0x" + "c3" * 20
KERNEL = "0x" + "11" * 20
ROUTER = "0x" + "22" * 20
ZERO32 = "0x" + "00" * 32

class Revert(Exception):
    def __init__(self, contract, sig, *args):
        sel = next(k for k, v in ABI[contract]["errors"].items() if v == sig)
        self.data = sel + encode(types_of(sig), list(args)).hex()

def b32(text): return text.encode().ljust(32, b"\0")

class Chain:
    def __init__(self):
        self.block = 1; self.logs = []; self.receipts = {}; self.ntx = 0
        self.safe_stopped = False; self.verifiers = {VERIFIER.lower()}
        self.processors = set(); self.jobs = {}; self.job_count = 0
        self.ledger_len = 0
        self.ledger_head = hashlib.sha256(b32("HGBNSI.JOBS.GENESIS") + w(31337) + bytes.fromhex(ROUTER[2:]) + bytes.fromhex(KERNEL[2:])).digest()

    # ---------- helpers
    def emit(self, name, *values):
        ev = ABI["router"]["events"][name]; ts = types_of(ev["sig"])
        topics = [ev["topic"]] + ["0x" + enc for enc in (encode([t], [v]).hex() for t, v, ix in zip(ts, values, ev["indexed"]) if ix)]
        data = encode([t for t, ix in zip(ts, ev["indexed"]) if not ix], [v for v, ix in zip(values, ev["indexed"]) if not ix])
        self.pending_logs.append({"address": ROUTER, "topics": topics, "data": "0x" + data.hex(),
                                  "blockNumber": hex(self.block), "logIndex": hex(len(self.pending_logs))})
    def append(self, tag, subject, data):
        e = hashlib.sha256(self.ledger_head + w(self.ledger_len) + b32(tag) + subject + data + w(self.block)).digest()
        self.ledger_head = e; self.ledger_len += 1
    def job(self, jid):
        if jid not in self.jobs: raise Revert("router", "UnknownJob(uint256)", jid)
        return self.jobs[jid]
    def guide(self, sender):
        if sender != GUIDE.lower(): raise Revert("router", "NotHumanGuide()")
    def running(self):
        if self.safe_stopped: raise Revert("router", "SafeStopped()")

    # ---------- router transactions (transcription of HGBNSIJobRouter.sol)
    def setProcessor(self, s, p, active):
        self.guide(s)
        if active and (p.lower() == GUIDE.lower() or p.lower() in self.verifiers): raise Revert("router", "RoleConflict(address)", p)
        (self.processors.add if active else self.processors.discard)(p.lower())
        self.emit("ProcessorSet", p, active)
    def submitJob(self, s, spec, weight, deadline):
        self.guide(s); self.running()
        code = validate_spec(spec)
        if code is not None: raise Revert("router", "BadSpec(uint8)", code)
        if deadline <= (time.time_ns() // 10**9): raise Revert("router", "BadDeadline()")
        self.job_count += 1; jid = self.job_count; h = "0x" + packed_hash(spec)
        self.jobs[jid] = dict(status=1, weight=weight, attempts=0, lastReason=0, deadline=deadline, requester=s,
                              solver="0x" + "00" * 20, specHash=h, planHash=ZERO32, cost=0, reportHash=ZERO32)
        self.emit("JobSubmitted", jid, h, weight, deadline, spec); self.append("HGBNSI.JOBS.SUBMIT", w(jid), bytes.fromhex(h[2:]))
    def permitJob(self, s, jid, approve, reason_hash):
        if s not in self.verifiers: raise Revert("router", "NotVerifier()")
        self.running(); j = self.job(jid)
        if j["status"] != 1: raise Revert("router", "WrongStatus(uint256,uint8)", jid, j["status"])
        if reason_hash == ZERO32: raise Revert("router", "ZeroValue()")
        if (time.time_ns() // 10**9) > j["deadline"]: raise Revert("router", "DeadlinePassed(uint256)", jid)
        j["status"] = 2 if approve else 3
        self.emit("JobPermitted", jid, s, approve, reason_hash)
        if approve and j["weight"] == 1: self.emit("ExecutionCommand", jid, j["specHash"])
    def submitResult(self, s, jid, spec, plan):
        self.running(); j = self.job(jid)
        if j["status"] != 2: raise Revert("router", "WrongStatus(uint256,uint8)", jid, j["status"])
        if (time.time_ns() // 10**9) > j["deadline"]: raise Revert("router", "DeadlinePassed(uint256)", jid)
        allowed = s == j["requester"] if j["weight"] == 0 else s in self.processors
        if not allowed: raise Revert("router", "NotSolver(uint256,address)", jid, s)
        if "0x" + packed_hash(spec) != j["specHash"]: raise Revert("router", "SpecMismatch(uint256)", jid)
        reason, cost = check_plan(spec, plan)
        j["attempts"] += 1; j["lastReason"] = reason
        if reason == 0:
            j.update(status=4, solver=s, planHash="0x" + packed_hash(plan), cost=cost)
            self.emit("ResultAccepted", jid, s, j["planHash"], cost, plan)
        else:
            if j["attempts"] >= 3: j["status"] = 5
            self.emit("ResultRejected", jid, s, reason, j["attempts"])
    def markExecuted(self, s, jid, report):
        self.running(); j = self.job(jid)
        if s != j["requester"]: raise Revert("router", "NotRequester(uint256)", jid)
        if j["status"] != 4: raise Revert("router", "WrongStatus(uint256,uint8)", jid, j["status"])
        if report == ZERO32: raise Revert("router", "ZeroValue()")
        j.update(status=6, reportHash=report); self.emit("JobExecuted", jid, report)

    # ---------- dispatch
    def execute(self, to, data, sender, commit):
        sel = data[:10]; args_hex = data[10:]
        contract = "kernel" if to.lower() == KERNEL.lower() else "router"
        f = next((n for n, x in ABI[contract]["functions"].items() if x["selector"] == sel), None)
        if f is None: raise RuntimeError("mock: unknown selector " + sel)
        args = decode(types_of(ABI[contract]["functions"][f]["sig"]), args_hex)
        R = lambda types, vals: "0x" + encode(types, vals).hex()
        if contract == "kernel":
            K = {"owner": lambda: R(["address"], [GUIDE]), "pendingOwner": lambda: R(["address"], ["0x" + "00" * 20]),
                 "safeStopped": lambda: R(["bool"], [self.safe_stopped]), "activeKernel": lambda: R(["bytes32"], ["0x" + "9e" * 32]),
                 "currentEpoch": lambda: R(["uint256"], [0]), "ledgerHead": lambda: R(["bytes32"], [ZERO32]),
                 "ledgerLength": lambda: R(["uint256"], [0]), "axiomsSealed": lambda: R(["bool"], [True]),
                 "axiomRoot": lambda: R(["bytes32"], [ZERO32]), "axiomCount": lambda: R(["uint256"], [0]),
                 "freshnessWindow": lambda: R(["uint256"], [3600]), "adoptionDelay": lambda: R(["uint256"], [172800]),
                 "isVerifier": lambda: R(["bool"], [args[0].lower() in self.verifiers]),
                 "getAgent": lambda: "0x" + "00" * 320}
            if f == "setSafeStop":
                engage = bool(args[0])
                if not (sender == GUIDE.lower() or (engage and sender in self.verifiers)):
                    raise Revert("kernel", "NotOwner()")
                if commit: self.safe_stopped = engage
                return "0x"
            return K[f]()
        if f in ("setProcessor", "submitJob", "permitJob", "submitResult", "markExecuted"):
            target = self if commit else copy.deepcopy(self)
            target.pending_logs = []
            getattr(target, f)(sender, *args)
            if commit: self.logs += target.pending_logs
            return "0x"
        j = lambda jid: self.jobs.get(jid)
        V = {"kernel": lambda: R(["address"], [KERNEL]), "jobCount": lambda: R(["uint256"], [self.job_count]),
             "isProcessor": lambda: R(["bool"], [args[0].lower() in self.processors]),
             "ledgerHead": lambda: R(["bytes32"], ["0x" + self.ledger_head.hex()]), "ledgerLength": lambda: R(["uint256"], [self.ledger_len]),
             "checkPlan": lambda: R(["uint8", "int256"], list(check_plan(args[0], args[1]))),
             "specHashOf": lambda: R(["bytes32"], ["0x" + packed_hash(args[0])]),
             "isExecutable": lambda: R(["bool"], [bool(j(args[0])) and j(args[0])["status"] == 4 and j(args[0])["planHash"] == args[1] and not self.safe_stopped]),
             "getJob": lambda: R(["uint8", "uint8", "uint8", "uint8", "uint64", "address", "address", "bytes32", "bytes32", "int256", "bytes32"],
                                 [x for x in (j(args[0]) or dict(status=0, weight=0, attempts=0, lastReason=0, deadline=0, requester="0x" + "00" * 20,
                                  solver="0x" + "00" * 20, specHash=ZERO32, planHash=ZERO32, cost=0, reportHash=ZERO32)).values()])}
        return V[f]()

    def rpc(self, method, params):
        if method == "eth_chainId": return "0x7a69"
        if method in ("eth_accounts", "eth_requestAccounts"): return [GUIDE, VERIFIER, PROCESSOR, STRANGER]
        if method == "eth_blockNumber": return hex(self.block)
        if method == "eth_getCode": return "0x6080" if params[0].lower() in (KERNEL.lower(), ROUTER.lower()) else "0x"
        if method == "eth_call":
            tx = params[0]; return self.execute(tx["to"], tx["data"], tx.get("from", "0x" + "00" * 20).lower(), False)
        if method == "eth_sendTransaction":
            tx = params[0]; self.block += 1
            self.execute(tx["to"], tx["data"], tx["from"].lower(), True)
            self.ntx += 1; h = "0x" + hashlib.sha256(str(self.ntx).encode()).hexdigest()
            self.receipts[h] = {"status": "0x1", "blockNumber": hex(self.block)}; return h
        if method == "eth_getTransactionReceipt": return self.receipts.get(params[0])
        if method == "eth_getLogs":
            q = params[0]; lo = int(q.get("fromBlock", "0x0"), 16); hi = self.block if q.get("toBlock", "latest") == "latest" else int(q["toBlock"], 16)
            out = []
            for lg in self.logs:
                if lg["address"].lower() != q["address"].lower() or not lo <= int(lg["blockNumber"], 16) <= hi: continue
                if all(t is None or (i < len(lg["topics"]) and lg["topics"][i].lower() == t.lower()) for i, t in enumerate(q.get("topics", []))):
                    out.append(lg)
            return out
        raise RuntimeError("mock: unsupported " + method)

CHAIN = Chain()

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "Content-Type")
    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        try: res = {"jsonrpc": "2.0", "id": req["id"], "result": CHAIN.rpc(req["method"], req.get("params", []))}
        except Revert as r: res = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": 3, "message": "execution reverted", "data": r.data}}
        except Exception as e: res = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32000, "message": str(e)}}
        body = json.dumps(res).encode()
        self.send_response(200); self._cors(); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8545
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
