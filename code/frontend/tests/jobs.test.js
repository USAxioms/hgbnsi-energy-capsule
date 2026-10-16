const S = require("../core.js"), cs = require("./job_cases.json");
let pass = 0, fail = 0; const ok = (c, l) => { if (c) pass++; else { fail++; if (fail < 6) console.log("FAIL", l); } };
for (const c of cs) {
  const spec = c.spec.map(BigInt), plan = c.plan.map(BigInt);
  ok(S.validateSpec(spec) === c.valid_spec, "validateSpec " + c.spec.slice(0, 3));
  ok(S.packedHash(spec) === c.hash, "packed hash");
  if (c.check) {
    const r = S.checkPlan(spec, plan);
    ok(r.reason === c.check[0] && r.cost.toString() === c.check[1], "checkPlan " + r.reason + " vs " + c.check[0]);
    ok(S.encodeCall("router", "submitResult", [7, spec, plan]) === c.calldata, "calldata with two dynamic lists");
    const back = S.decodeData(["uint256", "int256[]", "int256[]"], "0x" + c.calldata.slice(10));
    ok(back[0] === 7n && back[1].join() === spec.join() && back[2].join() === plan.join(), "decode round trip");
  }
}
console.log(`jobs: passed ${pass}, failed ${fail} (${cs.length} random specs and plans vs the Python model and encoder)`);
process.exit(fail ? 1 : 0);
