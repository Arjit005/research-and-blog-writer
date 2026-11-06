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

    # Verify fencing token incremented
    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT fencing_token FROM active_run_claims WHERE user_id = ?", (user_id,))
        claim = cur.fetchone()
        updated_token = claim["fencing_token"] if is_tidb else claim[0]
        assert updated_token == 2

    # Stale/unauthorized worker attempt fails
    unauthorized_renew = db.heartbeat_active_run_claim(run_id, worker_id=worker_b, lease_token=lease_token)
    assert unauthorized_renew is False

    # Invalid lease token attempt fails
    invalid_token_renew = db.heartbeat_active_run_claim(run_id, worker_id=worker_a, lease_token="fake_lease_token")
    assert invalid_token_renew is False
