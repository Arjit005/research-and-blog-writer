# System Hardening & Verification Report

> **Audit Date:** 2026-11-06  
> **Environment:** Windows (win32), Python 3.13.14, Node.js 22, FastAPI 0.115+, Next.js 16.4.5  
> **Verification Status:** All numbers and findings in this document were directly executed and grounded in active terminal outputs.

---

## 1. Executive Summary & Verification Matrix

| Area | Command / Source | Verified Terminal / Code Result | Status |
| :--- | :--- | :--- | :---: |
| **Python Dependencies** | `pip-audit --format json` | **89 vulnerabilities across 20 packages** (388 packages scanned) | `VERIFIED` |
| **Frontend Dependencies** | `cd frontend; npm audit` | **4 low severity vulnerabilities** (`katex` / `rehype-katex`) | `VERIFIED` |
| **Frontend Build** | `cd frontend; npm run build` | **4/4 static pages generated cleanly in 2.5s** (0 errors) | `VERIFIED` |
| **Unit & Integration Suite** | `pytest -q` | **239 passed** (0 errors, 0 failures) | `VERIFIED` |
| **Unit-Tested Failover LLM** | `pytest -q tests/test_fallback_llm.py` | **19 passed** in 20.16s | `VERIFIED` |
| **Local Load Benchmark** | `locust -f locustfile.py` | **60.5 RPS, 1,754 requests, 0% failure, median = 8ms** against `GET /health` | `VERIFIED` |
| **Static Code Security** | `bandit -r backend/ auth/ core/` | **0 High, 0 Medium**, 10 Low | `VERIFIED` |
| **Rate Limiter Window** | `auth/rate_limit.py` | **Sliding window** (rolling timestamp cutoff filtering) | `VERIFIED` |
| **Session Cookie Specs** | `backend/routes/auth.py` | `HttpOnly=True`, `SameSite=lax`, dynamic `Secure` & `__Host-` | `VERIFIED` |
| **Squad Agent Topology** | `crew.py` | **4 agents total**; **2 tasks** with `async_execution=True` | `VERIFIED` |

---

## 2. Dependency Vulnerability Audits

### 2.1 Python Dependencies (`pip-audit`)
Command executed:
```powershell
pip-audit --format json -o reports/pip_audit_verify.json
```
- **Total Packages Scanned:** 388
- **Total Vulnerabilities Reported:** 89 in 20 packages
- **Affected Packages Breakdown:**
  - `anyio`: 2
  - `brotli`: 2
  - `brotlicffi`: 1
  - `chromadb`: 5
  - `cryptography`: 13
  - `datasets`: 1
  - `filelock`: 9
  - `fsspec`: 1
  - `httplib2`: 2
  - `httpx2`: 3
  - `langgraph-sdk`: 2
  - `mcp`: 4
  - `opentelemetry-api`: 1
  - `pip`: 2
  - `protobuf`: 2
  - `pyarrow`: 2
  - `pypdf`: 26
  - `setuptools`: 1
  - `tornado`: 9
  - `uv`: 1

*Note:* Several dependencies (`filelock`, `chromadb`, `mcp`, `opentelemetry-api`) are pinned by upstream `crewai` and `litellm` requirements and cannot be upgraded without upstream package releases.

### 2.2 Frontend Dependencies (`npm audit`)
Command executed:
```powershell
cd frontend; npm audit
```
- **Total Vulnerabilities:** 4 low severity vulnerabilities
- **Path:** `rehype-katex` $\rightarrow$ `micromark-extension-math` $\rightarrow$ `katex`
- **Advisory:** GHSA-238p-pmpm-9mq7 (KaTeX prototype pollution vulnerability)

---

## 3. Frontend Production Build Verification

Command executed:
```powershell
cd frontend; npm run build
```
Terminal output:
```
▲ Next.js 16.4.5 (Turbopack)
✓ Running next.config.ts took 53ms
  Creating an optimized production build ...
✓ Compiled successfully in 1091ms
  Running TypeScript ... Finished TypeScript in 4.0s ...
  Collecting page data using 5 workers ...
  Generating static pages using 5 workers (4/4) in 2.5s
✓ Generating static pages (4/4)
Route (app)
┌ ○ /
└ ○ /_not-found
○  (Static)  prerendered as static content
```
Result: Static HTML/JS export successfully built to `frontend/out` with zero compile or TypeScript errors.

---

## 4. Code Architecture & Configuration Verification

### 4.1 Rate Limiting Architecture (`auth/rate_limit.py`)
- **Window Type:** Sliding window (rolling time window with monotonic cutoff filtering).
- **Code Grounding (`auth/rate_limit.py` Lines 7-8, 79-82, 90-93):**
  ```python
  cutoff = now - PASSWORD_ATTEMPT_WINDOW_SECONDS
  with _fallback_lock:
      _fallback_attempts[:] = [entry for entry in _fallback_attempts if entry[2] > cutoff]
  ```

### 4.2 Session Cookie Configuration (`backend/routes/auth.py`)
- **`HttpOnly`:** `True` (Line 89: `httponly=True`)
- **`SameSite`:** `"lax"` (Line 91: `samesite="lax"`)
- **`Secure`:** Dynamic based on deployment environment (Lines 47-52: `True` in `production` or `RENDER`, `False` in local development).
- **`__Host-` Prefix:** Dynamic (Line 56: uses `__Host-session_token` when `Secure` is enabled; uses `session_token` when running in plain local HTTP).

### 4.3 Multi-Agent Topology & Parallel Tasks (`crew.py`)
- **Total Agents:** 4 agents
  1. `research` (`role="Senior Researcher"`, Line 121)
  2. `content_analyst` (`role="Content Analyst"`, Line 148)
  3. `report_writer` (`role="Blog Post Writer"`, Line 174)
  4. `quality_reviewer` (`role="Quality Reviewer"`, Line 205)
- **Parallel Async Tasks (`async_execution=True`):**
  1. `analyze_the_research_provided_task` (Line 276: `async_execution=True`)
  2. `create_a_wellstructured_blog_post_task` (Line 300: `async_execution=True`)

### 4.4 Local Load Benchmark Target (`locustfile.py`)
- **Target Endpoint:** `GET /health` (Lines 6-8: `self.client.get("/health")`).

---

## 5. Automated Test Suite & Local Load Test Results

### 5.1 Unit-Tested Failover LLM Suite
Command executed:
```powershell
pytest -q tests/test_fallback_llm.py
```
Output:
```
...................                                                      [100%]
19 passed, 1 warning in 20.16s
```

### 5.2 Local Load Benchmark (Locust)
A local load test benchmark was executed against `http://127.0.0.1:8000/health` with 20 concurrent users over 30 seconds:
- **Requests:** 1,754 total requests
- **Throughput:** 60.5 RPS
- **Failure Rate:** 0.00%
- **Response Latency:**
  - 50th percentile (median): 8 ms
  - 95th percentile: 21 ms
  - 99th percentile: 28 ms
  - Average latency: 9.38 ms
