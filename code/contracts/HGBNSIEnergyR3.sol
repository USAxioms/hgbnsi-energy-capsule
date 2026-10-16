// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.24;

/*
 * HUMAN-GUIDED BLOCKCHAIN-NATIVE SAFE SUPERINTELLIGENCE (HGBNSI)
 * Energy-sector domain module — normative port of ENERGY_R3.py
 * by Michael Aaron Russell (Universal Standard Axiom Corp).
 *
 * Category: a domain module of the SSI Verification Kernel (SSIVerificationKernel.sol).
 *   - Governance is the kernel's owner: the human guide.
 *   - Only the kernel's registered verifiers may submit measurement rounds.
 *   - The kernel's SAFE STOP halts this module too.
 *   - Every accepted round yields a record hash that kernel verifiers cite as
 *     evidence when they attest to an energy-sector action.
 *
 * Ported faithfully from ENERGY_R3.py:
 *   - meta-root triad EV ∧ EE ∧ ET; every axiom must ground to ≥ 2 components;
 *   - domain checks: thermodynamics (energy_in = energy_out + energy_stored),
 *     economics (value_created ≥ value_destroyed), ethics (|benefit_a − benefit_b| ≤ 1),
 *     operations (uptime ≥ 95 %), generic (every named condition = 1);
 *   - coherence fallback threshold 50 %.
 *
 * Deliberate changes (fail-closed, exact):
 *   - all quantities are WAD-18 integers; 95 % is checked as up·100 ≥ total·95, never with floats;
 *   - uptime must also satisfy 0 ≤ up ≤ total (the Python accepts up > total);
 *   - an axiom grounding to fewer than 2 components is REFUSED at registration
 *     (in the Python it registers but can never verify);
 *   - the mod-1,000,000 arithmetic hashes are replaced by SHA-256;
 *   - coherence is reported as exact counts (verified / total), never a rounded fraction.
 *
 * Human guidance:
 *   FULL     — every axiom verified: accepted automatically;
 *   PARTIAL  — at least half verified: accepted only if the human guide ratifies it;
 *   FALLBACK — fewer than half verified: can never be accepted.
 *
 * Off-chain only: the meta-dynamics of ENERGY_R3.py (Hamiltonian flow, Fokker–Planck,
 * resonance oscillators) use exp/log approximations that cannot be exact in WAD-18;
 * verifiers run them off-chain and commit their output through evidenceHash.
 *
 * STATUS: written without access to a Solidity compiler. Compile, test on a testnet,
 * and obtain an independent audit before mainnet deployment.
 */

interface ISSIVerificationKernel {
    function owner() external view returns (address);
    function isVerifier(address account) external view returns (bool);
    function safeStopped() external view returns (bool);
    function activeKernel() external view returns (bytes32);
}

