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



def test_expired_lease_renewal_rejection(tmp_path):
    """Test that an expired worker CANNOT renew its lease even if claim row is still present."""
    test_db = str(tmp_path / "expired_lease.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 1234
    run_id = "run_expired_worker_1"
    worker_id = "worker_slow"

    created, _ = db.create_research_job_atomic(run_id, "Test Expired Lease", user_id=user_id, worker_id=worker_id)
    assert created is True

    # Retrieve tokens
    with db.get_connection() as (conn, is_tidb):
        cur = db._exec(conn, is_tidb, "SELECT lease_token, fencing_token FROM active_run_claims WHERE user_id = ?", (user_id,))
        claim = cur.fetchone()
        lease_token = claim["lease_token"] if is_tidb else claim[0]
        fencing_token = claim["fencing_token"] if is_tidb else claim[1]

    # Artificially expire the lease in the past
    past_str = "2020-01-01 00:00:00"
    with db.get_connection() as (conn, is_tidb):
        db._exec(conn, is_tidb, "UPDATE active_run_claims SET lease_expires_at = ? WHERE user_id = ?", (past_str, user_id))

    # Heartbeat attempt on expired lease MUST fail
    renew_result = db.heartbeat_active_run_claim(
        run_id=run_id,
        worker_id=worker_id,
        lease_token=lease_token,
        fencing_token=fencing_token,
    )
    assert renew_result is False, "Expired worker must be rejected from renewing lease"


def test_cancellation_race_during_llm_execution(tmp_path):
    """Test cancellation race scenario:
    1. Worker A starts execution.
    2. Cancellation request sets job status to cancelled in DB.
    3. Worker A finishes LLM execution and checks cancellation.
    4. Worker A aborts without persisting output or publishing articles.
    """
    test_db = str(tmp_path / "cancel_race.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 9988
    run_id = "run_race_cancel"

    created, _ = db.create_research_job_atomic(run_id, "Cancellation Race Topic", user_id=user_id)
    assert created is True

    # Concurrent cancel occurs
    db.update_research_job(run_id, status="cancelled")

    # Worker checks status
    job = db.get_research_job(run_id)
    assert job["status"] == "cancelled"

    # Worker attempts update with terminal state check
    updated = db.update_research_job(run_id, status="completed")
    assert updated is False, "Terminal cancelled job must freeze and reject completion"

    # Verify no article was persisted
    articles = db.get_articles(user_id=user_id)
    assert len(articles) == 0, "No article should be saved after cancellation"



def test_stale_worker_article_write_rejected_under_fencing(tmp_path):
    """Test that a stale worker cannot write articles when its lease token or fencing token is invalid."""
    test_db = str(tmp_path / "stale_write.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 5566
    run_id = "run_stale_write_1"
    worker_a = "worker_alpha"

    created, _ = db.create_research_job_atomic(run_id, "Stale Write Topic", user_id=user_id, worker_id=worker_a)
    assert created is True

    # Attempting to save article with wrong worker_id or wrong fencing token MUST be rejected
    with pytest.raises(PermissionError) as exc:
        db.save_article_with_initial_revision(
            topic="Stale Write Topic",
            content="# Stale content",
            user_id=user_id,
            run_id=run_id,
            worker_id="worker_imposter",
            lease_token="lease_invalid",
            fencing_token=999,
        )
    assert "rejected" in str(exc.value).lower() or "stale" in str(exc.value).lower()

    # Verify no articles were inserted
    articles = db.get_articles(user_id=user_id)
    assert len(articles) == 0


def test_cancellation_atomicity_rejects_article_write(tmp_path):
    """Test that if cancellation commits first, any subsequent article write for that run is rejected."""
    test_db = str(tmp_path / "cancel_atomic.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    user_id = 7788
    run_id = "run_cancel_atomic_1"

    created, _ = db.create_research_job_atomic(run_id, "Atomic Cancel Topic", user_id=user_id)
    assert created is True

    # User cancels run
    db.update_research_job(run_id, status="cancelled")

    # Worker attempts to write article for the cancelled run
    with pytest.raises(PermissionError) as exc:
        db.save_article_with_initial_revision(
            topic="Atomic Cancel Topic",
            content="# Late content from cancelled run",
            user_id=user_id,
            run_id=run_id,
        )
    assert "cancelled" in str(exc.value).lower() or "terminal" in str(exc.value).lower()

    # Confirm 0 articles persisted
    assert len(db.get_articles(user_id=user_id)) == 0


def _worker_append_events(run_id: str, count: int, barrier, result_queue, db_path: str):
    """Independent process appending sequenced events to the SSE event ledger."""
    import os
    os.environ["RESEARCH_STUDIO_DB_PATH"] = db_path
    import database as worker_db

    assigned_sequences = []
    barrier.wait()
    for i in range(count):
        try:
            seq = worker_db.append_job_event(
                run_id,
                "step",
                {"worker_pid": os.getpid(), "index": i},
            )
            assigned_sequences.append(seq)
        except Exception as exc:
            assigned_sequences.append(f"err:{exc}")

    result_queue.put({"pid": os.getpid(), "sequences": assigned_sequences})


def test_concurrent_sse_event_sequences_gap_free_and_monotonic(tmp_path):
    """Test 4 independent OS workers concurrently appending 100 events total (25 each) to one run."""
    test_db = str(tmp_path / "sse_concurrency.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    target_run_id = "run_sse_concurrency_100"
    db.create_research_job_atomic(target_run_id, "SSE Concurrency Test", user_id=8899)

    num_workers = 4
    events_per_worker = 25
    total_events = num_workers * events_per_worker

    barrier = multiprocessing.Barrier(num_workers)
    result_queue = multiprocessing.Queue()

    processes = []
    for _ in range(num_workers):
        p = multiprocessing.Process(
            target=_worker_append_events,
            args=(target_run_id, events_per_worker, barrier, result_queue, test_db),
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join(timeout=20)

    # Collect results
    all_assigned = []
    for _ in range(num_workers):
        res = result_queue.get(timeout=5)
        for s in res["sequences"]:
            assert not str(s).startswith("err:"), f"Worker event append failed: {s}"
            all_assigned.append(s)

    # 1. Total event count
    assert len(all_assigned) == total_events == 100

    # 2. Sequence uniqueness
    assert len(set(all_assigned)) == 100, "Sequence numbers must be strictly unique"

    # 3. Gap-free contiguous integers from 1 to 100
    assert sorted(all_assigned) == list(range(1, 101)), "Sequence numbers must be gap-free 1..100"

    # 4. Fetch events from database and verify persistence & resume with after_seq
    persisted = db.get_job_events(target_run_id, after_seq_id=0, limit=200)
    assert len(persisted) == 100
    db_sequences = [e["seq_id"] for e in persisted]
    assert db_sequences == list(range(1, 101))

    # 5. SSE Resume test: reconnect after seq 50
    resumed = db.get_job_events(target_run_id, after_seq_id=50, limit=200)
    assert len(resumed) == 50
    assert [e["seq_id"] for e in resumed] == list(range(51, 101))


def test_concurrent_sse_events_across_different_runs(tmp_path):
    """Test independent workers appending events concurrently to separate runs without interference."""
    test_db = str(tmp_path / "sse_diff_runs.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    run_a = "run_alpha_events"
    run_b = "run_beta_events"
    db.create_research_job_atomic(run_a, "Alpha Topic", user_id=9001)
    db.create_research_job_atomic(run_b, "Beta Topic", user_id=9002)

    barrier = multiprocessing.Barrier(2)
    result_queue = multiprocessing.Queue()

    p1 = multiprocessing.Process(
        target=_worker_append_events,
        args=(run_a, 20, barrier, result_queue, test_db),
    )
    p2 = multiprocessing.Process(
        target=_worker_append_events,
        args=(run_b, 20, barrier, result_queue, test_db),
    )
    p1.start()
    p2.start()
    p1.join(timeout=15)
    p2.join(timeout=15)

    ev_a = db.get_job_events(run_a, after_seq_id=0)
    ev_b = db.get_job_events(run_b, after_seq_id=0)

    assert len(ev_a) == 20
    assert len(ev_b) == 20
    assert [e["seq_id"] for e in ev_a] == list(range(1, 21))
    assert [e["seq_id"] for e in ev_b] == list(range(1, 21))


def test_sse_event_idempotency_and_duplicate_retry(tmp_path):
    """Test that appending an event with an existing event_id returns the original seq_id without gaps."""
    test_db = str(tmp_path / "sse_idempotent.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    run_id = "run_idempotent_1"
    db.create_research_job_atomic(run_id, "Idempotent Topic", user_id=9090)

    # 1. First append with event_id
    seq1 = db.append_job_event(run_id, "step", {"step": 1}, event_id="evt_unique_1")
    assert seq1 == 1

    # 2. Duplicate retry with same event_id
    seq1_retry = db.append_job_event(run_id, "step", {"step": 1, "retry": True}, event_id="evt_unique_1")
    assert seq1_retry == 1, "Duplicate event_id must return original seq_id"

    # 3. Next new event should receive next sequential number (2, not 3) - zero gaps!
    seq2 = db.append_job_event(run_id, "step", {"step": 2}, event_id="evt_unique_2")
    assert seq2 == 2, "Sequence counter must remain contiguous after duplicate retry"

    # 4. Confirm exactly 2 rows exist in DB
    events = db.get_job_events(run_id)
    assert len(events) == 2
    assert [e["seq_id"] for e in events] == [1, 2]
    assert [e["event_id"] for e in events] == ["evt_unique_1", "evt_unique_2"]


def _worker_append_duplicate_events(run_id: str, event_id: str, barrier, result_queue, db_path: str):
    """Worker attempting to insert the exact same logical event_id simultaneously."""
    import os
    os.environ["RESEARCH_STUDIO_DB_PATH"] = db_path
    import database as worker_db

    barrier.wait()
    try:
        seq = worker_db.append_job_event(
            run_id,
            "duplicate_step",
            {"worker_pid": os.getpid()},
            event_id=event_id,
        )
        result_queue.put({"pid": os.getpid(), "seq": seq, "status": "ok"})
    except Exception as exc:
        result_queue.put({"pid": os.getpid(), "error": str(exc), "status": "err"})


def test_concurrent_duplicate_event_submissions_race(tmp_path):
    """Test 4 concurrent processes attempting to commit the EXACT SAME event_id at the same instant."""
    test_db = str(tmp_path / "sse_race_idempotency.db")
    os.environ["RESEARCH_STUDIO_DB_PATH"] = test_db
    db.init_db()

    run_id = "run_race_idempotent"
    db.create_research_job_atomic(run_id, "Race Idempotent", user_id=9091)
    shared_event_id = "shared_event_alpha_999"

    num_workers = 4
    barrier = multiprocessing.Barrier(num_workers)
    result_queue = multiprocessing.Queue()

    processes = []
    for _ in range(num_workers):
        p = multiprocessing.Process(
            target=_worker_append_duplicate_events,
            args=(run_id, shared_event_id, barrier, result_queue, test_db),
        )
        p.start()
        processes.append(p)

    for p in processes:
        p.join(timeout=15)

    results = [result_queue.get(timeout=5) for _ in range(num_workers)]
    for r in results:
        assert r["status"] == "ok", f"Worker failed: {r}"
        assert r["seq"] == 1, "All 4 racing workers must observe the identical seq_id 1"

    # Verify only 1 physical event was persisted
    persisted = db.get_job_events(run_id)
    assert len(persisted) == 1
    assert persisted[0]["seq_id"] == 1
    assert persisted[0]["event_id"] == shared_event_id


