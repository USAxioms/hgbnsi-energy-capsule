// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.24;

/*
 * SSI Verification Kernel — on-chain execution of the Safe Super Intelligence
 * decision semantics by Michael Aaron Russell (Universal Standard Axiom Corp).
 *
 * Ported from the C reference kernel ssi-verification-kernel v1.1
 * (decision_table_sha256 9e180bc9a6aba7bb58813b0ee24e7ae99722786aa655d801aa96bf010ca221b7).
 *
 * What this contract is: the deterministic, fail-closed GATE and LEDGER of an
 * intelligent system. Reasoning happens off-chain; every action the system wants
 * to take must pass through this contract, which decides EXECUTE / REJECT /
 * DEFER / SAFE_STOP exactly as the reference kernel does, records the decision in
 * an append-only SHA-256 hash chain, and only then marks the action authorized.
 *
 * Security properties by construction:
 *   - no external calls, no ether handling, no upgrade path, no delegatecall;
 *   - every check fails closed: UNKNOWN is never PASS, a missing value is never TRUE;
 *   - separation of duties: owner, verifiers and agents are disjoint sets;
 *   - verifiers can engage SAFE STOP; only the owner can release it;
 *   - kernel replacement (R³ adoption) needs a verifier proof, non-regression,
 *     and a time lock.
 *
 * STATUS: written without access to a Solidity compiler. It must be compiled,
 * tested, and independently audited before any mainnet deployment.
 */

/* ------------------------------------------------------------------------- */
/*  Shared types — numbering matches the C kernel's enums exactly             */
/* ------------------------------------------------------------------------- */

enum Decision { EXECUTE, REJECT, DEFER, SAFE_STOP }
enum VerResult { PASS, FAIL, UNKNOWN }
enum AssetStatus { PROPOSED, VERIFIED, ACTIVE, REVALIDATION, REVOKED, REJECTED }

/* ------------------------------------------------------------------------- */
/*  WAD-18: exact 18-decimal fixed point, range and failure modes of wad18.c  */
/* ------------------------------------------------------------------------- */

library WAD18 {
    int256 internal constant SCALE = 1e18;
    int256 internal constant MAX = int256(type(int128).max); // 2^127 - 1
    int256 internal constant MIN = -int256(type(int128).max); // symmetric range

    error WadOverflow();
    error WadDivisionByZero();
    error WadNonExact();

    function inRange(int256 x) internal pure returns (bool) {
        return x >= MIN && x <= MAX;
    }

    function _req(int256 x) private pure returns (int256) {
        if (x < MIN || x > MAX) revert WadOverflow();
        return x;
    }

    function add(int256 a, int256 b) internal pure returns (int256) {
        return _req(_req(a) + _req(b));
    }

    function sub(int256 a, int256 b) internal pure returns (int256) {
        return _req(_req(a) - _req(b));
    }

    /// Exact or revert: no silent rounding (Axiom W2).
    function mul(int256 a, int256 b) internal pure returns (int256) {
        int256 p = _req(a) * _req(b); // |p| < 2^254: cannot overflow int256
        int256 q = _req(p / SCALE); // overflow is checked before exactness, as in wad18.c
        if (p % SCALE != 0) revert WadNonExact();
        return q;
    }

    /// Exact or revert: no silent rounding (Axiom W2).
    function div(int256 a, int256 b) internal pure returns (int256) {
        _req(b);
        if (b == 0) revert WadDivisionByZero();
        int256 n = _req(a) * SCALE; // |n| < 2^187: cannot overflow int256
        int256 q = _req(n / b); // overflow is checked before exactness, as in wad18.c
        if (n % b != 0) revert WadNonExact();
        return q;
    }
}

/* ------------------------------------------------------------------------- */
/*  Kernel decision semantics — line-for-line port of ssi.c                    */
/* ------------------------------------------------------------------------- */

