/*
 * Sovereign Axiomatic Front End — core (no dependencies, no network except the
 * Ethereum endpoint the human guide chooses). Runs in a browser or in Node for tests.
 * Human-Guided Blockchain-Native Safe Superintelligence (HGBNSI).
 */
(function (root) {
  "use strict";

  /* Function selectors, custom errors and event topics, generated from the
     contract sources with a verified Keccak-256 (see build/gen_abi.py). */
  const ABI = __ABI__;

  /* ------------------------------------------------------------ bytes */
  const enc = new TextEncoder();
  const dec = new TextDecoder();

  function hexToBytes(hex) {
    let h = String(hex);
    if (h.startsWith("0x") || h.startsWith("0X")) h = h.slice(2);
    if (h.length % 2 !== 0 || /[^0-9a-fA-F]/.test(h)) throw new Error("Not valid hexadecimal: " + hex);
    const out = new Uint8Array(h.length / 2);
    for (let i = 0; i < out.length; i++) out[i] = parseInt(h.substr(2 * i, 2), 16);
    return out;
  }

  function bytesToHex(b) {
    let s = "0x";
    for (const x of b) s += x.toString(16).padStart(2, "0");
    return s;
  }

  function concat(...parts) {
    const n = parts.reduce((a, p) => a + p.length, 0);
    const out = new Uint8Array(n);
    let k = 0;
    for (const p of parts) { out.set(p, k); k += p.length; }
    return out;
  }

  /* ------------------------------------------------------------ SHA-256 (FIPS 180-4) */
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);

  function sha256(data) {
    const msg = typeof data === "string" ? enc.encode(data) : data;
    const bitLen = msg.length * 8;
    const padLen = (msg.length + 9 + 63) & ~63;
    const p = new Uint8Array(padLen);
    p.set(msg);
    p[msg.length] = 0x80;
    const view = new DataView(p.buffer);
    view.setUint32(padLen - 8, Math.floor(bitLen / 0x100000000));
    view.setUint32(padLen - 4, bitLen >>> 0);
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const W = new Uint32Array(64);
    const r = (x, n) => (x >>> n) | (x << (32 - n));
    for (let o = 0; o < padLen; o += 64) {
      for (let i = 0; i < 16; i++) W[i] = view.getUint32(o + 4 * i);
      for (let i = 16; i < 64; i++) {
        const s0 = r(W[i - 15], 7) ^ r(W[i - 15], 18) ^ (W[i - 15] >>> 3);
        const s1 = r(W[i - 2], 17) ^ r(W[i - 2], 19) ^ (W[i - 2] >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const S1 = r(e, 6) ^ r(e, 11) ^ r(e, 25);
        const t1 = (h + S1 + ((e & f) ^ (~e & g)) + K[i] + W[i]) >>> 0;
        const S0 = r(a, 2) ^ r(a, 13) ^ r(a, 22);
        const t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    const out = new Uint8Array(32);
    const ov = new DataView(out.buffer);
    for (let i = 0; i < 8; i++) ov.setUint32(4 * i, H[i]);
    return out;
  }

  const sha256Hex = (data) => bytesToHex(sha256(data));

  /* ------------------------------------------------------------ WAD-18 */
  const WAD = 10n ** 18n;
  const WAD_MAX = (1n << 127n) - 1n;
  const WAD_MIN = -WAD_MAX;

  /** Exact decimal → WAD-18 integer. Same literal rules as wad_parse in the C kernel. */
  function parseWad(text) {
    const s = String(text).trim();
    const m = /^([+-])?(\d+)(?:\.(\d+))?$/.exec(s);
    if (!m) throw new Error("Enter a plain decimal number, such as 1000.25");
    if (m[3] && m[3].length > 18) throw new Error("More than 18 decimal places can't be represented exactly");
    let v = BigInt(m[2]) * WAD + BigInt((m[3] || "").padEnd(18, "0") || "0");
    if (m[1] === "-") v = -v;
    if (v > WAD_MAX || v < WAD_MIN) throw new Error("Outside the WAD-18 range");
    return v;
  }

  function formatWad(v) {
    const neg = v < 0n;
    const a = neg ? -v : v;
    const whole = a / WAD;
    let frac = (a % WAD).toString().padStart(18, "0").replace(/0+$/, "");
    return (neg ? "-" : "") + whole.toString() + (frac ? "." + frac : "");
  }

  /* ------------------------------------------------------------ ABI (static types) */
  const TWO256 = 1n << 256n;

  function word(n) {
    const out = new Uint8Array(32);
    let x = n;
    for (let i = 31; i >= 0; i--) { out[i] = Number(x & 0xffn); x >>= 8n; }
    return out;
  }

  function splitTypes(s) {
    const out = [];
    let depth = 0, cur = "";
    for (const ch of s) {
      if (ch === "(") depth++;
      if (ch === ")") depth--;
      if (ch === "," && depth === 0) { out.push(cur); cur = ""; } else cur += ch;
    }
    if (cur) out.push(cur);
    return out;
  }

  function sigTypes(sig) {
    const inner = sig.slice(sig.indexOf("(") + 1, sig.lastIndexOf(")"));
    return inner ? splitTypes(inner) : [];
  }

  function isAddress(a) {
    return /^0x[0-9a-fA-F]{40}$/.test(String(a));
  }

  function encodeValue(type, v) {
    if (type.startsWith("(")) {
      const ts = splitTypes(type.slice(1, -1));
      if (!Array.isArray(v) || v.length !== ts.length) throw new Error("Tuple needs " + ts.length + " values");
      return concat(...ts.map((t, i) => encodeValue(t, v[i])));
    }
    if (type === "bool") return word(v ? 1n : 0n);
    if (type === "address") {
      if (!isAddress(v)) throw new Error("Not an Ethereum address: " + v);
      return word(BigInt(v));
    }
    if (type === "bytes32") {
      if (!/^0x[0-9a-fA-F]{64}$/.test(String(v))) throw new Error("Not a 32-byte value: " + v);
      return hexToBytes(v);
    }
    const m = /^(u?)int(\d+)$/.exec(type);
    if (!m) throw new Error("Unsupported type " + type);
    const bits = BigInt(m[2]);
    const n = BigInt(v);
    if (m[1] === "u") {
      if (n < 0n || n >= (1n << bits)) throw new Error(type + " out of range: " + n);
      return word(n);
    }
    const lim = 1n << (bits - 1n);
    if (n < -lim || n >= lim) throw new Error(type + " out of range: " + n);
    return word(n < 0n ? TWO256 + n : n);
  }

  function fn(contract, name) {
    const f = ABI[contract] && ABI[contract].functions[name];
    if (!f) throw new Error("Unknown function " + contract + "." + name);
    return f;
  }

  const isDynamic = (t) => t.endsWith("[]");
  function staticSize(t) {
    return t.startsWith("(") ? splitTypes(t.slice(1, -1)).reduce((n, x) => n + staticSize(x), 0) : 32;
  }

  /** ABI head/tail encoding; supports static types, static tuples and arrays of static elements. */
  function encodeArgs(types, values) {
    const headSize = types.reduce((n, t) => n + (isDynamic(t) ? 32 : staticSize(t)), 0);
    const heads = [], tails = [];
    let tailLen = 0;
    types.forEach((t, i) => {
      if (isDynamic(t)) {
        const el = t.slice(0, -2);
        const arr = values[i];
        if (!Array.isArray(arr)) throw new Error(t + " needs a list");
        heads.push(word(BigInt(headSize + tailLen)));
        const tail = concat(word(BigInt(arr.length)), ...arr.map((v) => encodeValue(el, v)));
        tails.push(tail);
        tailLen += tail.length;
      } else heads.push(encodeValue(t, values[i]));
    });
    return concat(...heads, ...tails);
  }

  function encodeCall(contract, name, args) {
    const f = fn(contract, name);
    const types = sigTypes(f.sig);
    const a = args || [];
    if (types.length !== a.length) throw new Error(f.sig + " needs " + types.length + " arguments");
    return bytesToHex(concat(hexToBytes(f.selector), encodeArgs(types, a)));
  }

  /** Decodes ABI data (return values or non-indexed event fields) into BigInts and lists. */
  function decodeData(types, hex) {
    const ws = words(hex);
    let k = 0;
    return types.map((t) => {
      if (isDynamic(t)) {
        const off = Number(ws[k++]) / 32;
        const len = Number(ws[off]);
        const el = ws.slice(off + 1, off + 1 + len);
        return t.startsWith("int") ? el.map(asInt) : el;
      }
      const w = ws[k++];
      if (t === "address") return asAddress(w);
      if (t === "bytes32") return asBytes32(w);
      if (t === "bool") return asBool(w);
      return t.startsWith("int") ? asInt(w) : w;
    });
  }

  function words(hex) {
    const b = hexToBytes(hex || "0x");
    const out = [];
    for (let i = 0; i + 32 <= b.length; i += 32) {
      let n = 0n;
      for (let j = 0; j < 32; j++) n = (n << 8n) | BigInt(b[i + j]);
      out.push(n);
    }
    return out;
  }

  const asBool = (w) => w !== 0n;
  const asAddress = (w) => "0x" + w.toString(16).padStart(40, "0").slice(-40);
  const asBytes32 = (w) => "0x" + w.toString(16).padStart(64, "0");
  const asInt = (w) => (w >= 1n << 255n ? w - TWO256 : w);

  /* ------------------------------------------------------------ revert decoding */
  function extractRevertData(err) {
    const seen = new Set();
    const stack = [err];
    while (stack.length) {
      const x = stack.pop();
      if (!x || seen.has(x)) continue;
      seen.add(x);
      if (typeof x === "string") {
        const m = /0x[0-9a-fA-F]{8,}/.exec(x);
        if (m && m[0].length % 2 === 0) return m[0];
        continue;
      }
      if (typeof x === "object") {
        for (const k of ["data", "error", "info", "cause", "originalError"]) if (k in x) stack.push(x[k]);
        if (typeof x.message === "string") stack.push(x.message);
      }
    }
    return null;
  }

  function decodeRevert(data) {
    if (!data || data.length < 10) return "The contract refused without a reason code.";
    const sel = data.slice(0, 10).toLowerCase();
    const sig = ABI.kernel.errors[sel] || ABI.energy.errors[sel] || (ABI.router && ABI.router.errors[sel]);
    if (!sig) return "The contract refused (unrecognized code " + sel + ").";
    if (sig === "Error(string)") {
      const w = hexToBytes(data.slice(10));
      const len = Number(words(bytesToHex(w.slice(32, 64)))[0]);
      return dec.decode(w.slice(64, 64 + len));
    }
    const types = sigTypes(sig);
    const ws = words("0x" + data.slice(10));
    const vals = types.map((t, i) => {
      const w = ws[i];
      if (w === undefined) return "?";
      if (t === "address") return asAddress(w);
      if (t === "bytes32") return asBytes32(w);
      if (t.startsWith("int")) return asInt(w).toString();
      return w.toString();
    });
    return sig.slice(0, sig.indexOf("(")) + (vals.length ? "(" + vals.join(", ") + ")" : "");
  }

  /* ------------------------------------------------------------ text helpers */
  /** Short label → bytes32, left-aligned like a Solidity string literal. */
  function textToBytes32(s) {
    const b = enc.encode(String(s));
    if (b.length === 0 || b.length > 32) throw new Error("Use 1–32 characters");
    const out = new Uint8Array(32);
    out.set(b);
    return bytesToHex(out);
  }

  function bytes32ToText(h) {
    const b = hexToBytes(h);
    let end = b.length;
    while (end > 0 && b[end - 1] === 0) end--;
    const t = b.slice(0, end);
    return t.every((x) => x >= 32 && x < 127) ? dec.decode(t) : h;
  }

  /* ------------------------------------------------------------ provider */
  /**
   * mode "wallet": the wallet injected into this browser signs every transaction.
   * mode "node":   a JSON-RPC endpoint the human guide runs, e.g. http://127.0.0.1:8545.
   */
  function makeProvider(mode, url) {
    if (mode === "wallet") {
      const eth = root.ethereum;
      if (!eth) throw new Error("No wallet found in this browser.");
      return { mode, request: (method, params) => eth.request({ method, params: params || [] }) };
    }
    let id = 0;
    return {
      mode,
      request: async (method, params) => {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: ++id, method, params: params || [] }),
        });
        const j = await res.json();
        if (j.error) {
          const e = new Error(j.error.message);
          e.data = j.error.data;
          throw e;
        }
        return j.result;
      },
    };
  }

  function isLocalUrl(u) {
    try {
      const h = new URL(u).hostname;
      return h === "127.0.0.1" || h === "localhost" || h === "[::1]" || /^10\.|^192\.168\.|^172\.(1[6-9]|2\d|3[01])\./.test(h);
    } catch (_) {
      return false;
    }
  }

  /* ------------------------------------------------------------ contract client */
  function makeClient(provider, addresses) {
    async function call(contract, name, args, from) {
      const tx = { to: addresses[contract], data: encodeCall(contract, name, args) };
      if (from) tx.from = from;
      return words(await provider.request("eth_call", [tx, "latest"]));
    }

    /** Dry run: returns { ok: true } or { ok: false, reason }. */
    async function simulate(contract, name, args, from) {
      try {
        await call(contract, name, args, from);
        return { ok: true };
      } catch (e) {
        return { ok: false, reason: decodeRevert(extractRevertData(e)) };
      }
    }

    async function send(contract, name, args, from) {
      return provider.request("eth_sendTransaction", [{ from, to: addresses[contract], data: encodeCall(contract, name, args) }]);
    }

    async function receipt(hash) {
      for (let i = 0; i < 120; i++) {
        const r = await provider.request("eth_getTransactionReceipt", [hash]);
        if (r) return r;
        await new Promise((ok) => setTimeout(ok, 1500));
      }
      throw new Error("No receipt after three minutes; check the transaction in your wallet.");
    }

    return { call, simulate, send, receipt, addresses, provider };
  }

  /* ------------------------------------------------------------ state readers */
  async function readKernel(c, account) {
    const one = async (n, a) => (await c.call("kernel", n, a || []))[0];
    const s = {
      owner: asAddress(await one("owner")),
      pendingOwner: asAddress(await one("pendingOwner")),
      safeStopped: asBool(await one("safeStopped")),
      activeKernel: asBytes32(await one("activeKernel")),
      currentEpoch: await one("currentEpoch"),
      ledgerHead: asBytes32(await one("ledgerHead")),
      ledgerLength: await one("ledgerLength"),
      axiomsSealed: asBool(await one("axiomsSealed")),
      axiomRoot: asBytes32(await one("axiomRoot")),
      axiomCount: await one("axiomCount"),
      freshnessWindow: await one("freshnessWindow"),
      adoptionDelay: await one("adoptionDelay"),
    };
    if (account) {
      s.accountIsVerifier = asBool(await one("isVerifier", [account]));
      s.accountAgent = decodeAgent(await c.call("kernel", "getAgent", [account]));
    }
    return s;
  }

  const STATUS = ["Proposed", "Verified", "Active", "Revalidation", "Revoked", "Rejected"];
  function decodeAgent(w) {
    return {
      registered: asBool(w[0]), revoked: asBool(w[1]), status: Number(w[2]), statusName: STATUS[Number(w[2])],
      allowedKinds: Number(w[3]), authorizedCaps: Number(w[4]), issuedAt: w[5], validUntil: w[6],
      revocationEpoch: w[7], deploymentId: asBytes32(w[8]), certificateHash: asBytes32(w[9]),
    };
  }

  const ROUND = ["None", "Full", "Partial", "Fallback", "Ratified"];
  function decodeRound(w) {
    return {
      status: Number(w[0]), statusName: ROUND[Number(w[0])], verifiedCount: Number(w[1]), total: Number(w[2]),
      timestamp: w[3], verifier: asAddress(w[4]), verifiedMask: w[5], contextHash: asBytes32(w[6]),
      evidenceHash: asBytes32(w[7]), record: asBytes32(w[8]),
    };
  }

  function decodeAxiom(w) {
    return {
      exists: asBool(w[0]), domain: Number(w[1]), grounding: Number(w[2]), contentHash: asBytes32(w[3]),
      conditionMask: w[4], chargeWad: asInt(w[5]),
    };
  }

  async function readEnergy(c, maxRounds) {
    const one = async (n, a) => (await c.call("energy", n, a || []))[0];
    const s = {
      kernel: asAddress(await one("kernel")),
      axiomsSealed: asBool(await one("axiomsSealed")),
      registryHash: asBytes32(await one("registryHash")),
      ledgerHead: asBytes32(await one("ledgerHead")),
      ledgerLength: await one("ledgerLength"),
      roundCount: await one("roundCount"),
      lastAcceptedRound: await one("lastAcceptedRound"),
      bestVerifiedCount: await one("bestVerifiedCount"),
      triadCovered: asBool(await one("triadCovered")),
      axioms: [],
      rounds: [],
    };
    const n = Number(await one("axiomCount"));
    for (let i = 0; i < n; i++) {
      const id = asBytes32(await one("axiomIds", [i]));
      s.axioms.push({ id, label: bytes32ToText(id), ...decodeAxiom(await c.call("energy", "getAxiom", [id])) });
    }
    const total = Number(s.roundCount);
    const from = Math.max(1, total - (maxRounds || 50) + 1);
    for (let r = total; r >= from; r--) {
      s.rounds.push({ id: r, ...decodeRound(await c.call("energy", "getRound", [r])) });
    }
    return s;
  }

  /* ------------------------------------------------------------ ledger verification */
  const TAGS = {
    kernelGenesis: textToBytes32("SSI.GENESIS"),
    energyGenesis: textToBytes32("HGBNSI.ENERGY.GENESIS"),
  };

  function genesis(kind, chainId, address, kernelAddress) {
    const parts = [hexToBytes(kind === "kernel" ? TAGS.kernelGenesis : TAGS.energyGenesis), word(BigInt(chainId)), hexToBytes(address)];
    if (kind === "energy") parts.push(hexToBytes(kernelAddress));
    return sha256Hex(concat(...parts));
  }

  function ledgerEntry(prev, seq, tag, subject, data, blockNumber) {
    return sha256Hex(concat(hexToBytes(prev), word(BigInt(seq)), hexToBytes(tag), hexToBytes(subject), hexToBytes(data), word(BigInt(blockNumber))));
  }

  /**
   * Recomputes a ledger from its LedgerAppended logs, starting at genesis.
   * Returns { ok, entries, head, problem }.
   */
  function verifyLedgerLogs(genesisHash, logs, expectedHead, expectedLength) {
    const sorted = logs.slice().sort((a, b) => {
      const d = BigInt(a.blockNumber) - BigInt(b.blockNumber);
      return d !== 0n ? (d < 0n ? -1 : 1) : Number(BigInt(a.logIndex) - BigInt(b.logIndex));
    });
    let head = genesisHash;
    let seq = 0n;
    for (const log of sorted) {
      const s = BigInt(log.topics[1]);
      if (s !== seq) return { ok: false, entries: Number(seq), head, problem: "Entry " + seq + " is missing or out of order." };
      const d = hexToBytes(log.data);
      const subject = bytesToHex(d.slice(0, 32));
      const data = bytesToHex(d.slice(32, 64));
      const e = ledgerEntry(head, seq, log.topics[3], subject, data, log.blockNumber);
      if (e.toLowerCase() !== String(log.topics[2]).toLowerCase()) {
        return { ok: false, entries: Number(seq), head, problem: "Entry " + seq + " does not match its recomputed hash." };
      }
      head = e;
      seq += 1n;
    }
    if (expectedLength !== undefined && seq !== BigInt(expectedLength)) {
      return { ok: false, entries: Number(seq), head, problem: "Found " + seq + " entries; the contract reports " + expectedLength + "." };
    }
    if (expectedHead && head.toLowerCase() !== expectedHead.toLowerCase()) {
      return { ok: false, entries: Number(seq), head, problem: "The recomputed head differs from the contract's head." };
    }
    return { ok: true, entries: Number(seq), head, problem: null };
  }

  async function verifyLedger(c, kind, fromBlock, expected) {
    const chainId = await c.provider.request("eth_chainId", []);
    const address = c.addresses[kind];
    const kernelAddress = kind === "energy" ? asAddress((await c.call("energy", "kernel"))[0]) : null;
    const g = genesis(kind, chainId, address, kernelAddress);
    const topic = ABI[kind].events.LedgerAppended.topic;
    const logs = await c.provider.request("eth_getLogs", [
      { address, topics: [topic], fromBlock: "0x" + BigInt(fromBlock || 0).toString(16), toBlock: "latest" },
    ]);
    return verifyLedgerLogs(g, logs, expected.head, expected.length);
  }

  /* ------------------------------------------------------------ energy axioms */
  const DOMAINS = ["Thermodynamics", "Economics", "Ethics", "Operations", "Generic"];
  const GROUND = { EV: 1, EE: 2, ET: 4 };
  const FAIRNESS_TOLERANCE = WAD;

  /** Same checks as HGBNSIEnergyR3._holds, on WAD-18 BigInts. */
  function axiomHolds(domain, conditionMask, c) {
    switch (domain) {
      case 0: return c.energyIn === c.energyOut + c.energyStored;
      case 1: return c.valueCreated >= c.valueDestroyed;
      case 2: {
        let d = c.benefitA - c.benefitB;
        if (d < 0n) d = -d;
        return d <= FAIRNESS_TOLERANCE;
      }
      case 3:
        if (c.systemTotal <= 0n || c.systemUp < 0n || c.systemUp > c.systemTotal) return false;
        return c.systemUp * 100n >= c.systemTotal * 95n;
      default: return (c.conditions & conditionMask) === conditionMask;
    }
  }

  function evaluateLocal(axioms, c) {
    let mask = 0n, count = 0;
    axioms.forEach((a, i) => {
      if (axiomHolds(a.domain, BigInt(a.conditionMask || 0), c)) { mask |= 1n << BigInt(i); count++; }
    });
    const total = axioms.length;
    const status = total === 0 ? "None" : count === total ? "Full" : count * 2 >= total ? "Partial" : "Fallback";
    return { mask, count, total, status };
  }

  const CONTEXT_FIELDS = ["energyIn", "energyOut", "energyStored", "valueCreated", "valueDestroyed", "benefitA", "benefitB", "systemUp", "systemTotal"];
  const contextTuple = (c) => [...CONTEXT_FIELDS.map((k) => c[k]), c.conditions];

  function groundingCount(g) {
    return (g & 1) + ((g >> 1) & 1) + ((g >> 2) & 1);
  }

  /** The seven axioms of ENERGY_R3.py. contentHash = SHA-256(name + "\n" + statement). */
  const ENERGY_PRESETS = [
    ["AX_001", "Energy Conservation", "Energy cannot be created or destroyed, only transformed", 0, GROUND.EV | GROUND.EE, "9.8"],
    ["AX_002", "Thermodynamic Inefficiency", "Every energy transformation has unavoidable losses", 0, GROUND.EV, "9.5"],
    ["AX_003", "Value of Energy", "Energy has intrinsic value for human flourishing and economic activity", 1, GROUND.EV | GROUND.ET, "9.0"],
    ["AX_004", "Energy Markets", "Energy exchange requires defined markets with transparent pricing", 1, GROUND.EE | GROUND.ET, "8.8"],
    ["AX_005", "Environmental Justice", "Energy production and consumption must not disproportionately harm vulnerable communities", 2, GROUND.EV | GROUND.ET, "9.2"],
    ["AX_006", "Grid Reliability", "Energy systems must maintain reliable supply to support human needs", 3, GROUND.EV | GROUND.EE | GROUND.ET, "9.5"],
    ["AX_007", "Regulatory Oversight", "Energy systems require transparent regulation to maintain trust and safety", 3, GROUND.ET, "8.5"],
  ].map(([id, name, statement, domain, grounding, charge]) => ({
    id, name, statement, domain, grounding, charge,
    idBytes: textToBytes32(id),
    contentHash: sha256Hex(name + "\n" + statement),
    registrable: groundingCount(grounding) >= 2,
  }));

  /** The sample context in ENERGY_R3.py's start-up code. */
  const SAMPLE_CONTEXT = {
    energyIn: "100", energyOut: "85", energyStored: "15", valueCreated: "100", valueDestroyed: "90",
    benefitA: "50", benefitB: "48", systemUp: "950", systemTotal: "1000",
  };

  const KINDS = ["Read", "Compute", "Communicate", "Write", "Purchase", "Deploy", "Credential", "Physical", "Self-modify", "Policy change"];

  /* ------------------------------------------------------------ jobs (HGBNSIJobRouter) */
  const JOB_STATUS = ["None", "Requested", "Permitted", "Denied", "Completed", "Failed", "Executed"];
  const WEIGHTS = ["Light", "Heavy"];
  const PLAN_REASONS = ["valid", "wrong number of outputs", "an output is out of range", "a generator runs below its minimum",
    "a generator runs above capacity", "a cost isn't exact at 18 decimals", "outputs don't sum exactly to demand", "cost is above the ceiling"];

  /** spec = [demand, ceiling, n, then capacity, minimum, marginal cost, fixed cost per generator]. */
  function buildSpec(demand, ceiling, generators) {
    const spec = [parseWad(demand), parseWad(ceiling), BigInt(generators.length)];
    generators.forEach((g, i) => {
      for (const [k, label] of [["capacity", "capacity"], ["minimum", "minimum output"], ["marginal", "marginal cost"], ["fixed", "fixed cost"]]) {
        try { spec.push(parseWad(g[k])); } catch (err) { throw new Error("Generator " + (i + 1) + " " + label + ": " + err.message); }
      }
    });
    return spec;
  }

  const packedHash = (arr) => sha256Hex(concat(...arr.map((v) => encodeValue("int256", v))));

  /** Same as HGBNSIJobRouter._validateSpec: null if valid, else the BadSpec code. */
  function validateSpec(s) {
    if (s.length < 7) return 1;
    if (s[2] < 1n || s[2] > 32n) return 2;
    const n = Number(s[2]);
    if (s.length !== 3 + 4 * n) return 3;
    if (s[0] <= 0n || s[0] > WAD_MAX) return 4;
    if (s[1] < 0n || s[1] > WAD_MAX) return 5;
    for (let i = 0; i < n; i++) {
      const b = 3 + 4 * i;
      for (let k = 0; k < 4; k++) if (s[b + k] < 0n || s[b + k] > WAD_MAX) return 6;
      if (s[b] === 0n || s[b + 1] > s[b]) return 7;
    }
    return null;
  }

  /** Same as HGBNSIJobRouter.checkPlan: { reason, cost }; reason 0 = valid. */
  function checkPlan(spec, plan) {
    const n = Number(spec[2]);
    if (plan.length !== n) return { reason: 1, cost: 0n };
    let total = 0n, cost = 0n;
    for (let i = 0; i < n; i++) {
      const p = plan[i];
      if (p < 0n || p > WAD_MAX) return { reason: 2, cost: 0n };
      if (p === 0n) continue;
      const b = 3 + 4 * i;
      if (p < spec[b + 1]) return { reason: 3, cost: 0n };
      if (p > spec[b]) return { reason: 4, cost: 0n };
      const product = spec[b + 2] * p;
      if (product % WAD !== 0n) return { reason: 5, cost: 0n };
      total += p;
      cost += spec[b + 3] + product / WAD;
    }
    if (total !== spec[0]) return { reason: 6, cost: 0n };
    if (cost > spec[1]) return { reason: 7, cost };
    return { reason: 0, cost };
  }

  /** Exactly optimal when no generator has a minimum or a fixed cost (light jobs). */
  function meritOrder(spec) {
    const n = Number(spec[2]);
    const idx = [...Array(n).keys()].sort((a, b) => {
      const d = spec[3 + 4 * a + 2] - spec[3 + 4 * b + 2];
      return d < 0n ? -1 : d > 0n ? 1 : a - b;
    });
    const plan = Array(n).fill(0n);
    let rest = spec[0];
    for (const i of idx) {
      const take = spec[3 + 4 * i] < rest ? spec[3 + 4 * i] : rest;
      plan[i] = take;
      rest -= take;
    }
    return rest === 0n ? plan : null;
  }

  /** Light jobs are solved exactly on the front end; heavy ones go to a processor. */
  function classify(spec) {
    const n = Number(spec[2]);
    let mins = 0, fixed = 0, cap = 0n;
    for (let i = 0; i < n; i++) {
      if (spec[4 + 4 * i] > 0n) mins++;
      if (spec[6 + 4 * i] > 0n) fixed++;
      cap += spec[3 + 4 * i];
    }
    const feasibleCapacity = cap >= spec[0];
    if (mins || fixed) {
      return { weight: 1, feasibleCapacity, why: "Heavy: " + [mins && mins + " generator(s) with a minimum output", fixed && fixed + " with a fixed cost"].filter(Boolean).join(" and ") + " make this an on/off search." };
    }
    if (n > 12) return { weight: 1, feasibleCapacity, why: "Heavy: more than 12 generators." };
    return { weight: 0, feasibleCapacity, why: "Light: no minimums or fixed costs, so this front end solves it exactly." };
  }

  function decodeJob(w) {
    return {
      status: Number(w[0]), statusName: JOB_STATUS[Number(w[0])], weight: Number(w[1]), weightName: WEIGHTS[Number(w[1])],
      attempts: Number(w[2]), lastReason: Number(w[3]), deadline: w[4], requester: asAddress(w[5]), solver: asAddress(w[6]),
      specHash: asBytes32(w[7]), planHash: asBytes32(w[8]), cost: asInt(w[9]), reportHash: asBytes32(w[10]),
    };
  }

  async function readJobs(c, max) {
    const total = Number((await c.call("router", "jobCount"))[0]);
    const out = [];
    for (let id = total; id >= Math.max(1, total - (max || 25) + 1); id--) {
      out.push({ id, ...decodeJob(await c.call("router", "getJob", [id])) });
    }
    return out;
  }

  /** Reads one of the router's events for a job and decodes its non-indexed fields. */
  async function jobEvent(c, name, jobId, fromBlock) {
    const ev = ABI.router.events[name];
    const logs = await c.provider.request("eth_getLogs", [{
      address: c.addresses.router, topics: [ev.topic, asBytes32(BigInt(jobId))],
      fromBlock: "0x" + BigInt(fromBlock || 0).toString(16), toBlock: "latest",
    }]);
    if (!logs.length) return null;
    const types = sigTypes(ev.sig).filter((_, i) => !ev.indexed[i]);
    const log = logs[logs.length - 1];
    return { values: decodeData(types, log.data), topics: log.topics, blockNumber: log.blockNumber };
  }

  /* ------------------------------------------------------------ self-test */
  function selfTest() {
    const t = [
      sha256Hex("") === "0xe3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      sha256Hex("abc") === "0xba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      parseWad("0.1") + parseWad("0.2") === parseWad("0.3"),
      formatWad(parseWad("-1000.10")) === "-1000.1",
      encodeCall("kernel", "setSafeStop", [true]) === fn("kernel", "setSafeStop").selector + "0".repeat(63) + "1",
    ];
    return t.every(Boolean);
  }

  const api = {
    ABI, hexToBytes, bytesToHex, concat, sha256, sha256Hex, WAD, WAD_MAX, WAD_MIN, parseWad, formatWad,
    encodeCall, encodeValue, words, asBool, asAddress, asBytes32, asInt, extractRevertData, decodeRevert,
    textToBytes32, bytes32ToText, makeProvider, isLocalUrl, isAddress, makeClient, readKernel, readEnergy,
    decodeAgent, decodeRound, decodeAxiom, genesis, ledgerEntry, verifyLedgerLogs, verifyLedger,
    DOMAINS, GROUND, axiomHolds, evaluateLocal, CONTEXT_FIELDS, contextTuple, groundingCount,
    ENERGY_PRESETS, SAMPLE_CONTEXT, KINDS, STATUS, ROUND, selfTest, encodeArgs, decodeData,
    JOB_STATUS, WEIGHTS, PLAN_REASONS, buildSpec, packedHash, validateSpec, checkPlan, meritOrder, classify,
    decodeJob, readJobs, jobEvent,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SAF = api;
})(typeof window !== "undefined" ? window : globalThis);
