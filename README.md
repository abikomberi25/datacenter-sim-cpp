
# datacenter-sim

**Real-World, Multi-User Data Centre Workload Simulation for Server Testing**

A scalable, open-source framework for simulating realistic multi-user login traffic against a server — built to test how authentication systems behave under ramp-up, peak, sustained, and cooldown conditions, from hundreds to millions of users.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Locust](https://img.shields.io/badge/Load%20Gen-Locust-green)
![FastAPI](https://img.shields.io/badge/Server-FastAPI-teal)
![Docker](https://img.shields.io/badge/Infra-Docker-blue)
![Prometheus](https://img.shields.io/badge/Metrics-Prometheus-orange)
![Grafana](https://img.shields.io/badge/Dashboard-Grafana-red)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What this is

Most server load tests send flat, constant traffic — but real production traffic ramps up, spikes, sustains, and cools down, often through multiple interfaces at once, with different user types competing for the same server resources.

This framework reproduces that realism around a login/authentication system — one of the most concurrency-sensitive parts of any application. It simulates three interface types (web, mobile, API), each with light and heavy user variants, generating realistic session lifecycles alongside sustained machine traffic. This creates genuine cross-interface contention and exposes defects that flat-load tests miss entirely.

---

## Table of contents

- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Folder structure](#folder-structure)
- [Team and responsibilities](#team-and-responsibilities)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Workload profiles](#workload-profiles)
- [Simulated user types](#simulated-user-types)
- [Server endpoints](#server-endpoints)
- [Running tests](#running-tests)
- [Monitoring](#monitoring)
- [Crash logging](#crash-logging)
- [Generating the report](#generating-the-report)
- [Scalability](#scalability)
- [SLA thresholds](#sla-thresholds)
- [Contributing](#contributing)

---

## Architecture

```
┌──────────────────────────────────────┐
│         workload_profiles/           │
│         normal_day.yaml              │  ← steady baseline pattern
│         flash_event.yaml             │  ← sudden spike pattern
└─────────────────┬────────────────────┘
                  │ read by run_test.py
┌─────────────────▼────────────────────┐
│         Locust (master + workers)    │  ← WebUser, MobileUser, APIUser
│         locustfile.py + loadshapes.py│     light + heavy variants
└─────────────────┬────────────────────┘
                  │ HTTP requests
┌─────────────────▼────────────────────┐
│         FastAPI server               │
│         /login  /logout  /me         │
│         /profile/update  /api/data   │
│         /health  /metrics            │
└──────────┬───────────────────────────┘
           │ metrics
     ┌─────▼──────┐          ┌──────────────┐
     │ Prometheus │─────────▶│   Grafana    │
     │ + Node Exp │          │  dashboards  │
     └─────┬──────┘          └──────────────┘
           │
     ┌─────▼──────────────┐
     │  analysis/          │
     │  run_analysis.py    │  ← Analysis engine, bottleneck detection,
     │  → PDF, HTML, JSON  │    SLA verdict, timeline, charts
     └─────────────────────┘
```

---

## Tech stack

| Layer | Tools |
|---|---|
| Language and config | Python 3.11, YAML, Git |
| Test target server | FastAPI, Uvicorn |
| Load generation | Locust (distributed master/worker) |
| Infrastructure | Docker, Docker Compose |
| Monitoring | Prometheus, Node Exporter, Grafana |
| Analysis and reporting | Pandas, Matplotlib, Seaborn |

All tools are 100% open source — zero licensing cost.

---

## Folder structure

```
datacenter-sim/
├── app/                          # FastAPI server (test target)
│   ├── main.py                   # All endpoints: /login /logout /me etc.
│   ├── Dockerfile
│   └── requirements.txt
│
├── simulation/                   # Locust load generation
│   ├── locustfile.py             # WebUser, MobileUser, APIUser (light + heavy)
│   ├── loadshapes.py             # Ramp-up / peak / cooldown phase curves
│   ├── run_test.py               # Reads YAML profile, launches Locust
│   └── requirements.txt
│
├── infra/                        # Infrastructure
│   ├── docker-compose.yml        # Wires all 6 services on one Docker network
│   └── prometheus.yml            # Scrape config for Prometheus
│
├── monitor/                      # Crash detection
│   └── crash_watch.py            # Health check loop — saves logs on crash
│
├── monitoring/                   # Grafana dashboards
│   └── dashboards/*.json
│
├── analysis/                     # Analysis and reporting
│   ├── analyse.py                # Bottleneck detection, SLA verdict, PDF output
│   └── reports/.gitkeep
│
├── workload_profiles/            # Test scenario configs
│   ├── normal_day.yaml           # Steady baseline (day/night cycle)
│   └── flash_event.yaml          # Sudden spike (event-driven surge)
│
├── results/.gitkeep              # Locust CSV output
├── logs/.gitkeep                 # Server and crash logs
├── docs/                         # Project proposal, diagrams, notes
├── .env.example                  # Environment variable template
├── .gitignore
├── CONTRIBUTING.md
└── README.md
```

---

## Team and responsibilities

| Member | Role | Owns |
|---|---|---|
| Member 1 | App developer | `app/main.py` — FastAPI endpoints |
| Member 2 | App developer | `app/main.py` — auth logic, session tokens |
| Member 3 | Simulation developer | `simulation/` — Locust users, loadshapes, run_test.py, YAML profiles |
| Member 4 | Infrastructure | `infra/` — Docker Compose, Prometheus config, crash watchdog |
| Member 5 | Monitoring | `monitoring/` — Grafana dashboards, Node Exporter, alerts |
| Member 6 | Analysis and reporting | `analysis/` — run_analysis.py, analyse.py, report_generator.py (PDF/HTML/JSON, SLA verdicts, charts) |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) or Docker Engine (Linux)
- Python 3.11+
- Git
- 8GB RAM minimum, 16GB recommended (six containers run simultaneously)

---

## Quick start

### 1. Clone the repo

```bash
git clone https://github.com/subhasreelk/datacenter-sim.git
cd datacenter-sim
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env if needed — defaults work for local development
```

### 3. Install Python dependencies

```bash
pip install -r app/requirements.txt
pip install -r simulation/requirements.txt
```

### 4. Start the full stack

```bash
cd infra
docker-compose up --build
```

This starts all six services on one Docker network:
- FastAPI login server
- Locust master + workers
- Prometheus + Node Exporter
- Grafana

### 5. Open the dashboards

| Service | URL |
|---|---|
| FastAPI server | http://localhost:8000 |
| Locust UI | http://localhost:8089 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

---

## Workload profiles

All test parameters live in a single YAML file. Changing one file changes the entire test — no code touched.

```yaml
# workload_profiles/normal_day.yaml

target_users: 500
spawn_rate: 10
duration: 300

phases:
  ramp_up: 60        # seconds — users gradually increase
  peak: 120          # seconds — full concurrency
  steady_state: 90   # seconds — sustained load
  cooldown: 30       # seconds — users wind down

user_mix:
  web: 0.50
  mobile: 0.35
  api: 0.15

sla:
  p95_login_ms: 500
  error_rate: 0.01
  cpu_percent: 80
  memory_percent: 90
```

Two profiles are included out of the box:

| Profile | Pattern | Use for |
|---|---|---|
| `normal_day.yaml` | Steady baseline with gradual ramp | Establishing a healthy baseline |
| `flash_event.yaml` | Sudden spike, short sharp peak | Simulating a sale, event, or viral moment |

---

## Simulated user types

Three interface types are simulated, each split into weighted light and heavy variants:

| User type | Weight | Light variant | Heavy variant |
|---|---|---|---|
| WebUser | 50% | 80% — login → /me → logout (single pass) | 20% — login → loop(/me + /profile/update) → logout |
| MobileUser | 35% | 60% — login → /me once | 40% — login → poll /me repeatedly (background sync) |
| APIUser | 15% | 30% — login once → occasional /api/data | 70% — login once → sustained /api/data calls |

The heavy APIUser is the primary source of cross-interface contention — it competes with web and mobile traffic for the same CPU and session store resources.

---

## Server endpoints

| Method | Endpoint | Used by | Purpose |
|---|---|---|---|
| POST | /login | All users | Authenticate, issue session token |
| POST | /logout | Web users | End session, invalidate token |
| GET | /me | Web + Mobile | Get current user profile |
| POST | /profile/update | Mobile (heavy), Web (heavy) | Update profile — write-heavy |
| GET | /api/data | API users | Sustained machine traffic |
| GET | /health | Monitoring | Liveness check |
| GET | /metrics | Prometheus | Request count, latency histograms |

---

## Running tests

Always run the baseline first, then the spike, so the analysis can compare both runs:

```bash
# Run steady baseline
python simulation/run_test.py --profile workload_profiles/normal_day.yaml

# Run flash event spike
python simulation/run_test.py --profile workload_profiles/flash_event.yaml
```

### Scale up workers for higher user counts

```bash
docker-compose up --scale locust-worker=4
```

No code changes needed — just add workers.

---

## Monitoring

While a test runs, open Grafana at http://localhost:3000 to see live panels for:

- Requests per second
- p95 login latency
- Error rate
- CPU utilisation
- Memory utilisation
- Active concurrent users

Prometheus raw metrics are available at http://localhost:9090.

---

## Crash logging

Container logs and Prometheus metrics are persisted via Docker volume mounts — they survive container crashes and restarts.

Log locations on the host machine:

```
logs/fastapi/server.log     ← FastAPI app logs (full stack traces)
logs/crash_<timestamp>.txt  ← Crash snapshot captured by watchdog
data/prometheus/            ← Prometheus time-series data
```

Run the crash watchdog alongside your test to automatically capture a full snapshot the moment the server goes down:

```bash
python monitor/crash_watch.py &
python simulation/run_test.py --profile workload_profiles/flash_event.yaml
```

---

## Generating the report (Member 6)

The analysis and diagnostics subsystem processes Locust load generation results, correlated Prometheus system metrics, and container crash watchdog events to produce SLA evaluations, root-cause bottleneck diagnoses, and cross-format reports.

### Entry point

```bash
python -m analysis.run_analysis --profile <profile_name> [options]
```

### Supported CLI arguments

| Argument | Description | Default |
|---|---|---|
| `--profile` | Workload profile name (e.g. `normal_day`, `flash_event`) | `normal_day` |
| `--csv` | Custom Locust results prefix or path (e.g. `results_normal_day`) | `results_<profile>` |
| `--start-time` | Experiment start timestamp (Unix epoch seconds) | Derived from Locust history |
| `--end-time` | Experiment end timestamp (Unix epoch seconds) | Derived from Locust history |
| `--live` | Fall back to current sliding window when history timestamps are absent | `False` |
| `--config` | Path to analysis configuration YAML file | `analysis/config.yaml` |
| `--output-dir` | Directory to save generated reports and plots | `reports` |
| `--json-out` | Optional custom filename for exported JSON analysis report | None (auto-generated) |

### Common run examples

```bash
# Analyze historical normal_day run (auto-derives [start, end] window from history CSV)
python -m analysis.run_analysis --csv results_normal_day --profile normal_day

# Analyze historical flash_event run with custom output directory
python -m analysis.run_analysis --csv results_flash_event --profile flash_event --output-dir reports_custom

# Analyze a live experiment with explicit epoch window
python -m analysis.run_analysis --profile normal_day --start-time 1787489781.0 --end-time 1787490199.0
```

### Input requirements & deterministic run selection

The Locust parser expects companion CSV files sharing a common run prefix:
- `<prefix>_stats.csv` (Aggregated and per-endpoint HTTP metrics)
- `<prefix>_stats_history.csv` (Time-series RPS, user counts, and latency percentiles)
- `<prefix>_failures.csv` (HTTP failure details and error messages)

If multiple ambiguous runs are detected within a directory and no prefix is specified, the parser raises an `AmbiguousRunError` with an actionable error message requiring an explicit `--csv` argument.

### Experiment time-window alignment

The analysis engine aligns Prometheus metrics with the actual Locust execution window:
1. **Historical data (Default):** When `--start-time` or `--end-time` are omitted, boundaries `[min_timestamp, max_timestamp]` are automatically derived from the Locust history CSV.
2. **Explicit window:** Users can supply precise `--start-time` and `--end-time` in Unix epoch seconds.
3. **Live experiments:** Passing `--live` permits sliding-window fallback to the last 10 minutes from `time.time()` when history timestamps are absent.

### SLA verdicts and observability diagnostics

The analysis engine distinguishes performance SLA compliance from telemetry completeness:

- **`PASS`:** All evaluated checks met defined thresholds (p95 latency <= 500 ms, error rate <= 1.0%, peak CPU <= 80%, peak memory <= 90%).
- **`FAIL`:** One or more evaluated checks violated SLA thresholds.
- **`INCOMPLETE`:** Required telemetry was missing or unevaluated (e.g., offline re-analysis without Prometheus), while evaluated checks satisfied thresholds. Missing metrics are preserved in `missing_evidence`.

#### Diagnostic classification hierarchy

- **Observability Gaps:** If Prometheus is unreachable or telemetry is absent, the engine records `classification: INSUFFICIENT_EVIDENCE` with primary bottleneck `None` and `confidence: LOW`. It never invents an application bottleneck or falsely declares health.
- **Resource Saturation:** High resource utilization (CPU > 80%) without latency breaches is classified as `RESOURCE_SATURATION` rather than `SYSTEM_HEALTHY`.
- **Infrastructure Scope:** Node Exporter reports container/host environment metrics depending on Docker Compose network configuration (`bridge` vs `host`).

### Generated report artifacts

Each analysis run creates a timestamped folder `<output-dir>/<profile>/<YYYYMMDD_HHMMSS>/` containing:

1. **`report_<profile>_<timestamp>.pdf`:** Multi-page executive PDF report (Matplotlib `PdfPages`) with overflow continuation pagination for large endpoint tables and event timelines.
2. **`report_<profile>_<timestamp>.html`:** Interactive HTML report with SLA badges and embedded performance summaries.
3. **`analysis_<profile>_<timestamp>.json`:** Canonical structured JSON artifact containing complete experiment metadata, SLA evaluations, load metrics, timeline, and provenance.
4. **`<profile>_<timestamp>_locust_performance.png`:** Concurrency, RPS, and P95 latency charts over time.
5. **`<profile>_<timestamp>_system_metrics.png`:** CPU, memory, and network throughput charts with defensive placeholder notices when telemetry is absent.

---

## Testing & Verification

Automated test suites are managed with `pytest`:

```bash
# Run Member 6 analysis and diagnostics test suite (100% passing)
pytest tests/

# Run the complete workspace test suite
pytest
```

### Workspace test status

- **Member 6 tests (`tests/`):** 51 passed, 0 failed. Covers baseline fixtures, input integrity, time alignment, SLA evaluation boundaries, bottleneck hierarchy, table pagination, chart placeholders, and Matplotlib resource cleanup.
- **Full workspace:** 69 passed, 3 pre-existing failures in `app/tests/test_endpoints.py`. These 3 failures (`TestMe::test_me_without_token`, `TestProfileUpdate::test_update_profile_no_token`, `TestApiData::test_api_data_no_token`) are pre-existing Member 2 endpoint authorization assertion mismatches where FastAPI's HTTPBearer returns `401 Unauthorized` instead of the test's expected `403 Forbidden`.

---

## Scalability

Simulating millions of users is achieved architecturally, not by literally running a million-user test on a laptop:

- **Config-driven scale** — change `target_users` in the YAML, nothing else changes
- **Locust distributed mode** — one master coordinates many worker nodes generating load independently
- **Horizontal scaling** — `docker-compose up --scale locust-worker=N` adds capacity in one command
- **Bottleneck identification** — the report identifies the exact ceiling and what to fix to go higher
- **Cloud-ready** — the same `docker-compose up` command works on any cloud VM (AWS EC2, Azure, GCP) for true large-scale runs

---

## SLA thresholds

Default thresholds (configurable per profile in the YAML):

| Metric | Default threshold |
|---|---|
| p95 login latency | < 500ms |
| Error rate | < 1% |
| CPU utilisation | < 80% |
| Memory utilisation | < 90% |

---

## Contributing

### Branch naming

```
feature/<your-name>-<short-description>
e.g. feature/member3-locustfile
     feature/member5-grafana-dashboard
```

### Workflow

1. Never push directly to `main`
2. Create a branch for your feature or fix
3. Open a pull request when your work is ready
4. At least one other team member reviews before merge
5. Use `develop` branch for integration testing — merge to `main` only when the full stack works end to end

### Integration checkpoints

Three points where the whole team must sync before moving on:

| Checkpoint | Condition |
|---|---|
| 1 | FastAPI server is running locally and Locust can hit it successfully |
| 2 | `docker-compose up --build` starts all six services and Prometheus is scraping metrics |
| 3 | A full end-to-end test run produces a Locust CSV and `analyse.py` generates a PDF |

---