library SSIKernelLogic {
    uint8 internal constant ACT_POLICY_CHANGE = 9; // last typed action (§8)
    uint32 internal constant PERMIT_MASK = 0x1FFF; // the 13 conditions of §13
    uint32 internal constant PERMIT_REQUIRED = 0x1BFF; // all set except bit 10 (revoked)

    /// VS(X): at least one declared invariant (S1) and every one TRUE (S2).
    function vs(uint256 trueMask, uint8 count) internal pure returns (bool) {
        if (count == 0) return false;
        uint256 need = (uint256(1) << count) - 1;
        return (trueMask & need) == need;
    }

    /// Permit predicate (§13); bit i = condition i in the C struct's order.
    function permit13FromBits(uint32 bits) internal pure returns (bool) {
        return (bits & PERMIT_MASK) == PERMIT_REQUIRED;
    }

    /// Decision (§7, §13, §14, §23).
    function decide(bool arithmeticValid, VerResult v, bool permit) internal pure returns (Decision) {
        if (!arithmeticValid) return Decision.SAFE_STOP; // §7
        if (v == VerResult.UNKNOWN) return Decision.DEFER; // §14: UNKNOWN != PASS
        if (v == VerResult.FAIL) return Decision.REJECT;
        if (!permit) return Decision.REJECT; // §13: only Permit = 1 executes
        return Decision.EXECUTE;
    }

    /// Mediation (§9, §32): untyped actions never produce an external effect.
    function mediate(uint8 kind, bool permit) internal pure returns (bool) {
        if (kind > ACT_POLICY_CHANGE) return false;
        return permit;
    }

    /// CSL authorization (Axiom C1).
    function cslAuth(bool sig, bool revoked, uint64 validUntil, uint64 nowTs, bool inEnvelope)
        internal
        pure
        returns (bool)
    {
        return sig && !revoked && nowTs <= validUntil && inEnvelope;
    }

    /// Directive validity (§10).
    function directiveValid(
        bool sig,
        uint64 issue,
        uint64 expiry,
        uint64 revocationEpoch,
        uint64 nowTs,
        uint64 currentEpoch,
        bool inScope
    ) internal pure returns (bool) {
        return sig && issue <= nowTs && nowTs <= expiry && currentEpoch <= revocationEpoch && inScope;
    }

    /// Capability non-escalation (§17).
    function capabilityOk(uint32 nextCaps, uint32 authorizedCaps, bool governanceApproved)
        internal
        pure
        returns (bool)
    {
        return (nextCaps & ~authorizedCaps) == 0 || governanceApproved;
    }

    /// Non-regression (Def. 24): every invariant TRUE before stays TRUE after.
    function nonRegression(uint256 beforeMask, uint256 afterMask, uint8 count) internal pure returns (bool) {
        uint256 need = (uint256(1) << count) - 1;
        return (beforeMask & ~afterMask & need) == 0;
    }

    /// R³ adoption (Def. 23, §18). Returns 0 if adopted, else the 1-based failing condition.
    function adopt6(
        bool kernelEqual,
        bool safetyProofValid,
        bool authorizationValid,
        bool deploymentCertificateValid,
        bool nonRegressionOk,
        bool capabilityDisclosureValid
    ) internal pure returns (uint8) {
        if (!kernelEqual) return 1;
        if (!safetyProofValid) return 2;
        if (!authorizationValid) return 3;
        if (!deploymentCertificateValid) return 4;
        if (!nonRegressionOk) return 5;
        if (!capabilityDisclosureValid) return 6;
        return 0;
    }

    /// Safety Asset Class lifecycle (§21–§22): the seven legal transitions.
    function canTransition(AssetStatus f, AssetStatus t) internal pure returns (bool) {
        return (f == AssetStatus.PROPOSED && t == AssetStatus.VERIFIED)
            || (f == AssetStatus.PROPOSED && t == AssetStatus.REJECTED)
            || (f == AssetStatus.VERIFIED && t == AssetStatus.ACTIVE)
            || (f == AssetStatus.ACTIVE && t == AssetStatus.REVALIDATION)
            || (f == AssetStatus.REVALIDATION && t == AssetStatus.ACTIVE)
            || (f == AssetStatus.REVALIDATION && t == AssetStatus.REVOKED)
            || (f == AssetStatus.ACTIVE && t == AssetStatus.REVOKED);
    }

    /// VERIFY_SSI (§31): returns 0 on PASS, else the 1-based index of the first failed check.
    function ssiVerify(uint16 checks) internal pure returns (uint8) {
        for (uint8 i = 0; i < 11; i++) {
            if (((checks >> i) & 1) == 0) return i + 1;
        }
        return 0;
    }
}

/* ------------------------------------------------------------------------- */
/*  Domain invariants: autonomous-vehicle control (AV Capsule v2.0, Table I)   */
/* ------------------------------------------------------------------------- */

