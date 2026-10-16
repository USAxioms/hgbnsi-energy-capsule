// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.24;

/*
 * HUMAN-GUIDED BLOCKCHAIN-NATIVE SAFE SUPERINTELLIGENCE (HGBNSI)
 * Job router — a domain module of the SSI Verification Kernel.
 *
 * Flow:
 *   1. The human guide submits a job from the Sovereign Axiomatic Front End.
 *   2. A kernel verifier grants or denies permission.
 *   3. LIGHT jobs are solved by the front end itself; HEAVY jobs receive an
 *      ExecutionCommand that a registered processor (e.g. photonic) pulls.
 *   4. Whoever solves it submits the result here, and THIS CONTRACT checks it
 *      exactly in WAD-18. A processor is never trusted: an analog or approximate
 *      answer that is not exactly valid is rejected.
 *   5. The front end reads the accepted result, re-checks it, executes it, and
 *      records an execution report.
 *
 * Job type: grid dispatch. Specification (flat int256 array, WAD-18 except the count):
 *   spec[0] demand (> 0)        spec[1] cost ceiling (≥ 0)      spec[2] n generators (1..32, plain integer)
 *   then per generator i:  capacity, minimum output when on, marginal cost per unit, fixed cost when on
 * A plan is n outputs. It is valid iff every output is 0 or within [minimum, capacity],
 * outputs sum EXACTLY to demand, every cost product is exact at 18 decimals, and the
 * total cost (Σ fixed_i + marginal_i·output_i over running generators) ≤ ceiling.
 * The contract verifies validity, not optimality: optimality is not checkable cheaply.
 *
 * STATUS: written without access to a Solidity compiler. Compile, test on a testnet,
 * and obtain an independent audit before mainnet deployment.
 */

interface ISSIVerificationKernelForJobs {
    function owner() external view returns (address);
    function isVerifier(address account) external view returns (bool);
    function safeStopped() external view returns (bool);
}