contract HGBNSIEnergyR3 {
    /* ----------------------------- types --------------------------------- */
    enum Domain { THERMODYNAMICS, ECONOMICS, ETHICS, OPERATIONS, GENERIC }
    enum RoundStatus { NONE, FULL, PARTIAL, FALLBACK, RATIFIED }

    struct Axiom {
        bool exists;
        Domain domain;
        uint8 grounding; // bitmask over the meta-root: EV = 1, EE = 2, ET = 4
        bytes32 contentHash; // SHA-256 of the axiom's name and statement
        uint256 conditionMask; // GENERIC domain: conditions that must all equal 1
        int256 chargeWad; // metaphysical charge, WAD-18 (informational)
    }

    /// One measurement of the energy system. Quantities are WAD-18 (1.0 = 1e18).
    struct Context {
        int256 energyIn;
        int256 energyOut;
        int256 energyStored;
        int256 valueCreated;
        int256 valueDestroyed;
        int256 benefitA;
        int256 benefitB;
        int256 systemUp;
        int256 systemTotal;
        uint256 conditions; // bit i = named condition i holds (energy_conserved, …)
    }

    struct Round {
        RoundStatus status;
        uint8 verifiedCount;
        uint8 total;
        uint64 timestamp;
        address verifier;
        uint256 verifiedMask; // bit i = axiomIds[i] verified
        bytes32 contextHash;
        bytes32 evidenceHash;
        bytes32 record; // the hash kernel verifiers cite as evidence
    }

    /* ----------------------------- constants ----------------------------- */
    uint8 public constant EV = 1;
    uint8 public constant EE = 2;
    uint8 public constant ET = 4;
    uint8 public constant MAX_AXIOMS = 64;
    int256 public constant WAD = 1e18;
    int256 public constant FAIRNESS_TOLERANCE = 1e18; // |benefit_a − benefit_b| ≤ 1
    int256 public constant UPTIME_NUMERATOR = 95; // uptime ≥ 95 / 100
    int256 public constant UPTIME_DENOMINATOR = 100;
    int256 private constant WAD_MAX = int256(type(int128).max);
    int256 private constant WAD_MIN = -int256(type(int128).max);

    bytes32 private constant TAG_GENESIS = "HGBNSI.ENERGY.GENESIS";
    bytes32 private constant TAG_AXIOM = "HGBNSI.ENERGY.AXIOM";
    bytes32 private constant TAG_SEAL = "HGBNSI.ENERGY.SEAL";
    bytes32 private constant TAG_ROUND = "HGBNSI.ENERGY.ROUND";
    bytes32 private constant TAG_RATIFY = "HGBNSI.ENERGY.RATIFY";

    /* ----------------------------- errors -------------------------------- */
    error NotHumanGuide();
    error NotVerifier();
    error SafeStopped();
    error ZeroValue();
    error AxiomsAlreadySealed();
    error AxiomsNotSealed();
    error AxiomExists(bytes32 id);
    error TooManyAxioms();
    error InsufficientGrounding(bytes32 id, uint8 grounding);
    error InvalidAxiom(bytes32 id);
    error ValueOutOfWadRange();
    error UnknownRound(uint256 roundId);
    error NotRatifiable(uint256 roundId, RoundStatus status);

    /* ----------------------------- events -------------------------------- */
    event LedgerAppended(uint256 indexed seq, bytes32 indexed entry, bytes32 indexed tag, bytes32 subject, bytes32 data);
    event AxiomRegistered(bytes32 indexed id, Domain domain, uint8 grounding, bytes32 contentHash);
    event AxiomsSealed(bytes32 registryHash, uint256 count);
    event RoundSubmitted(
        uint256 indexed roundId, address indexed verifier, RoundStatus status, uint8 verifiedCount, uint8 total, bytes32 record
    );
    event RoundRatified(uint256 indexed roundId, address indexed humanGuide, bytes32 rationaleHash);

    /* ----------------------------- state --------------------------------- */
    ISSIVerificationKernel public immutable kernel;

    bytes32[] public axiomIds;
    mapping(bytes32 => Axiom) internal axioms;
    bool public axiomsSealed;
    bytes32 public registryHash;

    bytes32 public ledgerHead;
    uint256 public ledgerLength;

    uint256 public roundCount;
    mapping(uint256 => Round) internal rounds;

    // R³: compress (record) → verify (round) → store (rounds) → reinforce (best / last accepted)
    uint8 public bestVerifiedCount;
    uint256 public lastAcceptedRound; // 0 = none yet; round ids start at 1

    /* ----------------------------- modifiers ----------------------------- */
    modifier onlyHumanGuide() {
        if (msg.sender != kernel.owner()) revert NotHumanGuide();
        _;
    }

    modifier onlyVerifier() {
        if (!kernel.isVerifier(msg.sender)) revert NotVerifier();
        _;
    }

    modifier notStopped() {
        if (kernel.safeStopped()) revert SafeStopped();
        _;
    }

    /* ----------------------------- constructor --------------------------- */
    constructor(address ssiKernel) {
        if (ssiKernel == address(0)) revert ZeroValue();
        kernel = ISSIVerificationKernel(ssiKernel);
        ledgerHead = sha256(abi.encodePacked(TAG_GENESIS, block.chainid, address(this), ssiKernel));
    }

    /* ======================= axioms (human guide) ======================= */

    function registerAxiom(
        bytes32 id,
        bytes32 contentHash,
        Domain domain,
        uint8 grounding,
        uint256 conditionMask,
        int256 chargeWad
    ) external onlyHumanGuide {
        if (axiomsSealed) revert AxiomsAlreadySealed();
        if (id == bytes32(0) || contentHash == bytes32(0)) revert ZeroValue();
        if (axioms[id].exists) revert AxiomExists(id);
        if (axiomIds.length >= MAX_AXIOMS) revert TooManyAxioms();
        if (grounding >> 3 != 0) revert InvalidAxiom(id);
        if (_popcount3(grounding) < 2) revert InsufficientGrounding(id, grounding);
        if (domain == Domain.GENERIC && conditionMask == 0) revert InvalidAxiom(id);
        if (!_inRange(chargeWad)) revert ValueOutOfWadRange();

        axioms[id] = Axiom({
            exists: true,
            domain: domain,
            grounding: grounding,
            contentHash: contentHash,
            conditionMask: conditionMask,
            chargeWad: chargeWad
        });
        axiomIds.push(id);
        emit AxiomRegistered(id, domain, grounding, contentHash);
        _append(TAG_AXIOM, id, contentHash);
    }

    /// Seals the registry forever and fixes its SHA-256 identity.
    function sealAxioms() external onlyHumanGuide {
        if (axiomsSealed) revert AxiomsAlreadySealed();
        uint256 n = axiomIds.length;
        if (n == 0) revert ZeroValue();
        bytes memory packed;
        for (uint256 i = 0; i < n; i++) {
            Axiom storage a = axioms[axiomIds[i]];
            packed = abi.encodePacked(
                packed, axiomIds[i], a.contentHash, uint8(a.domain), a.grounding, a.conditionMask, a.chargeWad
            );
        }
        registryHash = sha256(packed);
        axiomsSealed = true;
        emit AxiomsSealed(registryHash, n);
        _append(TAG_SEAL, registryHash, bytes32(n));
    }

    /* ======================= verification rounds ======================== */

    /// A kernel verifier submits one measured context; the contract verifies every axiom.
    function submitRound(Context calldata c, bytes32 evidenceHash)
        external
        onlyVerifier
        notStopped
        returns (uint256 roundId, RoundStatus status)
    {
        if (!axiomsSealed) revert AxiomsNotSealed();
        if (evidenceHash == bytes32(0)) revert ZeroValue();
        _requireContextInRange(c);

        (uint256 mask, uint8 count, uint8 total) = _evaluate(c);
        if (count == total) status = RoundStatus.FULL;
        else if (uint256(count) * 2 >= uint256(total)) status = RoundStatus.PARTIAL;
        else status = RoundStatus.FALLBACK;

        roundId = ++roundCount;
        bytes32 contextHash = sha256(abi.encode(c));
        bytes32 record = sha256(
            abi.encodePacked(roundId, mask, contextHash, evidenceHash, registryHash, kernel.activeKernel())
        );
        rounds[roundId] = Round({
            status: status,
            verifiedCount: count,
            total: total,
            timestamp: uint64(block.timestamp),
            verifier: msg.sender,
            verifiedMask: mask,
            contextHash: contextHash,
            evidenceHash: evidenceHash,
            record: record
        });

        if (count > bestVerifiedCount) bestVerifiedCount = count; // R³ reinforce
        if (status == RoundStatus.FULL) lastAcceptedRound = roundId;

        emit RoundSubmitted(roundId, msg.sender, status, count, total, record);
        _append(TAG_ROUND, bytes32(roundId), record);
    }

    /// The human guide may accept a PARTIAL round, with a recorded rationale. Never a FALLBACK round.
    function ratifyRound(uint256 roundId, bytes32 rationaleHash) external onlyHumanGuide notStopped {
        Round storage r = rounds[roundId];
        if (r.status == RoundStatus.NONE) revert UnknownRound(roundId);
        if (r.status != RoundStatus.PARTIAL) revert NotRatifiable(roundId, r.status);
        if (rationaleHash == bytes32(0)) revert ZeroValue();
        r.status = RoundStatus.RATIFIED;
        lastAcceptedRound = roundId;
        emit RoundRatified(roundId, msg.sender, rationaleHash);
        _append(TAG_RATIFY, bytes32(roundId), rationaleHash);
    }

    /* ======================= views ===================================== */

    function isAccepted(uint256 roundId) external view returns (bool) {
        RoundStatus s = rounds[roundId].status;
        return s == RoundStatus.FULL || s == RoundStatus.RATIFIED;
    }

    function getRound(uint256 roundId) external view returns (Round memory) {
        return rounds[roundId];
    }

    function getAxiom(bytes32 id) external view returns (Axiom memory) {
        return axioms[id];
    }

    function axiomCount() external view returns (uint256) {
        return axiomIds.length;
    }

    /// Dry run: which axioms a context would verify, without recording anything.
    function evaluate(Context calldata c) external view returns (uint256 verifiedMask, uint8 verifiedCount, uint8 total) {
        _requireContextInRange(c);
        return _evaluate(c);
    }

    /// Meta-root triad check: EV ∧ EE ∧ ET are each grounded by at least one registered axiom.
    function triadCovered() external view returns (bool) {
        uint8 covered;
        for (uint256 i = 0; i < axiomIds.length; i++) covered |= axioms[axiomIds[i]].grounding;
        return covered == (EV | EE | ET);
    }

    /* ======================= internals ================================= */

    function _evaluate(Context calldata c) internal view returns (uint256 mask, uint8 count, uint8 total) {
        uint256 n = axiomIds.length;
        total = uint8(n);
        for (uint256 i = 0; i < n; i++) {
            if (_holds(axioms[axiomIds[i]], c)) {
                mask |= uint256(1) << i;
                count++;
            }
        }
    }

    /// The domain checks of Axiom.verify in ENERGY_R3.py, in exact integers.
    function _holds(Axiom storage a, Context calldata c) internal view returns (bool) {
        if (a.domain == Domain.THERMODYNAMICS) {
            return c.energyIn == c.energyOut + c.energyStored;
        }
        if (a.domain == Domain.ECONOMICS) {
            return c.valueCreated >= c.valueDestroyed;
        }
        if (a.domain == Domain.ETHICS) {
            int256 diff = c.benefitA - c.benefitB;
            if (diff < 0) diff = -diff;
            return diff <= FAIRNESS_TOLERANCE;
        }
        if (a.domain == Domain.OPERATIONS) {
            if (c.systemTotal <= 0 || c.systemUp < 0 || c.systemUp > c.systemTotal) return false;
            return c.systemUp * UPTIME_DENOMINATOR >= c.systemTotal * UPTIME_NUMERATOR;
        }
        return (c.conditions & a.conditionMask) == a.conditionMask; // GENERIC
    }

    function _requireContextInRange(Context calldata c) internal pure {
        if (
            !_inRange(c.energyIn) || !_inRange(c.energyOut) || !_inRange(c.energyStored)
                || !_inRange(c.valueCreated) || !_inRange(c.valueDestroyed) || !_inRange(c.benefitA)
                || !_inRange(c.benefitB) || !_inRange(c.systemUp) || !_inRange(c.systemTotal)
        ) revert ValueOutOfWadRange();
    }

    function _inRange(int256 x) internal pure returns (bool) {
        return x >= WAD_MIN && x <= WAD_MAX;
    }

    function _popcount3(uint8 g) internal pure returns (uint8) {
        return (g & 1) + ((g >> 1) & 1) + ((g >> 2) & 1);
    }

    /// Append-only SHA-256 hash chain, same construction as the kernel's ledger.
    function _append(bytes32 tag, bytes32 subject, bytes32 data) private {
        uint256 seq = ledgerLength;
        bytes32 entry = sha256(abi.encodePacked(ledgerHead, seq, tag, subject, data, block.number));
        ledgerHead = entry;
        ledgerLength = seq + 1;
        emit LedgerAppended(seq, entry, tag, subject, data);
    }
}
