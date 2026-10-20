import os
import pytest
import tempfile
import shutil

@pytest.fixture
def temp_test_dir():
    """Provides a clean temporary directory for test isolation."""
    d = tempfile.mkdtemp(prefix="dcsim_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture
def valid_locust_csv_dir(temp_test_dir):
    """Generates a set of valid Locust CSV result files."""
    prefix = os.path.join(temp_test_dir, "results_synthetic")

    # 1. Stats CSV
    stats_content = (
        "Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%\n"
        "GET,/health,1000,0,10,12.5,5.0,85.0,60.0,50.0,0.0,10,12,14,16,20,25,30,40,60,80,85\n"
        "POST,/login,100,5,45,65.2,20.0,450.0,75.0,5.0,0.25,45,55,65,75,120,180,250,350,420,450,450\n"
        "GET,/api/data,500,0,80,95.4,30.0,320.0,2200.0,25.0,0.0,80,90,100,110,140,170,210,260,300,320,320\n"
        ",Aggregated,1600,5,15,31.7,5.0,450.0,730.0,80.0,0.25,15,20,30,40,75,120,190,280,380,450,450\n"
    )
    with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
        f.write(stats_content)

    # 2. Stats History CSV
    history_content = (
        "Timestamp,User Count,Type,Name,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%,Total Request Count,Total Failure Count,Total Median Response Time,Total Average Response Time,Total Min Response Time,Total Max Response Time,Total Average Content Size\n"
        "1700000000,10,GET,/health,10.0,0.0,10,12,14,16,20,25,30,40,60,80,85,10,0,10,12.5,5.0,85.0,60.0\n"
        "1700000000,10,,Aggregated,10.0,0.0,10,12,14,16,20,25,30,40,60,80,85,10,0,10,12.5,5.0,85.0,60.0\n"
        "1700000005,50,,Aggregated,40.0,0.0,12,15,18,22,35,50,70,90,120,150,150,50,0,12,18.0,5.0,150.0,150.0\n"
        "1700000010,100,,Aggregated,80.0,0.5,15,20,30,40,75,120,190,280,380,450,450,1600,5,15,31.7,5.0,450.0,730.0\n"
    )
    with open(f"{prefix}_stats_history.csv", "w", encoding="utf-8") as f:
        f.write(history_content)

    # 3. Failures CSV
    failures_content = (
        "Method,Name,Error,Occurrences\n"
        "POST,/login,HTTPError('500 Internal Server Error'),5\n"
    )
    with open(f"{prefix}_failures.csv", "w", encoding="utf-8") as f:
        f.write(failures_content)

    return prefix

@pytest.fixture
def empty_locust_csv_dir(temp_test_dir):
    """Generates empty/header-only Locust CSV files representing 0 requests."""
    prefix = os.path.join(temp_test_dir, "results_empty")
    stats_header = (
        "Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%\n"
    )
    with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
        f.write(stats_header)

    with open(f"{prefix}_stats_history.csv", "w", encoding="utf-8") as f:
        f.write("Timestamp,User Count,Type,Name,Requests/s,Failures/s,50%,95%\n")

    with open(f"{prefix}_failures.csv", "w", encoding="utf-8") as f:
        f.write("Method,Name,Error,Occurrences\n")

    return prefix

@pytest.fixture
def malformed_locust_csv_dir(temp_test_dir):
    """Generates corrupted/malformed Locust CSV files with non-numeric values and invalid rows."""
    prefix = os.path.join(temp_test_dir, "results_malformed")
    stats_content = (
        "Type,Name,Request Count,Failure Count,Average Response Time,95%\n"
        "GET,/broken,not_a_number,null,CORRUPT,N/A\n"
        ",Aggregated,N/A,invalid,,undefined\n"
    )
    with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
        f.write(stats_content)

    with open(f"{prefix}_stats_history.csv", "w", encoding="utf-8") as f:
        f.write("Timestamp,User Count,Name,Requests/s,95%\nBAD_TIME,BAD_USER,Aggregated,abc,def\n")

    return prefix

@pytest.fixture
def mock_prometheus_data():
    """Provides standard deterministic mock payloads for Prometheus queries."""
    start_ts = 1700000000.0
    end_ts = 1700000060.0
    
    cpu_series = [
        {"timestamp": start_ts + i * 5, "value": 25.0 + (i % 5) * 5.0}
        for i in range(12)
    ]
    # Set peak
    cpu_series[6]["value"] = 85.5

    memory_series = [
        {"timestamp": start_ts + i * 5, "value": 40.0 + i * 0.5}
        for i in range(12)
    ]
    memory_series[10]["value"] = 72.0

    network_rx_series = [
        {"timestamp": start_ts + i * 5, "value": 1.2 + (i % 3) * 0.4}
        for i in range(12)
    ]
    network_tx_series = [
        {"timestamp": start_ts + i * 5, "value": 0.8 + (i % 3) * 0.2}
        for i in range(12)
    ]

    return {
        "cpu_metrics": {
            "average": 35.2,
            "peak": 85.5,
            "peak_timestamp": start_ts + 30,
            "series": cpu_series,
            "available": True,
            "mode": "bridge"
        },
        "memory_metrics": {
            "average": 42.8,
            "peak": 72.0,
            "peak_timestamp": start_ts + 50,
            "series": memory_series,
            "available": True,
            "mode": "bridge"
        },
        "network_metrics": {
            "device": "eth0",
            "classification": "DOCKER_CONTAINER",
            "mode": "bridge",
            "warning": None,
            "total_rx_mb": 15.4,
            "total_tx_mb": 8.2,
            "peak_rx_MBps": 2.0,
            "peak_rx_timestamp": start_ts + 20,
            "peak_tx_MBps": 1.2,
            "peak_tx_timestamp": start_ts + 25,
            "rx_series": network_rx_series,
            "tx_series": network_tx_series,
            "available": True
        },
        "unavailable_cpu": {
            "average": None,
            "peak": None,
            "peak_timestamp": None,
            "series": [],
            "available": False,
            "mode": "bridge"
        },
        "unavailable_memory": {
            "average": None,
            "peak": None,
            "peak_timestamp": None,
            "series": [],
            "available": False,
            "mode": "bridge"
        },
        "unavailable_network": {
            "device": "unknown",
            "classification": "UNAVAILABLE",
            "mode": "bridge",
            "warning": "Prometheus connection refused",
            "total_rx_mb": None,
            "total_tx_mb": None,
            "peak_rx_MBps": None,
            "peak_rx_timestamp": None,
            "peak_tx_MBps": None,
            "peak_tx_timestamp": None,
            "rx_series": [],
            "tx_series": [],
            "available": False
        }
    }

@pytest.fixture
def valid_watchdog_dir(temp_test_dir):
    """Creates a temporary directory with valid crash logs."""
    logs_dir = os.path.join(temp_test_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    crash_file = os.path.join(logs_dir, "crash_20260823_184458.txt")
    crash_content = (
        "=== Crash snapshot — 2026-08-23T18:44:58.412288 ===\n"
        "Reason: connection error: [Errno 111] Connection refused\n"
        "\n"
        "--- docker compose ps ---\n"
        "NAME                COMMAND                  SERVICE             STATUS              PORTS\n"
        "dcsim-fastapi       \"uvicorn app.main:ap…\"   fastapi             exited (137)\n"
        "\n"
        "--- last 200 lines of logs/fastapi/server.log ---\n"
        "2026-08-23 18:44:55 [INFO] Request POST /login\n"
        "Killed\n"
    )
    with open(crash_file, "w", encoding="utf-8") as f:
        f.write(crash_content)
    return logs_dir