library AVControlInvariants {
    /// floor(π/2 × 10^18). π/2 is irrational, so the floor is the conservative bound.
    int256 internal constant HALF_PI_WAD = 1570796326794896619;
    int256 internal constant ONE = 1e18;
    int256 internal constant HALF = 5e17;
    uint8 internal constant COUNT = 6; // I1–I6; I7 (audit) is enforced by the ledger itself

    function integrityHash(
        int256 steering,
        int256 throttle,
        int256 brake,
        uint64 tState,
        uint64 tDecision,
        bytes32 purpose
    ) internal pure returns (bytes32) {
        return sha256(abi.encodePacked(steering, throttle, brake, tState, tDecision, purpose));
    }

    /// Returns a mask: bit i set = invariant I(i+1) TRUE.
    function evaluate(
        int256 steering,
        int256 throttle,
        int256 brake,
        uint64 tState,
        uint64 tDecision,
        bytes32 integrity,
        bytes32 purpose
    ) internal pure returns (uint256 tt) {
        if (steering >= -HALF_PI_WAD && steering <= HALF_PI_WAD) tt |= 1; // I1 |θ| ≤ π/2
        if (throttle >= 0 && throttle <= ONE && brake >= 0 && brake <= ONE) tt |= 2; // I2 normalized
        if (!(throttle > HALF && brake > HALF)) tt |= 4; // I3 mutual exclusion
        if (tDecision > tState) tt |= 8; // I4 causality: decision strictly after state
        if (integrity == integrityHash(steering, throttle, brake, tState, tDecision, purpose)) tt |= 16; // I5
        if (purpose != bytes32(0)) tt |= 32; // I6 named purpose
    }
}

/* ------------------------------------------------------------------------- */
/*  The kernel                                                                */
/* ------------------------------------------------------------------------- */

