import os
import pytest

def test_valid_locust_csv_fixtures(valid_locust_csv_dir):
    """Verifies that the valid Locust CSV fixture creates the required files."""
    stats_file = f"{valid_locust_csv_dir}_stats.csv"
    history_file = f"{valid_locust_csv_dir}_stats_history.csv"
    failures_file = f"{valid_locust_csv_dir}_failures.csv"

    assert os.path.exists(stats_file)
    assert os.path.exists(history_file)
    assert os.path.exists(failures_file)

    with open(stats_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Aggregated" in content
        assert "/health" in content
        assert "/login" in content

def test_empty_locust_csv_fixtures(empty_locust_csv_dir):
    """Verifies that the empty Locust CSV fixture provides headers but no data rows."""
    stats_file = f"{empty_locust_csv_dir}_stats.csv"
    assert os.path.exists(stats_file)
    with open(stats_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        assert len(lines) == 1  # Only header
        assert "Type,Name" in lines[0]

def test_malformed_locust_csv_fixtures(malformed_locust_csv_dir):
    """Verifies that the malformed Locust CSV fixture contains invalid non-numeric records."""
    stats_file = f"{malformed_locust_csv_dir}_stats.csv"
    assert os.path.exists(stats_file)
    with open(stats_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "not_a_number" in content

def test_mock_prometheus_fixtures(mock_prometheus_data):
    """Verifies that Prometheus deterministic mock data is complete and well-formed."""
    assert "cpu_metrics" in mock_prometheus_data
    assert "memory_metrics" in mock_prometheus_data
    assert "network_metrics" in mock_prometheus_data
    assert mock_prometheus_data["cpu_metrics"]["available"] is True
    assert mock_prometheus_data["unavailable_cpu"]["available"] is False
    assert len(mock_prometheus_data["cpu_metrics"]["series"]) == 12

def test_watchdog_fixture(valid_watchdog_dir):
    """Verifies that the watchdog log fixture produces a readable crash snapshot."""
    files = os.listdir(valid_watchdog_dir)
    assert len(files) == 1
    assert files[0].startswith("crash_")
    with open(os.path.join(valid_watchdog_dir, files[0]), "r", encoding="utf-8") as f:
        content = f.read()
        assert "Crash snapshot" in content
        assert "exited (137)" in content
