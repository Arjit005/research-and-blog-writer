"""Integration tests for multi-process concurrency, true cross-process claims, and worker lease recovery."""

import multiprocessing
import os
import time
import pytest
import database as db

def _worker_attempt_claim(user_id: int, topic: str, barrier, result_queue, db_path: str):
    """Independent worker process entry point with its own connection and memory space."""
    os.environ["RESEARCH_STUDIO_DB_PATH"] = db_path
    import database as worker_db
    import uuid

    run_id = f"proc_run_{uuid.uuid4().hex[:8]}"
    worker_id = f"proc_{os.getpid()}"

    # Wait for all processes to synchronize at the starting line
    barrier.wait()

    # Attempt atomic creation simultaneously
    created, active_id = worker_db.create_research_job_atomic(
        run_id=run_id,
        topic=topic,
        user_id=user_id,
        worker_id=worker_id,
    )
    result_queue.put({
        "pid": os.getpid(),
        "run_id": run_id,
        "created": created,
        "active_id": active_id,
    })


def test_multi_process_concurrency_with_independent_workers(tmp_path):
    """Test using 4 independent application worker processes with independent memory and DB connections."""
    test_db = str(tmp_path / "multiprocess_test.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    target_user_id = 4242
    num_workers = 4

    # Setup multiprocessing primitives
    barrier = multiprocessing.Barrier(num_workers)
    result_queue = multiprocessing.Queue()

    processes = []
    for _ in range(num_workers):
        p = multiprocessing.Process(
            target=_worker_attempt_claim,
            args=(target_user_id, "Distributed Consensus Systems", barrier, result_queue, test_db),
        )
        processes.append(p)
        p.start()

    for p in processes:
        p.join(timeout=10)

    # Collect outcomes
    results = []
    while not result_queue.empty():
        results.append(result_queue.get_nowait())

    assert len(results) == num_workers

    created_runs = [r for r in results if r["created"]]
    rejected_runs = [r for r in results if not r["created"]]

    # CRITICAL INVARIANT: Exactly 1 worker process creates the job
    assert len(created_runs) == 1, f"Expected exactly 1 created job, got {len(created_runs)}"
    assert len(rejected_runs) == num_workers - 1, f"Expected {num_workers - 1} rejections, got {len(rejected_runs)}"

    winning_run_id = created_runs[0]["run_id"]

    # All rejected workers must have identified the winning run_id
    for rejected in rejected_runs:
        assert rejected["active_id"] == winning_run_id

    # Verify claim in active_run_claims table
    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT user_id, run_id FROM active_run_claims WHERE user_id = ?", (target_user_id,))
        claim = cur.fetchone()
        assert claim is not None
        assert claim["run_id"] if is_tidb else claim[1] == winning_run_id

    # Test release on completion
    db.update_research_job(winning_run_id, status="completed")
    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT user_id FROM active_run_claims WHERE user_id = ?", (target_user_id,))
        assert cur.fetchone() is None, "Claim should be deleted once job reaches terminal status"


def test_worker_recovery_does_not_abort_healthy_active_jobs(tmp_path):
    """Test that recover_interrupted_jobs does not terminate running jobs with fresh heartbeats."""
    test_db = str(tmp_path / "recovery_test.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 5555
    run_id = "run_healthy_active_1"
    worker_id = "worker_alpha"

    created, _ = db.create_research_job_atomic(run_id, "Active Job", user_id=user_id, worker_id=worker_id)
    assert created is True

    # Job is fresh (heartbeat just written)
    recovered = db.recover_interrupted_jobs(stale_after_seconds=60)
    assert recovered == 0, "Healthy job within lease period must NOT be recovered"

    job = db.get_research_job(run_id)
    assert job["status"] == "pending"

    # Simulate heartbeat update
    heartbeat_ok = db.heartbeat_active_run_claim(run_id, worker_id=worker_id)
    assert heartbeat_ok is True



def test_fencing_token_and_conditional_lease_renewal(tmp_path):
    """Test that a worker cannot renew or modify a claim after losing ownership."""
    test_db = str(tmp_path / "fencing_test.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 8888
    run_id = "run_fenced_1"
    worker_a = "worker_alpha"
    worker_b = "worker_beta_stale"

    created, _ = db.create_research_job_atomic(run_id, "Fencing test", user_id=user_id, worker_id=worker_a)
    assert created is True

    # Get initial fencing token
    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT fencing_token, lease_token FROM active_run_claims WHERE user_id = ?", (user_id,))
        claim = cur.fetchone()
        initial_token = claim["fencing_token"] if is_tidb else claim[0]
        lease_token = claim["lease_token"] if is_tidb else claim[1]
        assert initial_token == 1

    # Valid worker renews lease
    renew_ok = db.heartbeat_active_run_claim(run_id, worker_id=worker_a, lease_token=lease_token)
    assert renew_ok is True

    # In accordance with correct fencing token semantics, heartbeat updates heartbeat_at
    # while preserving the fencing token (token changes only on new lease acquisition)
    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT fencing_token FROM active_run_claims WHERE user_id = ?", (user_id,))
        claim = cur.fetchone()
        current_token = claim["fencing_token"] if is_tidb else claim[0]
        assert current_token == 1

    # Stale/unauthorized worker attempt fails
    unauthorized_renew = db.heartbeat_active_run_claim(run_id, worker_id=worker_b, lease_token=lease_token)
    assert unauthorized_renew is False

    # Invalid lease token attempt fails
    invalid_token_renew = db.heartbeat_active_run_claim(run_id, worker_id=worker_a, lease_token="fake_lease_token")
    assert invalid_token_renew is False



def test_stale_worker_rejection_scenario(tmp_path):
    """Test exact stale worker failure sequence:
    1. Worker A acquires lease with fencing token (e.g. 41).
    2. Worker A stops sending heartbeats.
    3. Lease expires / is pruned.
    4. Worker B acquires a new lease with incremented fencing token (e.g. 42).
    5. Stale Worker A resumes and attempts to mutate DB or release claim.
    6. All stale Worker A mutations are rejected; Worker B lease remains intact.
    """
    test_db = str(tmp_path / "stale_worker_test.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 9911
    run_a = "run_worker_a_stale"
    worker_a = "worker_node_1"

    # 1. Worker A acquires lease
    created_a, _ = db.create_research_job_atomic(run_a, "Topic A", user_id=user_id, worker_id=worker_a)
    assert created_a is True

    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT lease_token, fencing_token FROM active_run_claims WHERE user_id = ?", (user_id,))
        claim_a = cur.fetchone()
        lease_a = claim_a["lease_token"] if is_tidb else claim_a[0]
        token_a = claim_a["fencing_token"] if is_tidb else claim_a[1]
        assert token_a == 1

    # 2 & 3. Simulate Worker A going silent and lease expiring
    # When a lease expires, the previous job is marked failed/cancelled and claim is removed
    db.update_research_job(run_a, status="failed", error_message="lease expired")

    # 4. Worker B acquires a new lease
    run_b = "run_worker_b_new"
    worker_b = "worker_node_2"
    created_b, _ = db.create_research_job_atomic(run_b, "Topic B", user_id=user_id, worker_id=worker_b)
    assert created_b is True

    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT lease_token, fencing_token FROM active_run_claims WHERE user_id = ?", (user_id,))
        claim_b = cur.fetchone()
        lease_b = claim_b["lease_token"] if is_tidb else claim_b[0]
        token_b = claim_b["fencing_token"] if is_tidb else claim_b[1]
        # Fencing token must be strictly greater than Worker A's token
        assert token_b > token_a
        assert token_b == 2

    # 5 & 6. Stale Worker A resumes and attempts mutations
    # Attempt heartbeat
    hb_fail = db.heartbeat_active_run_claim(run_a, worker_id=worker_a, lease_token=lease_a, fencing_token=token_a)
    assert hb_fail is False

    # Attempt updating job status with old lease / fencing token
    update_fail = db.update_research_job(run_a, status="completed", lease_token=lease_a, fencing_token=token_a)
    assert update_fail is False

    # Attempt releasing claim
    release_fail = db.release_active_run_claim(run_a, user_id=user_id, lease_token=lease_a, fencing_token=token_a)
    assert release_fail is False

    # 7. Verify Worker B's active lease remains untouched!
    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT run_id, worker_id, lease_token, fencing_token FROM active_run_claims WHERE user_id = ?", (user_id,))
        current_claim = cur.fetchone()
        assert (current_claim["run_id"] if is_tidb else current_claim[0]) == run_b
        assert (current_claim["worker_id"] if is_tidb else current_claim[1]) == worker_b
        assert (current_claim["lease_token"] if is_tidb else current_claim[2]) == lease_b
        assert (current_claim["fencing_token"] if is_tidb else current_claim[3]) == token_b


def _worker_process_a_execution(user_id: int, run_id: str, start_barrier, cancel_barrier, result_queue, db_path: str):
    """Process A executing long-running job and checking persistent cancellation."""
    os.environ["RESEARCH_STUDIO_DB_PATH"] = db_path
    import database as worker_db
    import threading

    created, _ = worker_db.create_research_job_atomic(run_id, "Cross-Process Cancel", user_id=user_id)
    assert created is True

    # Signal process B that job is active
    start_barrier.wait()

    # Wait for process B to issue cancellation
    cancel_barrier.wait()

    # Give DB write a moment to settle
    time.sleep(0.1)

    # Process A checks cancellation via persistent database status (cross-process)
    dummy_event = threading.Event()
    # Check persistent status directly from DB
    job = worker_db.get_research_job(run_id)
    cancelled = bool(job and job.get("status") == "cancelled")

    result_queue.put({
        "run_id": run_id,
        "observed_cancellation": cancelled,
        "final_status": job.get("status"),
    })


def _worker_process_b_cancellation(run_id: str, start_barrier, cancel_barrier, db_path: str):
    """Process B receives cancellation request and marks DB status."""
    os.environ["RESEARCH_STUDIO_DB_PATH"] = db_path
    import database as cancel_db

    # Wait for Process A to start job
    start_barrier.wait()

    # Process B cancels the run in DB (simulating cancel HTTP endpoint reaching Worker B)
    cancel_db.update_research_job(run_id, status="cancelled")

    # Signal Process A to check
    cancel_barrier.wait()


def test_cross_process_cancellation_multiprocessing(tmp_path):
    """Test that cancellation issued on Process B is reliably detected by Process A executing the run."""
    test_db = str(tmp_path / "cross_cancel.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 7777
    run_id = "run_cross_cancel_1"

    start_barrier = multiprocessing.Barrier(2)
    cancel_barrier = multiprocessing.Barrier(2)
    result_queue = multiprocessing.Queue()

    p_a = multiprocessing.Process(
        target=_worker_process_a_execution,
        args=(user_id, run_id, start_barrier, cancel_barrier, result_queue, test_db),
    )
    p_b = multiprocessing.Process(
        target=_worker_process_b_cancellation,
        args=(run_id, start_barrier, cancel_barrier, test_db),
    )

    p_a.start()
    p_b.start()

    p_a.join(timeout=10)
    p_b.join(timeout=10)

    res = result_queue.get(timeout=5)
    assert res["observed_cancellation"] is True
    assert res["final_status"] == "cancelled"