contract HGBNSIJobRouter {
    /* ----------------------------- types --------------------------------- */
    enum Weight { LIGHT, HEAVY }
    enum JobStatus { NONE, REQUESTED, PERMITTED, DENIED, COMPLETED, FAILED, EXECUTED }

    struct Job {
        JobStatus status;
        Weight weight;
        uint8 attempts;
        uint8 lastReason;
        uint64 deadline;
        address requester;
        address solver;
        bytes32 specHash;
        bytes32 planHash;
        int256 cost;
        bytes32 reportHash;
    }

    /* ----------------------------- constants ----------------------------- */
    int256 public constant WAD = 1e18;
    int256 private constant WAD_MAX = int256(type(int128).max);
    uint256 public constant MAX_GENERATORS = 32;
    uint8 public constant MAX_ATTEMPTS = 3;

    // Result-check reason codes (0 = valid).
    uint8 public constant R_OK = 0;
    uint8 public constant R_LENGTH = 1; // plan length differs from n
    uint8 public constant R_RANGE = 2; // output negative or outside WAD range
    uint8 public constant R_BELOW_MIN = 3; // running below its minimum
    uint8 public constant R_ABOVE_CAP = 4; // above capacity
    uint8 public constant R_NON_EXACT = 5; // a cost product is not exact at 18 decimals
    uint8 public constant R_DEMAND = 6; // outputs do not sum exactly to demand
    uint8 public constant R_CEILING = 7; // total cost above the ceiling

    bytes32 private constant TAG_GENESIS = "HGBNSI.JOBS.GENESIS";
    bytes32 private constant TAG_SUBMIT = "HGBNSI.JOBS.SUBMIT";
    bytes32 private constant TAG_PERMIT = "HGBNSI.JOBS.PERMIT";
    bytes32 private constant TAG_RESULT = "HGBNSI.JOBS.RESULT";
    bytes32 private constant TAG_EXECUTE = "HGBNSI.JOBS.EXECUTE";
    bytes32 private constant TAG_PROCESSOR = "HGBNSI.JOBS.PROCESSOR";

    /* ----------------------------- errors -------------------------------- */
    error NotHumanGuide();
    error NotVerifier();
    error SafeStopped();
    error ZeroValue();
    error RoleConflict(address account);
    error BadSpec(uint8 code);
    error BadDeadline();
    error UnknownJob(uint256 jobId);
    error WrongStatus(uint256 jobId, JobStatus status);
    error DeadlinePassed(uint256 jobId);
    error NotSolver(uint256 jobId, address caller);
    error SpecMismatch(uint256 jobId);
    error NotRequester(uint256 jobId);

    /* ----------------------------- events -------------------------------- */
    event LedgerAppended(uint256 indexed seq, bytes32 indexed entry, bytes32 indexed tag, bytes32 subject, bytes32 data);
    event ProcessorSet(address indexed processor, bool active);
    event JobSubmitted(uint256 indexed jobId, bytes32 specHash, uint8 weight, uint64 deadline, int256[] spec);
    event JobPermitted(uint256 indexed jobId, address indexed verifier, bool approved, bytes32 reasonHash);
    event ExecutionCommand(uint256 indexed jobId, bytes32 specHash);
    event ResultAccepted(uint256 indexed jobId, address indexed solver, bytes32 planHash, int256 cost, int256[] plan);
    event ResultRejected(uint256 indexed jobId, address indexed solver, uint8 reason, uint8 attempts);
    event JobExecuted(uint256 indexed jobId, bytes32 reportHash);

    /* ----------------------------- state --------------------------------- */
    ISSIVerificationKernelForJobs public immutable kernel;
    mapping(address => bool) public isProcessor;
    uint256 public jobCount;
    mapping(uint256 => Job) internal jobs;
    bytes32 public ledgerHead;
    uint256 public ledgerLength;

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

    constructor(address ssiKernel) {
        if (ssiKernel == address(0)) revert ZeroValue();
        kernel = ISSIVerificationKernelForJobs(ssiKernel);
        ledgerHead = sha256(abi.encodePacked(TAG_GENESIS, block.chainid, address(this), ssiKernel));
    }

    /* ======================= processors (human guide) ==================== */

    /// A processor must be neither the human guide nor a verifier.
    function setProcessor(address processor, bool active) external onlyHumanGuide {
        if (processor == address(0)) revert ZeroValue();
        if (active && (processor == kernel.owner() || kernel.isVerifier(processor))) revert RoleConflict(processor);
        isProcessor[processor] = active;
        emit ProcessorSet(processor, active);
        _append(TAG_PROCESSOR, bytes32(uint256(uint160(processor))), active ? bytes32(uint256(1)) : bytes32(0));
    }

    /* ======================= 1. submit ================================== */

    function submitJob(int256[] calldata spec, Weight weight, uint64 deadline)
        external
        onlyHumanGuide
        notStopped
        returns (uint256 jobId)
    {
        _validateSpec(spec);
        if (deadline <= block.timestamp) revert BadDeadline();
        bytes32 specHash = sha256(abi.encodePacked(spec));
        jobId = ++jobCount;
        Job storage j = jobs[jobId];
        j.status = JobStatus.REQUESTED;
        j.weight = weight;
        j.deadline = deadline;
        j.requester = msg.sender;
        j.specHash = specHash;
        emit JobSubmitted(jobId, specHash, uint8(weight), deadline, spec);
        _append(TAG_SUBMIT, bytes32(jobId), specHash);
    }

    /* ======================= 2. permission ============================== */

    function permitJob(uint256 jobId, bool approve, bytes32 reasonHash) external onlyVerifier notStopped {
        Job storage j = _job(jobId);
        if (j.status != JobStatus.REQUESTED) revert WrongStatus(jobId, j.status);
        if (reasonHash == bytes32(0)) revert ZeroValue();
        if (block.timestamp > j.deadline) revert DeadlinePassed(jobId);
        j.status = approve ? JobStatus.PERMITTED : JobStatus.DENIED;
        emit JobPermitted(jobId, msg.sender, approve, reasonHash);
        _append(TAG_PERMIT, bytes32(jobId), reasonHash);
        if (approve && j.weight == Weight.HEAVY) emit ExecutionCommand(jobId, j.specHash); // 3. command
    }

    /* ======================= 4. results, checked exactly ================ */

    function submitResult(uint256 jobId, int256[] calldata spec, int256[] calldata plan)
        external
        notStopped
        returns (uint8 reason)
    {
        Job storage j = _job(jobId);
        if (j.status != JobStatus.PERMITTED) revert WrongStatus(jobId, j.status);
        if (block.timestamp > j.deadline) revert DeadlinePassed(jobId);
        bool allowed = j.weight == Weight.LIGHT ? msg.sender == j.requester : isProcessor[msg.sender];
        if (!allowed) revert NotSolver(jobId, msg.sender);
        if (sha256(abi.encodePacked(spec)) != j.specHash) revert SpecMismatch(jobId);

        int256 cost;
        (reason, cost) = checkPlan(spec, plan);
        j.attempts += 1;
        j.lastReason = reason;
        if (reason == R_OK) {
            j.status = JobStatus.COMPLETED;
            j.solver = msg.sender;
            j.planHash = sha256(abi.encodePacked(plan));
            j.cost = cost;
            emit ResultAccepted(jobId, msg.sender, j.planHash, cost, plan);
            _append(TAG_RESULT, bytes32(jobId), j.planHash);
        } else {
            if (j.attempts >= MAX_ATTEMPTS) j.status = JobStatus.FAILED;
            emit ResultRejected(jobId, msg.sender, reason, j.attempts);
            _append(TAG_RESULT, bytes32(jobId), bytes32(uint256(reason)));
        }
    }

    /* ======================= 5. execution report ======================== */

    /// True only for an accepted plan with this exact fingerprint, while the system is running.
    function isExecutable(uint256 jobId, bytes32 planHash) external view returns (bool) {
        Job storage j = jobs[jobId];
        return j.status == JobStatus.COMPLETED && j.planHash == planHash && !kernel.safeStopped();
    }

    function markExecuted(uint256 jobId, bytes32 reportHash) external notStopped {
        Job storage j = _job(jobId);
        if (msg.sender != j.requester) revert NotRequester(jobId);
        if (j.status != JobStatus.COMPLETED) revert WrongStatus(jobId, j.status);
        if (reportHash == bytes32(0)) revert ZeroValue();
        j.status = JobStatus.EXECUTED;
        j.reportHash = reportHash;
        emit JobExecuted(jobId, reportHash);
        _append(TAG_EXECUTE, bytes32(jobId), reportHash);
    }

    /* ======================= views and pure checks ====================== */

    function getJob(uint256 jobId) external view returns (Job memory) {
        return jobs[jobId];
    }

    function specHashOf(int256[] calldata spec) external pure returns (bytes32) {
        return sha256(abi.encodePacked(spec));
    }

    /// The exact validity check. Public so anyone can dry-run a plan before submitting.
    function checkPlan(int256[] calldata spec, int256[] calldata plan) public pure returns (uint8 reason, int256 cost) {
        uint256 n = uint256(spec[2]);
        if (plan.length != n) return (R_LENGTH, 0);
        int256 total;
        for (uint256 i = 0; i < n; i++) {
            int256 p = plan[i];
            if (p < 0 || p > WAD_MAX) return (R_RANGE, 0);
            if (p == 0) continue; // generator off
            uint256 b = 3 + 4 * i;
            if (p < spec[b + 1]) return (R_BELOW_MIN, 0);
            if (p > spec[b]) return (R_ABOVE_CAP, 0);
            int256 product = spec[b + 2] * p; // both ≤ 2^127: cannot overflow int256
            if (product % WAD != 0) return (R_NON_EXACT, 0);
            total += p;
            cost += spec[b + 3] + product / WAD;
        }
        if (total != spec[0]) return (R_DEMAND, 0);
        if (cost > spec[1]) return (R_CEILING, cost);
        return (R_OK, cost);
    }

    /* ======================= internals ================================= */

    function _validateSpec(int256[] calldata s) internal pure {
        if (s.length < 7) revert BadSpec(1);
        int256 count = s[2];
        if (count < 1 || count > int256(MAX_GENERATORS)) revert BadSpec(2);
        uint256 n = uint256(count);
        if (s.length != 3 + 4 * n) revert BadSpec(3);
        if (s[0] <= 0 || s[0] > WAD_MAX) revert BadSpec(4);
        if (s[1] < 0 || s[1] > WAD_MAX) revert BadSpec(5);
        for (uint256 i = 0; i < n; i++) {
            uint256 b = 3 + 4 * i;
            for (uint256 k = 0; k < 4; k++) {
                if (s[b + k] < 0 || s[b + k] > WAD_MAX) revert BadSpec(6);
            }
            if (s[b] == 0 || s[b + 1] > s[b]) revert BadSpec(7);
        }
    }

    function _job(uint256 jobId) internal view returns (Job storage j) {
        j = jobs[jobId];
        if (j.status == JobStatus.NONE) revert UnknownJob(jobId);
    }

    function _append(bytes32 tag, bytes32 subject, bytes32 data) private {
        uint256 seq = ledgerLength;
        bytes32 entry = sha256(abi.encodePacked(ledgerHead, seq, tag, subject, data, block.number));
        ledgerHead = entry;
        ledgerLength = seq + 1;
        emit LedgerAppended(seq, entry, tag, subject, data);
    }
}
