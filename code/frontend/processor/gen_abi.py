import re, json
from keccak import keccak256
SOL="/mnt/user-data/outputs/ssi-onchain/"
STRUCTS={"Context":"(int256,int256,int256,int256,int256,int256,int256,int256,int256,uint256)"}
ENUMS={"Decision","VerResult","AssetStatus","Domain","RoundStatus","Weight","JobStatus"}
def norm(t):
    t=t.strip()
    if t in ENUMS: return "uint8"
    return STRUCTS.get(t,t)
def parse(path, kind):
    src=open(SOL+path).read()
    out={}
    for m in re.finditer(r'\b'+kind+r'\s+(\w+)\s*\(([^)]*)\)', src, re.S):
        name,params=m.group(1),m.group(2)
        if kind=="function" and name.startswith("_"): continue
        types=[]
        for p in [x for x in params.split(",") if x.strip()]:
            words=[w for w in p.split() if w not in("calldata","memory","storage","indexed")]
            types.append(norm(words[0]))
        sig=f"{name}({','.join(types)})"
        out.setdefault(name,sig)
    return out
def indexed_flags(path, name):
    src=open(SOL+path).read()
    m=re.search(r'\bevent\s+'+name+r'\s*\(([^)]*)\)', src, re.S)
    return [("indexed" in p.split()) for p in m.group(1).split(",") if p.strip()]
res={}
for c,f in (("kernel","SSIVerificationKernel.sol"),("energy","HGBNSIEnergyR3.sol"),("router","HGBNSIJobRouter.sol")):
    fns=parse(f,"function"); errs=parse(f,"error"); evs=parse(f,"event")
    res[c]={"functions":{n:{"sig":s,"selector":"0x"+keccak256(s.encode())[:4].hex()} for n,s in fns.items()},
            "errors":{"0x"+keccak256(s.encode())[:4].hex():s for s in errs.values()},
            "events":{n:{"sig":s,"topic":"0x"+keccak256(s.encode()).hex(),"indexed":indexed_flags(f,n)} for n,s in evs.items()}}
# public state-variable getters (not declared as functions)
getters={"kernel":["owner()","pendingOwner()","safeStopped()","activeKernel()","currentEpoch()","ledgerHead()","ledgerLength()",
                   "axiomsSealed()","axiomRoot()","isVerifier(address)","freshnessWindow()","adoptionDelay()","decided(bytes32)","isAuthorized(bytes32)"],
         "energy":["kernel()","axiomsSealed()","registryHash()","ledgerHead()","ledgerLength()","roundCount()","lastAcceptedRound()",
                   "bestVerifiedCount()","axiomIds(uint256)"],
         "router":["kernel()","isProcessor(address)","jobCount()","ledgerHead()","ledgerLength()"]}
for c,gs in getters.items():
    for s in gs:
        res[c]["functions"][s.split("(")[0]]={"sig":s,"selector":"0x"+keccak256(s.encode())[:4].hex()}
# Solidity's built-in Error(string) / Panic(uint256)
for c in res:
    res[c]["errors"]["0x08c379a0"]="Error(string)"; res[c]["errors"]["0x4e487b71"]="Panic(uint256)"
json.dump(res,open("abi.json","w"),indent=1)
for c in res:
    print(c, len(res[c]["functions"]),"functions", len(res[c]["errors"]),"errors", len(res[c]["events"]),"events")
print(res["energy"]["functions"]["evaluate"]); print(res["kernel"]["events"]["LedgerAppended"])
print(res["kernel"]["functions"]["transitionAgent"]["sig"], res["energy"]["functions"]["registerAxiom"]["sig"])