contract SSIVerificationKernel {
    /* ----------------------------- errors -------------------------------- */
    error NotOwner();
    error NotPendingOwner();
    error NotVerifier();
    error NotOwnerOrVerifier();
    error ZeroValue();
    error RoleConflict(address account);
    error AxiomsAlreadySealed();
    error AxiomsNotSealed();
    error AxiomExists(bytes32 id);
    error UnknownAgent(address agent);
    error AgentExists(address agent);
    error AgentClosed(address agent);
    error IllegalTransition(AssetStatus from, AssetStatus to);
    error TransitionNotPermittedForRole(AssetStatus from, AssetStatus to);
    error AlreadyDecided(bytes32 actionHash);
    error AttestationExists(bytes32 actionHash);
    error ProposalExists(bytes32 childKernel);
    error UnknownProposal(bytes32 childKernel);
    error TimelockActive(uint64 readyAt);
    error AdoptionDenied(uint8 failedCondition);
    error InvalidParameter();

    /* ----------------------------- events -------------------------------- */
    event LedgerAppended(uint256 indexed seq, bytes32 indexed entry, bytes32 indexed tag, bytes32 subject, bytes32 data);
    event OwnershipTransferStarted(address indexed from, address indexed to);
    event OwnershipTransferred(address indexed from, address indexed to);
    event VerifierSet(address indexed verifier, bool active);
    event SafeStopSet(bool engaged, address indexed by);
    event AxiomRegistered(bytes32 indexed id, bytes32 contentHash);
    event AxiomsSealed(bytes32 axiomRoot, uint256 count);
    event AgentRegistered(address indexed agent, bytes32 deploymentId, uint32 caps, uint16 kinds, uint64 validUntil);
    event AgentStatusChanged(address indexed agent, AssetStatus from, AssetStatus to, bytes32 certificateHash);
    event EpochAdvanced(uint64 epoch);
    event Attested(bytes32 indexed actionHash, address indexed verifier, VerResult result, bytes32 evidenceHash);
    event ActionDecided(
        bytes32 indexed actionHash, address indexed agent, Decision decision, uint32 permitBits, VerResult verification
    );
    event ExternalEffectPermitted(bytes32 indexed actionHash, address indexed agent, uint8 kind, bytes32 payloadHash);
    event KernelProposed(bytes32 indexed parent, bytes32 indexed child, uint64 readyAt);
    event KernelProofAttested(bytes32 indexed child, address indexed verifier, bytes32 proofHash);
    event KernelAdopted(bytes32 indexed parent, bytes32 indexed child);

    /* ----------------------------- ledger tags --------------------------- */
    bytes32 private constant TAG_GENESIS = "SSI.GENESIS";
    bytes32 private constant TAG_KERNEL = "SSI.KERNEL";
    bytes32 private constant TAG_GOVERNANCE = "SSI.GOVERNANCE";
    bytes32 private constant TAG_AXIOMS = "SSI.AXIOMS";
    bytes32 private constant TAG_AGENT = "SSI.AGENT";
    bytes32 private constant TAG_ATTEST = "SSI.ATTEST";
    bytes32 private constant TAG_ACTION = "SSI.ACTION";
    bytes32 private constant ACTION_DOMAIN = "SSI.ACTION.v1";

    /* ----------------------------- types --------------------------------- */
    struct ActionRequest {
        uint8 kind; // 0 READ … 9 POLICY_CHANGE (§8)
        uint32 requestedCaps; // capability bitmask the action needs (§17)
        bytes32 deploymentId; // deployment the action runs in (§16)
        bytes32 payloadHash; // SHA-256 of the off-chain action payload
        int256[] wadParams; // every numeric parameter, WAD-18
    }

    struct Agent {
        bool registered;
        bool revoked;
        AssetStatus status;
        uint16 allowedKinds; // bit k = action type k permitted (envelope / scope)
        uint32 authorizedCaps;
        uint64 issuedAt;
        uint64 validUntil;
        uint64 revocationEpoch;
        bytes32 deploymentId;
        bytes32 certificateHash;
    }

    struct Attestation {
        address verifier;
        uint64 timestamp;
        VerResult result;
        bool typeOk;
        bool actionSafe;
        uint8 invariantCount;
        uint256 invariantTrueMask;
        bytes32 kernel;
        bytes32 evidenceHash;
    }

    struct KernelProposal {
        bool exists;
        bool executed;
        uint8 invariantCount;
        uint64 readyAt;
        address proofVerifier;
        bytes32 parentKernel;
        bytes32 safetyProof;
        bytes32 deploymentCertificate;
        bytes32 capabilityDisclosure;
        uint256 invariantsBefore;
        uint256 invariantsAfter;
    }

    /* ----------------------------- state --------------------------------- */
    address public owner;
    address public pendingOwner;
    mapping(address => bool) public isVerifier;
    bool public safeStopped;

    uint64 public immutable freshnessWindow; // max age of an attestation, seconds
    uint64 public immutable adoptionDelay; // R³ time lock, seconds

    bytes32 public activeKernel; // reference kernel decision-table fingerprint
    uint64 public currentEpoch;

    mapping(bytes32 => bytes32) public axiomContent; // id => content hash
    bytes32[] public axiomIds;
    bool public axiomsSealed;
    bytes32 public axiomRoot;

    bytes32 public ledgerHead;
    uint256 public ledgerLength;

    mapping(address => Agent) internal agents;
    mapping(bytes32 => Attestation) internal attestations;
    mapping(bytes32 => bool) public decided; // final decisions only (EXECUTE / REJECT)
    mapping(bytes32 => bool) public isAuthorized; // external effect permitted
    mapping(bytes32 => KernelProposal) internal proposals;

    /* ----------------------------- modifiers ----------------------------- */
    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyVerifier() {
        if (!isVerifier[msg.sender]) revert NotVerifier();
        _;
    }

    /* ----------------------------- constructor --------------------------- */
    constructor(bytes32 kernelFingerprint, uint64 freshnessWindowSeconds, uint64 adoptionDelaySeconds) {
        if (kernelFingerprint == bytes32(0) || freshnessWindowSeconds == 0 || adoptionDelaySeconds == 0) {
            revert ZeroValue();
        }
        owner = msg.sender;
        freshnessWindow = freshnessWindowSeconds;
        adoptionDelay = adoptionDelaySeconds;
        activeKernel = kernelFingerprint;
        ledgerHead = sha256(abi.encodePacked(TAG_GENESIS, block.chainid, address(this)));
        _append(TAG_KERNEL, kernelFingerprint, bytes32(uint256(uint160(msg.sender))));
        emit OwnershipTransferred(address(0), msg.sender);
    }

    /* ======================= governance ================================= */

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroValue();
        if (isVerifier[newOwner] || agents[newOwner].registered) revert RoleConflict(newOwner);
        pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner, newOwner);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotPendingOwner();
        if (isVerifier[msg.sender] || agents[msg.sender].registered) revert RoleConflict(msg.sender);
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
        _append(TAG_GOVERNANCE, "OWNER", bytes32(uint256(uint160(msg.sender))));
    }

    function setVerifier(address verifier, bool active) external onlyOwner {
        if (verifier == address(0)) revert ZeroValue();
        if (active && (verifier == owner || verifier == pendingOwner || agents[verifier].registered)) {
            revert RoleConflict(verifier);
        }
        isVerifier[verifier] = active;
        emit VerifierSet(verifier, active);
        _append(TAG_GOVERNANCE, active ? bytes32("VERIFIER+") : bytes32("VERIFIER-"), bytes32(uint256(uint160(verifier))));
    }

    /// Any verifier or the owner may ENGAGE safe stop; only the owner may RELEASE it.
    function setSafeStop(bool engaged) external {
        if (engaged) {
            if (msg.sender != owner && !isVerifier[msg.sender]) revert NotOwnerOrVerifier();
        } else if (msg.sender != owner) {
            revert NotOwner();
        }
        safeStopped = engaged;
        emit SafeStopSet(engaged, msg.sender);
        _append(TAG_GOVERNANCE, engaged ? bytes32("SAFE_STOP+") : bytes32("SAFE_STOP-"), bytes32(uint256(uint160(msg.sender))));
    }

    /// Revokes every directive issued before now; agents must be renewed (§10).
    function advanceEpoch() external onlyOwner {
        currentEpoch += 1;
        emit EpochAdvanced(currentEpoch);
        _append(TAG_GOVERNANCE, "EPOCH", bytes32(uint256(currentEpoch)));
    }

    /* ======================= axioms ===================================== */

    function registerAxiom(bytes32 id, bytes32 contentHash) external onlyOwner {
        if (axiomsSealed) revert AxiomsAlreadySealed();
        if (id == bytes32(0) || contentHash == bytes32(0)) revert ZeroValue();
        if (axiomContent[id] != bytes32(0)) revert AxiomExists(id);
        axiomContent[id] = contentHash;
        axiomIds.push(id);
        emit AxiomRegistered(id, contentHash);
        _append(TAG_AXIOMS, id, contentHash);
    }

    /// Seals the axiom set forever. Nothing can attest or act until this is done.
    function sealAxioms() external onlyOwner {
        if (axiomsSealed) revert AxiomsAlreadySealed();
        uint256 n = axiomIds.length;
        if (n == 0) revert ZeroValue();
        bytes memory packed;
        for (uint256 i = 0; i < n; i++) {
            packed = abi.encodePacked(packed, axiomIds[i], axiomContent[axiomIds[i]]);
        }
        axiomRoot = sha256(packed);
        axiomsSealed = true;
        emit AxiomsSealed(axiomRoot, n);
        _append(TAG_AXIOMS, "SEALED", axiomRoot);
    }

    function axiomCount() external view returns (uint256) {
        return axiomIds.length;
    }

    /* ======================= agents (Safety Asset Class) ================ */

    function registerAgent(
        address agent,
        uint32 authorizedCaps,
        uint16 allowedKinds,
        bytes32 deploymentId,
        uint64 validUntil
    ) external onlyOwner {
        if (agent == address(0) || deploymentId == bytes32(0)) revert ZeroValue();
        if (agents[agent].registered) revert AgentExists(agent);
        if (agent == owner || agent == pendingOwner || isVerifier[agent]) revert RoleConflict(agent);
        if (allowedKinds >> 10 != 0 || validUntil <= block.timestamp) revert InvalidParameter();
        agents[agent] = Agent({
            registered: true,
            revoked: false,
            status: AssetStatus.PROPOSED,
            allowedKinds: allowedKinds,
            authorizedCaps: authorizedCaps,
            issuedAt: uint64(block.timestamp),
            validUntil: validUntil,
            revocationEpoch: currentEpoch,
            deploymentId: deploymentId,
            certificateHash: bytes32(0)
        });
        emit AgentRegistered(agent, deploymentId, authorizedCaps, allowedKinds, validUntil);
        _append(TAG_AGENT, bytes32(uint256(uint160(agent))), deploymentId);
    }

    /// Re-issues an agent's directive in the current epoch.
    function renewAgent(address agent, uint64 validUntil) external onlyOwner {
        Agent storage ag = agents[agent];
        if (!ag.registered) revert UnknownAgent(agent);
        if (ag.revoked || ag.status == AssetStatus.REJECTED) revert AgentClosed(agent);
        if (validUntil <= block.timestamp) revert InvalidParameter();
        ag.issuedAt = uint64(block.timestamp);
        ag.validUntil = validUntil;
        ag.revocationEpoch = currentEpoch;
        _append(TAG_AGENT, bytes32(uint256(uint160(agent))), "RENEWED");
    }

    /// Lifecycle transitions with separation of duties:
    ///   verifiers: PROPOSED→VERIFIED (with certificate), PROPOSED→REJECTED, ACTIVE→REVALIDATION
    ///   owner:     VERIFIED→ACTIVE, REVALIDATION→ACTIVE, REVALIDATION→REVOKED, ACTIVE→REVOKED
    function transitionAgent(address agent, AssetStatus to, bytes32 certificateHash) external {
        Agent storage ag = agents[agent];
        if (!ag.registered) revert UnknownAgent(agent);
        AssetStatus from = ag.status;
        if (!SSIKernelLogic.canTransition(from, to)) revert IllegalTransition(from, to);

        bool verifierMove = (from == AssetStatus.PROPOSED) || (from == AssetStatus.ACTIVE && to == AssetStatus.REVALIDATION);
        if (verifierMove) {
            if (!isVerifier[msg.sender]) revert TransitionNotPermittedForRole(from, to);
        } else if (msg.sender != owner) {
            revert TransitionNotPermittedForRole(from, to);
        }

        if (to == AssetStatus.VERIFIED) {
            if (certificateHash == bytes32(0)) revert ZeroValue();
            ag.certificateHash = certificateHash;
        }
        if (to == AssetStatus.REVOKED) ag.revoked = true;
        ag.status = to;
        emit AgentStatusChanged(agent, from, to, ag.certificateHash);
        _append(TAG_AGENT, bytes32(uint256(uint160(agent))), bytes32(uint256(uint8(to))));
    }

    /* ======================= verification ============================== */

    /// A verifier runs the reference kernel off-chain on the action and records the result.
    function attest(
        bytes32 actionHash,
        VerResult result,
        bool typeOk,
        bool actionSafe,
        uint8 invariantCount,
        uint256 invariantTrueMask,
        bytes32 evidenceHash
    ) external onlyVerifier {
        if (!axiomsSealed) revert AxiomsNotSealed();
        if (actionHash == bytes32(0) || evidenceHash == bytes32(0)) revert ZeroValue();
        if (decided[actionHash]) revert AlreadyDecided(actionHash);
        Attestation storage at = attestations[actionHash];
        // An existing attestation can only be replaced if its verifier has since been removed.
        if (at.verifier != address(0) && isVerifier[at.verifier]) revert AttestationExists(actionHash);
        attestations[actionHash] = Attestation({
            verifier: msg.sender,
            timestamp: uint64(block.timestamp),
            result: result,
            typeOk: typeOk,
            actionSafe: actionSafe,
            invariantCount: invariantCount,
            invariantTrueMask: invariantTrueMask,
            kernel: activeKernel,
            evidenceHash: evidenceHash
        });
        emit Attested(actionHash, msg.sender, result, evidenceHash);
        _append(TAG_ATTEST, actionHash, evidenceHash);
    }

    /// The hash a verifier attests to. Binds agent, nonce, chain and this contract.
    function computeActionHash(address agent, uint256 nonce, ActionRequest calldata req)
        external
        view
        returns (bytes32)
    {
        return _actionHash(agent, nonce, req);
    }

    /// Every action of the intelligent system passes through here.
    /// EXECUTE and REJECT are final; DEFER and SAFE_STOP may be resubmitted later.
    function submitAction(ActionRequest calldata req, uint256 nonce) external returns (Decision d) {
        Agent storage ag = agents[msg.sender];
        if (!ag.registered) revert UnknownAgent(msg.sender);
        bytes32 h = _actionHash(msg.sender, nonce, req);
        if (decided[h]) revert AlreadyDecided(h);

        Attestation storage at = attestations[h];
        bool hasAttestation = at.verifier != address(0) && isVerifier[at.verifier];
        VerResult v = hasAttestation ? at.result : VerResult.UNKNOWN;

        uint32 bits = _permitBits(ag, at, hasAttestation, req);
        bool permit = SSIKernelLogic.permit13FromBits(bits);

        if (safeStopped) {
            d = Decision.SAFE_STOP;
        } else {
            d = SSIKernelLogic.decide(_arithmeticValid(req.wadParams), v, permit);
        }
        _finalize(h, d, bits, v, req);
    }

    /* ======================= R³ kernel adoption ========================= */

    function proposeKernel(
        bytes32 childKernel,
        bytes32 deploymentCertificate,
        bytes32 capabilityDisclosure,
        uint8 invariantCount,
        uint256 invariantsBefore,
        uint256 invariantsAfter
    ) external onlyOwner {
        if (childKernel == bytes32(0) || childKernel == activeKernel) revert ZeroValue();
        if (invariantCount == 0) revert InvalidParameter();
        if (proposals[childKernel].exists) revert ProposalExists(childKernel);
        uint64 readyAt = uint64(block.timestamp) + adoptionDelay;
        proposals[childKernel] = KernelProposal({
            exists: true,
            executed: false,
            invariantCount: invariantCount,
            readyAt: readyAt,
            proofVerifier: address(0),
            parentKernel: activeKernel,
            safetyProof: bytes32(0),
            deploymentCertificate: deploymentCertificate,
            capabilityDisclosure: capabilityDisclosure,
            invariantsBefore: invariantsBefore,
            invariantsAfter: invariantsAfter
        });
        emit KernelProposed(activeKernel, childKernel, readyAt);
        _append(TAG_KERNEL, childKernel, "PROPOSED");
    }

    function attestKernelProof(bytes32 childKernel, bytes32 proofHash) external onlyVerifier {
        KernelProposal storage p = proposals[childKernel];
        if (!p.exists || p.executed) revert UnknownProposal(childKernel);
        if (proofHash == bytes32(0)) revert ZeroValue();
        p.safetyProof = proofHash;
        p.proofVerifier = msg.sender;
        emit KernelProofAttested(childKernel, msg.sender, proofHash);
        _append(TAG_KERNEL, childKernel, proofHash);
    }

    function adoptKernel(bytes32 childKernel) external onlyOwner {
        KernelProposal storage p = proposals[childKernel];
        if (!p.exists || p.executed) revert UnknownProposal(childKernel);
        if (block.timestamp < p.readyAt) revert TimelockActive(p.readyAt);
        uint8 failed = SSIKernelLogic.adopt6(
            p.parentKernel == activeKernel,
            p.safetyProof != bytes32(0) && isVerifier[p.proofVerifier],
            true, // authorization: onlyOwner, after the time lock
            p.deploymentCertificate != bytes32(0),
            SSIKernelLogic.nonRegression(p.invariantsBefore, p.invariantsAfter, p.invariantCount),
            p.capabilityDisclosure != bytes32(0)
        );
        if (failed != 0) revert AdoptionDenied(failed);
        bytes32 parent = activeKernel;
        p.executed = true;
        activeKernel = childKernel;
        emit KernelAdopted(parent, childKernel);
        _append(TAG_KERNEL, childKernel, parent);
    }

    /* ======================= views ===================================== */

    function getAgent(address agent) external view returns (Agent memory) {
        return agents[agent];
    }

    function getAttestation(bytes32 actionHash) external view returns (Attestation memory) {
        return attestations[actionHash];
    }

    function getProposal(bytes32 childKernel) external view returns (KernelProposal memory) {
        return proposals[childKernel];
    }

    /* ======================= pure reference functions =================== */

    /// VERIFY_SSI (§31): bit i = check i (TYPE … SUPERINTELLIGENCE_CRITERION).
    function verifySSI(uint16 checks) external pure returns (bool pass, uint8 firstFailed) {
        firstFailed = SSIKernelLogic.ssiVerify(checks);
        pass = firstFailed == 0;
    }

    function permitFromBits(uint32 bits) external pure returns (bool) {
        return SSIKernelLogic.permit13FromBits(bits);
    }

    function decideReference(bool arithmeticValid, VerResult v, bool permit) external pure returns (Decision) {
        return SSIKernelLogic.decide(arithmeticValid, v, permit);
    }

    function wadMul(int256 a, int256 b) external pure returns (int256) {
        return WAD18.mul(a, b);
    }

    function wadDiv(int256 a, int256 b) external pure returns (int256) {
        return WAD18.div(a, b);
    }

    /// AV Capsule invariants I1–I6 for a proposed control input.
    function evaluateAVControl(
        int256 steering,
        int256 throttle,
        int256 brake,
        uint64 tState,
        uint64 tDecision,
        bytes32 integrity,
        bytes32 purpose
    ) external pure returns (uint256 trueMask, uint8 count, bool allTrue) {
        trueMask = AVControlInvariants.evaluate(steering, throttle, brake, tState, tDecision, integrity, purpose);
        count = AVControlInvariants.COUNT;
        allTrue = SSIKernelLogic.vs(trueMask, count);
    }

    function avIntegrityHash(
        int256 steering,
        int256 throttle,
        int256 brake,
        uint64 tState,
        uint64 tDecision,
        bytes32 purpose
    ) external pure returns (bytes32) {
        return AVControlInvariants.integrityHash(steering, throttle, brake, tState, tDecision, purpose);
    }

    /* ======================= internals ================================= */

    function _actionHash(address agent, uint256 nonce, ActionRequest calldata req) internal view returns (bytes32) {
        return sha256(
            abi.encode(
                ACTION_DOMAIN,
                block.chainid,
                address(this),
                agent,
                nonce,
                req.kind,
                req.requestedCaps,
                req.deploymentId,
                req.payloadHash,
                req.wadParams
            )
        );
    }

    function _arithmeticValid(int256[] calldata params) internal pure returns (bool) {
        for (uint256 i = 0; i < params.length; i++) {
            if (!WAD18.inRange(params[i])) return false;
        }
        return true;
    }

    function _bit(bool condition, uint8 position) private pure returns (uint32) {
        return condition ? uint32(1) << position : uint32(0);
    }

    /// The 13 Permit conditions of §13, bit i in the C kernel's declaration order.
    function _permitBits(
        Agent storage ag,
        Attestation storage at,
        bool hasAttestation,
        ActionRequest calldata req
    ) internal view returns (uint32 bits) {
        uint64 nowTs = uint64(block.timestamp);
        bool wellTyped = req.kind <= SSIKernelLogic.ACT_POLICY_CHANGE;
        bool inScope = wellTyped && ((ag.allowedKinds >> req.kind) & 1) == 1;

        bits |= _bit(hasAttestation && at.typeOk, 0); // type_ok
        bits |= _bit(wellTyped, 1); // action_well_typed
        bits |= _bit(_cslValid(ag, nowTs, inScope), 2); // csl_valid
        bits |= _bit(_directiveValid(ag, nowTs, inScope), 3); // authorized
        bits |= _bit(SSIKernelLogic.capabilityOk(req.requestedCaps, ag.authorizedCaps, false), 4); // capability_valid
        bits |= _bit(hasAttestation && SSIKernelLogic.vs(at.invariantTrueMask, at.invariantCount), 5); // safety_inv
        bits |= _bit(hasAttestation && at.actionSafe, 6); // action_safe
        bits |= _bit(hasAttestation && axiomsSealed && at.kernel == activeKernel, 7); // evidence_valid
        bits |= _bit(
            ag.certificateHash != bytes32(0) && req.deploymentId == ag.deploymentId, 8
        ); // deployment_bound
        bits |= _bit(ag.status == AssetStatus.ACTIVE, 9); // current
        bits |= _bit(ag.revoked, 10); // revoked
        bits |= _bit(inScope, 11); // within_scope
        bits |= _bit(hasAttestation && uint256(nowTs) <= uint256(at.timestamp) + freshnessWindow, 12); // fresh
    }

    function _cslValid(Agent storage ag, uint64 nowTs, bool inScope) private view returns (bool) {
        return SSIKernelLogic.cslAuth(true, ag.revoked, ag.validUntil, nowTs, inScope);
    }

    function _directiveValid(Agent storage ag, uint64 nowTs, bool inScope) private view returns (bool) {
        return SSIKernelLogic.directiveValid(
            true, ag.issuedAt, ag.validUntil, ag.revocationEpoch, nowTs, currentEpoch, inScope
        );
    }

    function _finalize(bytes32 h, Decision d, uint32 bits, VerResult v, ActionRequest calldata req) internal {
        if (d == Decision.EXECUTE || d == Decision.REJECT) decided[h] = true;
        bool effect = SSIKernelLogic.mediate(req.kind, d == Decision.EXECUTE);
        if (effect) isAuthorized[h] = true;

        bytes32 record = sha256(abi.encodePacked(msg.sender, uint8(d), bits, uint8(v), req.payloadHash));
        _append(TAG_ACTION, h, record);
        emit ActionDecided(h, msg.sender, d, bits, v);
        if (effect) emit ExternalEffectPermitted(h, msg.sender, req.kind, req.payloadHash);
    }

    /// Cognitive State Ledger: append-only SHA-256 hash chain.
    /// entry_n = SHA256(entry_{n-1} ‖ n ‖ tag ‖ subject ‖ data ‖ block.number)
    function _append(bytes32 tag, bytes32 subject, bytes32 data) private {
        uint256 seq = ledgerLength;
        bytes32 entry = sha256(abi.encodePacked(ledgerHead, seq, tag, subject, data, block.number));
        ledgerHead = entry;
        ledgerLength = seq + 1;
        emit LedgerAppended(seq, entry, tag, subject, data);
    }
}
