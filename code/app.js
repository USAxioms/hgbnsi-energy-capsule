/*
 * Sovereign Axiomatic Front End — the human guide's console.
 * Nothing is sent without a review: plain-language effect, every precondition,
 * and a dry run on the chain. Uses Vue 3 from ./vendor and SAF from ./core.js.
 */
(function () {
  "use strict";
  const S = window.SAF;
  const { createApp } = window.Vue;
  const ZERO = "0x0000000000000000000000000000000000000000";
  const EMPTY32 = "0x" + "0".repeat(64);

  const CONTEXT_LABELS = {
    energyIn: "Energy in", energyOut: "Energy out", energyStored: "Energy stored",
    valueCreated: "Value created", valueDestroyed: "Value destroyed",
    benefitA: "Benefit to group A", benefitB: "Benefit to group B",
    systemUp: "System up (time)", systemTotal: "System total (time)",
  };

  const JOB_PRESETS = {
    heavy: { demand: "620", ceiling: "30000", minutes: "60", gens: [
      { name: "Hydro", capacity: "200", minimum: "40", marginal: "12.5", fixed: "300" },
      { name: "Wind farm", capacity: "150", minimum: "0", marginal: "2", fixed: "0" },
      { name: "Gas peaker", capacity: "120", minimum: "30", marginal: "68", fixed: "450" },
      { name: "Coal unit", capacity: "250", minimum: "100", marginal: "31.25", fixed: "900" },
      { name: "Solar array", capacity: "80", minimum: "0", marginal: "1.5", fixed: "0" },
      { name: "Battery", capacity: "60", minimum: "10", marginal: "45", fixed: "50" }] },
    light: { demand: "300", ceiling: "10000", minutes: "60", gens: [
      { name: "Hydro", capacity: "200", minimum: "0", marginal: "12.5", fixed: "0" },
      { name: "Wind farm", capacity: "150", minimum: "0", marginal: "2", fixed: "0" },
      { name: "Solar array", capacity: "80", minimum: "0", marginal: "1.5", fixed: "0" },
      { name: "Gas peaker", capacity: "120", minimum: "0", marginal: "68", fixed: "0" }] },
  };
  const copyPreset = (k) => JSON.parse(JSON.stringify(JOB_PRESETS[k]));

  const app = createApp({
    data() {
      return {
        conn: { mode: "wallet", url: "http://127.0.0.1:8545", kernel: "", energy: "", router: "", fromBlock: "0" },
        connected: false,
        connectError: "",
        selfTestOk: S.selfTest(),
        busy: false,
        client: null,
        chainId: "",
        accounts: [],
        account: "",
        k: {},
        e: null,
        rationale: {},
        ctx: { ...S.SAMPLE_CONTEXT },
        dry: { local: null, rows: [], chain: null, agree: false, error: "" },
        ledger: [],
        journal: [],
        jobs: [],
        jobForm: copyPreset("heavy"),
        jobNames: {},
        permitReason: {},
        executed: {},
        planReasons: S.PLAN_REASONS,
        review: null,
        forms: {
          verifier: "",
          agent: { address: "", deployment: "", days: "90", caps: "0", kinds: S.KINDS.map(() => false) },
          move: { address: "", to: 2 },
          kaxiom: { id: "", text: "" },
          processor: "",
        },
        presets: S.ENERGY_PRESETS,
        domains: S.DOMAINS,
        kinds: S.KINDS,
        contextFields: S.CONTEXT_FIELDS.map((key) => ({ key, label: CONTEXT_LABELS[key] })),
      };
    },

    computed: {
      isGuide() {
        return this.account && this.k.owner && this.account.toLowerCase() === this.k.owner.toLowerCase();
      },
      isVerifier() {
        return !!this.k.accountIsVerifier;
      },
      roleText() {
        if (this.isGuide) return "You are the human guide.";
        if (this.isVerifier) return "You are a verifier.";
        if (this.k.accountAgent && this.k.accountAgent.registered) return "You are a registered agent (" + this.k.accountAgent.statusName + ").";
        return "This account has no role. You can read everything but change nothing.";
      },
      roleClass() {
        return this.isGuide ? "guide" : this.isVerifier ? "verifier" : "none";
      },
      pendingRounds() {
        return this.e ? this.e.rounds.filter((r) => r.statusName === "Partial") : [];
      },
      jobDraft() {
        try {
          const spec = S.buildSpec(this.jobForm.demand, this.jobForm.ceiling, this.jobForm.gens);
          const code = S.validateSpec(spec);
          if (code !== null) return { error: this.specProblem(code) };
          return { spec, cls: S.classify(spec), error: "" };
        } catch (err) {
          return { error: err.message };
        }
      },
      jobsNeedingMe() {
        return this.jobs.filter((j) =>
          (this.isVerifier && j.statusName === "Requested") ||
          (this.isRequester(j) && (j.statusName === "Completed" || (j.statusName === "Permitted" && j.weight === 0))));
      },
      moduleMismatch() {
        return this.e && this.e.kernel.toLowerCase() !== this.conn.kernel.toLowerCase();
      },
      canSend() {
        const r = this.review;
        return !!r && !r.sending && !r.error && r.sim && r.sim.ok && r.checks.every((c) => c.ok || c.block === false);
      },
    },

    methods: {
      /* ---------------- connection */
      async connect() {
        this.connectError = "";
        if (!S.isAddress(this.conn.kernel)) return (this.connectError = "Enter the kernel contract's address (0x followed by 40 characters).");
        if (this.conn.energy && !S.isAddress(this.conn.energy)) return (this.connectError = "The energy module address isn't a valid address.");
        if (this.conn.mode === "node" && !S.isLocalUrl(this.conn.url)) {
          return (this.connectError = "Use a node on this machine or your own network (for example http://127.0.0.1:8545).");
        }
        this.busy = true;
        try {
          const provider = S.makeProvider(this.conn.mode, this.conn.url);
          this.accounts = await provider.request(this.conn.mode === "wallet" ? "eth_requestAccounts" : "eth_accounts", []);
          if (!this.accounts.length) throw new Error("No accounts are available to sign with.");
          this.account = this.accounts[0];
          this.chainId = parseInt(await provider.request("eth_chainId", []), 16).toString();
          const addresses = { kernel: this.conn.kernel };
          if (this.conn.energy) addresses.energy = this.conn.energy;
          if (this.conn.router) {
            if (!S.isAddress(this.conn.router)) throw new Error("The job router address isn't a valid address.");
            addresses.router = this.conn.router;
          }
          this.client = S.makeClient(provider, addresses);
          const code = await provider.request("eth_getCode", [this.conn.kernel, "latest"]);
          if (!code || code === "0x") throw new Error("No contract exists at the kernel address on chain " + this.chainId + ".");
          this.connected = true;
          await this.refresh();
          if (this.conn.mode === "wallet" && window.ethereum && window.ethereum.on) {
            window.ethereum.on("accountsChanged", (a) => { this.accounts = a; this.account = a[0] || ""; this.refresh(); });
            window.ethereum.on("chainChanged", () => this.disconnect());
          }
        } catch (err) {
          this.connected = false;
          this.connectError = err.message || String(err);
        } finally {
          this.busy = false;
        }
      },

      disconnect() {
        Object.assign(this, { connected: false, client: null, k: {}, e: null, ledger: [], review: null });
      },

      async refresh() {
        if (!this.client) return;
        this.busy = true;
        try {
          this.k = await S.readKernel(this.client, this.account);
          this.e = this.conn.energy ? await S.readEnergy(this.client, 50) : null;
          this.jobs = this.conn.router ? await S.readJobs(this.client, 25) : [];
        } catch (err) {
          this.connectError = "Couldn't read the contracts: " + (err.message || err);
        } finally {
          this.busy = false;
        }
      },

      /* ---------------- formatting */
      short(h) {
        return h ? h.slice(0, 8) + "…" + h.slice(-6) : "";
      },
      when(ts) {
        return ts ? new Date(Number(ts) * 1000).toLocaleString() : "";
      },
      groundingText(g) {
        return ["EV", "EE", "ET"].filter((_, i) => (g >> i) & 1).join(" + ");
      },
      isRegistered(p) {
        return !!(this.e && this.e.axioms.some((a) => a.id.toLowerCase() === p.idBytes.toLowerCase()));
      },
      failedAxioms(r) {
        if (!this.e) return [];
        return this.e.axioms.filter((_, i) => ((r.verifiedMask >> BigInt(i)) & 1n) === 0n).map((a) => a.label);
      },
      roundLabel(r) {
        return { Full: "Accepted (all hold)", Partial: "Waiting for you", Fallback: "Refused (under half)", Ratified: "Accepted by you" }[r.statusName] || r.statusName;
      },
      statusMeaning(s) {
        return {
          Full: "It would be accepted automatically.",
          Partial: "It would wait for your decision.",
          Fallback: "It could never be accepted.",
          None: "No axioms are registered yet.",
        }[s];
      },

      /* ---------------- review flow */
      async openReview(spec) {
        const r = { ...spec, sim: null, error: "", sending: false, data: "", signature: "" };
        try {
          r.signature = S.ABI[spec.contract].functions[spec.fn].sig;
          r.data = S.encodeCall(spec.contract, spec.fn, spec.args);
        } catch (err) {
          r.error = err.message;
          r.sim = { ok: false, reason: "the call could not be built" };
        }
        this.review = r;
        const live = this.review; // the reactive proxy Vue now holds
        if (!live.error) {
          const sim = await this.client.simulate(spec.contract, spec.fn, spec.args, this.account);
          if (this.review === live) live.sim = sim; // ignore a dry run for a sheet that was closed
        }
      },

      closeReview() {
        if (this.review && !this.review.sending) this.review = null;
      },

      async sendReviewed() {
        const r = this.review;
        if (!this.canSend) return;
        r.sending = true;
        let entry = null;
        try {
          const hash = await this.client.send(r.contract, r.fn, r.args, this.account);
          this.journal.unshift({ hash, title: r.title, state: "Pending", note: r.keepNote || "" });
          entry = this.journal[0]; // reactive copy, so status changes show
          this.review = null;
          const receipt = await this.client.receipt(hash);
          entry.state = receipt.status === "0x1" ? "Confirmed" : "Failed";
          if (entry.state === "Confirmed" && r.onConfirmed) r.onConfirmed();
          await this.refresh();
        } catch (err) {
          if (entry) entry.state = "Failed";
          if (this.review === r) {
            r.sending = false;
            r.error = err.code === 4001 ? "You declined to sign. Nothing was sent." : "Not sent: " + (err.message || err);
          }
        }
      },

      check(ok, label, block) {
        return { ok: !!ok, label, block: block !== false };
      },

      /* ---------------- actions */
      reviewSafeStop(engage) {
        const allowed = engage ? this.isGuide || this.isVerifier : this.isGuide;
        return this.openReview({
          title: engage ? "Engage Safe Stop" : "Release Safe Stop",
          lines: engage
            ? ["Every agent action will be answered SAFE_STOP and the energy module will refuse new rounds and ratifications.", "Only the human guide can release it."]
            : ["Agents' actions will be decided normally again, and the energy module will accept rounds."],
          checks: [
            this.check(allowed, engage ? "You are the human guide or a verifier" : "You are the human guide"),
            this.check(this.k.safeStopped !== engage, engage ? "Safe Stop is not already engaged" : "Safe Stop is currently engaged"),
          ],
          contract: "kernel", fn: "setSafeStop", args: [engage],
        });
      },

      reviewRatify(r) {
        const text = (this.rationale[r.id] || "").trim();
        const fingerprint = text ? S.sha256Hex(text) : EMPTY32;
        return this.openReview({
          title: "Accept round " + r.id,
          lines: [
            r.verifiedCount + " of " + r.total + " axioms held. You are accepting it despite: " + (this.failedAxioms(r).join(", ") || "none") + ".",
            "Your reason is recorded on chain by its SHA-256 fingerprint " + this.short(fingerprint) + ". Keep the text itself; anyone can check it against the fingerprint.",
          ],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(r.statusName === "Partial", "The round is waiting for a decision"),
            this.check(text.length >= 20, "You wrote a reason of at least 20 characters"),
            this.check(!this.k.safeStopped, "Safe Stop is not engaged"),
          ],
          contract: "energy", fn: "ratifyRound", args: [r.id, fingerprint],
          keepNote: "Reason: " + text,
        });
      },

      reviewRegisterPreset(p) {
        return this.openReview({
          title: "Register " + p.id + ", " + p.name,
          lines: [
            "\u201C" + p.statement + "\u201D",
            "Domain: " + S.DOMAINS[p.domain] + ". Grounds to " + this.groundingText(p.grounding) + ". Charge " + p.charge + ".",
            "Its statement's SHA-256 fingerprint " + this.short(p.contentHash) + " is what goes on chain.",
          ],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(p.registrable, "It grounds to at least two meta-root components"),
            this.check(!this.e.axiomsSealed, "The axiom set is not sealed"),
            this.check(!this.isRegistered(p), "It isn't registered already"),
          ],
          contract: "energy", fn: "registerAxiom",
          args: [p.idBytes, p.contentHash, p.domain, p.grounding, 0, S.parseWad(p.charge)],
        });
      },

      reviewSealEnergy() {
        const covered = this.e.axioms.reduce((g, a) => g | a.grounding, 0) === 7;
        return this.openReview({
          title: "Seal the energy axioms",
          lines: [
            "This permanently fixes the " + this.e.axioms.length + " registered axioms. Nothing can be added, changed, or removed afterward.",
            "Measurement rounds can begin once they're sealed.",
          ],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(this.e.axioms.length > 0, "At least one axiom is registered"),
            this.check(!this.e.axiomsSealed, "The set is not sealed yet"),
            this.check(covered, "Together they ground to all three of EV, EE and ET", false),
          ],
          contract: "energy", fn: "sealAxioms", args: [],
        });
      },

      reviewVerifier(active) {
        const a = this.forms.verifier;
        return this.openReview({
          title: (active ? "Add verifier " : "Remove verifier ") + this.short(a),
          lines: [active
            ? "This account will be able to attest to agents' actions, submit energy measurements, verify agents, and engage Safe Stop."
            : "This account will lose every verifier power. Attestations it already made stop counting."],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(S.isAddress(a), "The address is valid"),
            this.check(!active || a.toLowerCase() !== this.k.owner.toLowerCase(), "It isn't your own account (roles must stay separate)"),
          ],
          contract: "kernel", fn: "setVerifier", args: [S.isAddress(a) ? a : ZERO, active],
        });
      },

      reviewRegisterAgent() {
        const f = this.forms.agent;
        const kindsMask = f.kinds.reduce((m, on, i) => (on ? m | (1 << i) : m), 0);
        const days = Number(f.days);
        const caps = Number(f.caps);
        const validUntil = Math.floor(Date.now() / 1000) + Math.max(0, Math.floor(days)) * 86400;
        const depId = f.deployment ? S.sha256Hex("deployment:" + f.deployment) : EMPTY32;
        return this.openReview({
          title: "Register agent " + this.short(f.address),
          lines: [
            "It starts as Proposed. A verifier must verify it, then you activate it, before any action can execute.",
            "Allowed actions: " + (S.KINDS.filter((_, i) => f.kinds[i]).join(", ") || "none") + ". Directive valid " + days + " days.",
            "Deployment \u201C" + f.deployment + "\u201D is recorded as fingerprint " + this.short(depId) + ".",
          ],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(S.isAddress(f.address), "The agent address is valid"),
            this.check(f.deployment.length > 0, "A deployment name is given"),
            this.check(kindsMask > 0, "At least one action type is allowed"),
            this.check(Number.isInteger(days) && days > 0 && days <= 3650, "Validity is between 1 and 3650 days"),
            this.check(Number.isInteger(caps) && caps >= 0 && caps < 2 ** 32, "Capability bits fit in 32 bits"),
          ],
          contract: "kernel", fn: "registerAgent",
          args: [S.isAddress(f.address) ? f.address : ZERO, Number.isInteger(caps) && caps >= 0 && caps < 2 ** 32 ? caps : 0, kindsMask, depId, validUntil],
        });
      },

      async reviewTransition() {
        const f = this.forms.move;
        let agent = null;
        if (S.isAddress(f.address)) {
          try { agent = S.decodeAgent(await this.client.call("kernel", "getAgent", [f.address])); } catch (_) { agent = null; }
        }
        const to = Number(f.to);
        const from = agent ? agent.status : -1;
        const legal = (from === 1 && to === 2) || (from === 3 && to === 2) || (from === 3 && to === 4) || (from === 2 && to === 4);
        return this.openReview({
          title: (to === 2 ? "Activate agent " : "Revoke agent ") + this.short(f.address),
          lines: [to === 2
            ? "The agent's actions can execute when they pass every check."
            : "Permanent. The agent can never act again under this kernel."],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(agent && agent.registered, "The agent is registered"),
            this.check(legal, agent && agent.registered ? "Moving from " + agent.statusName + " to " + S.STATUS[to] + " is allowed" : "The move is allowed"),
          ],
          contract: "kernel", fn: "transitionAgent", args: [S.isAddress(f.address) ? f.address : ZERO, to, EMPTY32],
        });
      },

      reviewEpoch() {
        return this.openReview({
          title: "Advance the directive epoch",
          lines: ["Every agent's directive stops being valid immediately. Agents can't act until you renew each one."],
          checks: [this.check(this.isGuide, "You are the human guide")],
          contract: "kernel", fn: "advanceEpoch", args: [],
        });
      },

      reviewKernelAxiom() {
        const f = this.forms.kaxiom;
        let idBytes = EMPTY32, idOk = true;
        try { idBytes = S.textToBytes32(f.id); } catch (_) { idOk = false; }
        const hash = f.text.trim() ? S.sha256Hex(f.text) : EMPTY32;
        return this.openReview({
          title: "Register kernel axiom " + f.id,
          lines: ["\u201C" + f.text + "\u201D", "Recorded by its SHA-256 fingerprint " + this.short(hash) + ". Keep the exact text; one changed character changes the fingerprint."],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(idOk, "The identifier is 1 to 32 characters"),
            this.check(f.text.trim().length > 0, "The statement isn't empty"),
            this.check(!this.k.axiomsSealed, "Kernel axioms are not sealed"),
          ],
          contract: "kernel", fn: "registerAxiom", args: [idBytes, hash],
          keepNote: f.id + ": " + f.text,
        });
      },

      reviewSealKernel() {
        return this.openReview({
          title: "Seal the kernel axioms",
          lines: ["Permanently fixes the " + this.k.axiomCount + " kernel axioms. Verifiers can only attest after this."],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(Number(this.k.axiomCount) > 0, "At least one axiom is registered"),
            this.check(!this.k.axiomsSealed, "They aren't sealed yet"),
          ],
          contract: "kernel", fn: "sealAxioms", args: [],
        });
      },

      /* ---------------- jobs */
      fmt(v) {
        return S.formatWad(BigInt(v));
      },
      isRequester(j) {
        return !!this.account && j.requester.toLowerCase() === this.account.toLowerCase();
      },
      specProblem(code) {
        return ["", "The job needs at least one generator.", "Use between 1 and 32 generators.", "The generator list is malformed.",
          "Demand must be above zero.", "The cost ceiling can't be negative.", "Values must be zero or positive.",
          "Each generator needs a capacity above zero and a minimum no larger than its capacity."][code];
      },
      jobStatusText(j) {
        return { Requested: "Waiting for permission", Permitted: j.weight ? "Permitted, sent to processor" : "Permitted, solve here",
          Denied: "Denied", Completed: "Result accepted, ready to execute", Failed: "Failed after 3 refused results", Executed: "Executed" }[j.statusName] || j.statusName;
      },
      jobTagClass(j) {
        return { Executed: "s-full", Completed: "s-partial", Requested: "s-partial", Denied: "s-fallback", Failed: "s-fallback" }[j.statusName] || "";
      },
      loadJobPreset(k) {
        this.jobForm = copyPreset(k);
      },
      genName(specHash, i) {
        const names = this.jobNames[specHash];
        return (names && names[i]) || "Generator " + (i + 1);
      },
      async jobSpec(j) {
        const ev = await S.jobEvent(this.client, "JobSubmitted", j.id, this.conn.fromBlock);
        return ev ? ev.values[3] : null;
      },

      reviewSubmitJob() {
        const d = this.jobDraft;
        if (d.error) return;
        const minutes = Number(this.jobForm.minutes);
        const deadline = Math.floor(Date.now() / 1000) + Math.floor(minutes) * 60;
        const specHash = S.packedHash(d.spec);
        const names = this.jobForm.gens.map((g) => g.name);
        return this.openReview({
          title: "Send a " + (d.cls.weight ? "heavy" : "light") + " dispatch job",
          lines: [
            "Demand " + this.jobForm.demand + " across " + this.jobForm.gens.length + " generators, cost ceiling " + this.jobForm.ceiling + ", deadline in " + minutes + " minutes.",
            d.cls.why,
            "The specification goes on chain with fingerprint " + this.short(specHash) + ". Generator names stay on this machine.",
          ],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(d.cls.feasibleCapacity, "Total capacity covers demand"),
            this.check(Number.isInteger(minutes) && minutes >= 1 && minutes <= 10080, "Deadline is between 1 minute and 7 days"),
            this.check(!this.k.safeStopped, "Safe Stop is not engaged"),
          ],
          contract: "router", fn: "submitJob", args: [d.spec, d.cls.weight, deadline],
          onConfirmed: () => { this.jobNames[specHash] = names; },
        });
      },

      async reviewPermit(j, approve) {
        const spec = await this.jobSpec(j);
        const text = (this.permitReason[j.id] || "").trim();
        const cls = spec ? S.classify(spec) : null;
        return this.openReview({
          title: (approve ? "Grant permission for job " : "Deny job ") + j.id,
          lines: [
            spec ? "Demand " + this.fmt(spec[0]) + " across " + spec[2] + " generators, cost ceiling " + this.fmt(spec[1]) + "." : "The job's specification couldn't be read.",
            approve ? (j.weight ? "A processor will receive the execution command." : "The requester's front end will solve it.") : "The job ends here.",
          ],
          checks: [
            this.check(this.isVerifier, "You are a verifier"),
            this.check(j.statusName === "Requested", "The job is waiting for permission"),
            this.check(spec && S.packedHash(spec) === j.specHash, "The specification matches its on-chain fingerprint"),
            this.check(spec && S.validateSpec(spec) === null, "The specification is well formed"),
            this.check(Number(j.deadline) > Date.now() / 1000, "The deadline hasn't passed"),
            this.check(text.length >= 10, "You wrote a reason of at least 10 characters"),
            this.check(!approve || (cls && cls.feasibleCapacity), "Total capacity covers demand", false),
            this.check(!approve || (cls && cls.weight === j.weight), "The declared weight matches its difficulty", false),
          ],
          contract: "router", fn: "permitJob", args: [j.id, approve, text ? S.sha256Hex(text) : EMPTY32],
          keepNote: "Reason: " + text,
        });
      },

      async reviewSolveLight(j) {
        const spec = await this.jobSpec(j);
        const plan = spec ? S.meritOrder(spec) : null;
        const res = plan ? S.checkPlan(spec, plan) : null;
        return this.openReview({
          title: "Submit the exact solution for job " + j.id,
          lines: plan
            ? ["Solved here by merit order, which is exactly optimal for this job:",
              ...plan.map((p, i) => this.genName(j.specHash, i) + ": " + (p === 0n ? "off" : this.fmt(p))),
              "Exact total cost " + this.fmt(res.cost) + ". The contract checks it again before accepting it."]
            : ["No plan exists: capacity can't cover demand."],
          checks: [
            this.check(this.isRequester(j), "You requested this job"),
            this.check(j.statusName === "Permitted" && j.weight === 0, "It's a permitted light job"),
            this.check(spec && S.packedHash(spec) === j.specHash, "The specification matches its on-chain fingerprint"),
            this.check(res && res.reason === 0, res ? "Exact check: " + S.PLAN_REASONS[res.reason] : "A plan was found"),
          ],
          contract: "router", fn: "submitResult", args: [j.id, spec || [], plan || []],
        });
      },

      async reviewExecute(j) {
        const spec = await this.jobSpec(j);
        const acc = await S.jobEvent(this.client, "ResultAccepted", j.id, this.conn.fromBlock);
        const plan = acc ? acc.values[2] : null;
        const res = spec && plan ? S.checkPlan(spec, plan) : null;
        let executable = false;
        try { executable = plan ? S.asBool((await this.client.call("router", "isExecutable", [j.id, S.packedHash(plan)]))[0]) : false; } catch (_) { executable = false; }
        const report = plan
          ? ["Dispatch orders for job " + j.id + " (exact WAD-18)", ...plan.map((p, i) => this.genName(j.specHash, i) + ": " + (p === 0n ? "off" : this.fmt(p))),
            "Total " + this.fmt(spec[0]) + ", exact cost " + this.fmt(j.cost), "Plan fingerprint " + j.planHash].join("\n")
          : "";
        const reportHash = report ? S.sha256Hex(report) : EMPTY32;
        return this.openReview({
          title: "Execute job " + j.id,
          lines: plan
            ? ["These dispatch orders will be issued from this front end, and an execution report recorded on chain:", ...report.split("\n").slice(1, -1)]
            : ["The accepted plan couldn't be read from the chain."],
          checks: [
            this.check(this.isRequester(j), "You requested this job"),
            this.check(spec && S.packedHash(spec) === j.specHash, "The specification matches its on-chain fingerprint"),
            this.check(plan && S.packedHash(plan) === j.planHash, "The plan matches the accepted fingerprint"),
            this.check(res && res.reason === 0 && res.cost === j.cost, "Re-checked here exactly: valid, same cost"),
            this.check(executable, "The contract confirms it's executable now"),
          ],
          contract: "router", fn: "markExecuted", args: [j.id, reportHash],
          keepNote: report,
          onConfirmed: () => { this.executed[j.id] = report; },
        });
      },

      async reviewProcessor(active) {
        const a = this.forms.processor;
        let isVer = false;
        if (S.isAddress(a)) { try { isVer = S.asBool((await this.client.call("kernel", "isVerifier", [a]))[0]); } catch (_) { isVer = false; } }
        return this.openReview({
          title: (active ? "Register processor " : "Remove processor ") + this.short(a),
          lines: [active ? "This account will be able to pull heavy jobs' execution commands and submit results. The contract still checks every result exactly." : "This account will no longer be able to submit results."],
          checks: [
            this.check(this.isGuide, "You are the human guide"),
            this.check(S.isAddress(a), "The address is valid"),
            this.check(!active || (S.isAddress(a) && a.toLowerCase() !== this.k.owner.toLowerCase() && !isVer), "It isn't you or a verifier (roles stay separate)"),
          ],
          contract: "router", fn: "setProcessor", args: [S.isAddress(a) ? a : ZERO, active],
        });
      },

      /* ---------------- measurement dry run */
      loadSample() {
        this.ctx = { ...S.SAMPLE_CONTEXT };
      },

      async dryRun() {
        this.dry = { local: null, rows: [], chain: null, agree: false, error: "" };
        const c = { conditions: 0n };
        try {
          for (const f of this.contextFields) {
            try { c[f.key] = S.parseWad(this.ctx[f.key]); } catch (err) { throw new Error(f.label + ": " + err.message); }
          }
        } catch (err) {
          this.dry.error = err.message;
          return;
        }
        const axioms = this.e.axioms.length
          ? this.e.axioms
          : this.presets.filter((p) => p.registrable).map((p) => ({ label: p.id, domain: p.domain, conditionMask: 0n }));
        const local = S.evaluateLocal(axioms, c);
        this.dry.local = local;
        this.dry.rows = axioms.map((a, i) => ({ label: a.label || a.id, holds: ((local.mask >> BigInt(i)) & 1n) === 1n }));
        if (this.e.axioms.length) {
          try {
            const w = await this.client.call("energy", "evaluate", [S.contextTuple(c)]);
            this.dry.chain = { mask: w[0], count: Number(w[1]), total: Number(w[2]) };
            this.dry.agree = w[0] === local.mask && Number(w[1]) === local.count && Number(w[2]) === local.total;
          } catch (_) {
            this.dry.chain = null;
          }
        }
      },

      /* ---------------- ledgers */
      async verifyLedgers() {
        this.busy = true;
        this.ledger = [];
        try {
          const rows = [];
          const kr = await S.verifyLedger(this.client, "kernel", this.conn.fromBlock, { head: this.k.ledgerHead, length: this.k.ledgerLength });
          rows.push({ name: "Kernel ledger", ...kr });
          if (this.e) {
            const er = await S.verifyLedger(this.client, "energy", this.conn.fromBlock, { head: this.e.ledgerHead, length: this.e.ledgerLength });
            rows.push({ name: "Energy module ledger", ...er });
          }
          this.ledger = rows;
        } catch (err) {
          this.ledger = [{ name: "Ledger check", ok: false, problem: "Couldn't read the logs: " + (err.message || err) + ". Check the deployment block." }];
        } finally {
          this.busy = false;
        }
      },
    },

    mounted() {
      const boot = document.getElementById("boot");
      if (boot) boot.remove();
    },
  });

  app.mount("#app");
})();
