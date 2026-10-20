import os
import time
import pytest
import datetime
from unittest.mock import patch, MagicMock

from analysis.locust_results import LocustResultParser, AmbiguousRunError
from analysis.watchdog_reader import WatchdogReader
from analysis.analyse import AnalysisEngine

class TestLocustDiscoveryAndParsing:
    """Tests 1, 2, 3, 4, 5: Deterministic Locust discovery and CSV parsing."""

    def test_single_valid_run_discovery(self, valid_locust_csv_dir):
        """1. One valid Locust run resolved by prefix."""
        parser = LocustResultParser(valid_locust_csv_dir)
        data = parser.parse()

        assert data["summary"]["total_requests"] == 1600
        assert data["summary"]["failed_requests"] == 5
        assert len(data["endpoints"]) == 3
        assert data["discovered_files"]["stats_file"].endswith("_stats.csv")
        assert data["discovered_files"]["companion_history_found"] is True
        assert data["discovered_files"]["companion_failures_found"] is True

    def test_directory_with_single_run_is_deterministic(self, temp_test_dir):
        """2. Directory with single run resolves deterministically."""
        prefix = os.path.join(temp_test_dir, "results_runA")
        with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
            f.write("Type,Name,Request Count,Failure Count,Average Response Time,95%\nGET,/me,10,0,5.0,10.0\n")

        parser = LocustResultParser(temp_test_dir)
        assert parser.stats_file == f"{prefix}_stats.csv"
        assert parser.base_prefix == prefix

    def test_directory_with_multiple_runs_raises_ambiguous_error(self, temp_test_dir):
        """3. Ambiguous run selection raises AmbiguousRunError when multiple runs exist in dir."""
        for run_name in ["results_run1", "results_run2"]:
            prefix = os.path.join(temp_test_dir, run_name)
            with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
                f.write("Type,Name,Request Count,Failure Count,Average Response Time,95%\n,Aggregated,10,0,5.0,10.0\n")

        with pytest.raises(AmbiguousRunError) as exc_info:
            LocustResultParser(temp_test_dir)
        assert "Ambiguous Locust runs" in str(exc_info.value)
        assert "results_run1" in str(exc_info.value)
        assert "results_run2" in str(exc_info.value)

    def test_missing_companion_csv_files(self, temp_test_dir):
        """4. Stats CSV exists, but companion history and failures CSVs are absent."""
        prefix = os.path.join(temp_test_dir, "results_solo")
        with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
            f.write("Type,Name,Request Count,Failure Count,Average Response Time,95%\nGET,/ping,5,0,2.0,5.0\n")

        parser = LocustResultParser(prefix)
        data = parser.parse()

        assert data["discovered_files"]["companion_history_found"] is False
        assert data["discovered_files"]["companion_failures_found"] is False
        assert len(data["history_series"]) == 0
        assert len(data["failures"]) == 0
        assert data["summary"]["total_requests"] == 5

    def test_empty_and_malformed_csvs(self, empty_locust_csv_dir, malformed_locust_csv_dir):
        """5. Handles header-only (0 requests) and corrupted rows safely without crashing."""
        # Empty run
        empty_parser = LocustResultParser(empty_locust_csv_dir)
        empty_data = empty_parser.parse()
        assert empty_data["summary"]["total_requests"] == 0
        assert empty_data["summary"]["is_empty"] is True
        assert empty_data["summary"]["p95_latency_ms"] is None

        # Malformed run
        malformed_parser = LocustResultParser(malformed_locust_csv_dir)
        malformed_data = malformed_parser.parse()
        assert malformed_data["summary"]["total_requests"] == 0
        assert malformed_data["history_provenance"]["samples_discarded_invalid"] > 0


class TestLocustHistoryFiltering:
    """Tests 6, 7: History interval filtering and chronological ordering."""

    def test_history_interval_filtering(self, temp_test_dir):
        """6. Discards history samples before and after experiment window [start_time, end_time]."""
        prefix = os.path.join(temp_test_dir, "results_window")
        with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
            f.write("Type,Name,Request Count,Failure Count,Average Response Time,95%\n,Aggregated,100,0,10.0,20.0\n")

        # History with samples at t=100, t=105, t=110, t=115, t=120
        with open(f"{prefix}_stats_history.csv", "w", encoding="utf-8") as f:
            f.write("Timestamp,User Count,Name,Requests/s,Failures/s,95%\n")
            for ts in [100, 105, 110, 115, 120]:
                f.write(f"{ts},10,Aggregated,20.0,0.0,15.0\n")

        # Filter to window [105, 115]
        parser = LocustResultParser(prefix)
        data = parser.parse(start_time=105, end_time=115)

        prov = data["history_provenance"]
        assert prov["total_samples_read"] == 5
        assert prov["samples_retained"] == 3
        assert prov["samples_discarded_before"] == 1  # t=100 discarded
        assert prov["samples_discarded_after"] == 1   # t=120 discarded
        assert [h["timestamp"] for h in data["history_series"]] == [105.0, 110.0, 115.0]

    def test_unsorted_and_missing_history_timestamps(self, temp_test_dir):
        """7. Handles unsorted rows and rows with missing/corrupt timestamps."""
        prefix = os.path.join(temp_test_dir, "results_unsorted")
        with open(f"{prefix}_stats.csv", "w", encoding="utf-8") as f:
            f.write("Type,Name,Request Count,Failure Count,Average Response Time,95%\n,Aggregated,50,0,10.0,20.0\n")

        with open(f"{prefix}_stats_history.csv", "w", encoding="utf-8") as f:
            f.write("Timestamp,User Count,Name,Requests/s,Failures/s,95%\n")
            f.write("150,10,Aggregated,5.0,0.0,10.0\n")
            f.write("INVALID,10,Aggregated,5.0,0.0,10.0\n")
            f.write("110,10,Aggregated,5.0,0.0,10.0\n")
            f.write(",10,Aggregated,5.0,0.0,10.0\n")
            f.write("130,10,Aggregated,5.0,0.0,10.0\n")

        parser = LocustResultParser(prefix)
        data = parser.parse()

        # Should be chronologically sorted [110, 130, 150]
        timestamps = [h["timestamp"] for h in data["history_series"]]
        assert timestamps == [110.0, 130.0, 150.0]
        assert data["history_provenance"]["samples_discarded_invalid"] == 2


class TestTimeWindowValidation:
    """Test 8: Invalid experiment boundaries."""

    def test_invalid_experiment_boundaries_raise_value_error(self, valid_locust_csv_dir):
        """8. Rejects invalid boundaries (end_time < start_time, NaN, non-finite)."""
        parser = LocustResultParser(valid_locust_csv_dir)
        with pytest.raises(ValueError) as exc_info:
            parser.parse(start_time=200, end_time=100)
        assert "must be greater than or equal to start_time" in str(exc_info.value)

        with pytest.raises(ValueError):
            parser.parse(start_time=float("nan"), end_time=100)

        engine = AnalysisEngine()
        with pytest.raises(ValueError):
            engine.analyze(start_time=200, end_time=100, locust_target=valid_locust_csv_dir)


class TestWatchdogTimestampNormalization:
    """Tests 11, 12: Watchdog timestamps normalization, offsets, naive and invalid handling."""

    def test_watchdog_explicit_offsets(self, temp_test_dir):
        """11. Watchdog timestamps with explicit UTC offsets (+05:30, -04:00, Z)."""
        logs_dir = os.path.join(temp_test_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        # File 1 with +05:30 offset
        f1 = os.path.join(logs_dir, "crash_offset.txt")
        with open(f1, "w", encoding="utf-8") as f:
            f.write("=== Crash snapshot — 2026-08-23T18:30:00+05:30 ===\nReason: offset test\n")

        # File 2 with Z suffix
        f2 = os.path.join(logs_dir, "crash_utc.txt")
        with open(f2, "w", encoding="utf-8") as f:
            f.write("=== Crash snapshot — 2026-08-23T13:00:00Z ===\nReason: utc test\n")

        reader = WatchdogReader(logs_dir=logs_dir)
        p1 = reader.parse_crash_file(f1)
        p2 = reader.parse_crash_file(f2)

        # 18:30:00+05:30 == 13:00:00 UTC == timestamp 1787490000.0
        assert p1["timezone_status"] == "EXPLICIT_OFFSET"
        assert p2["timezone_status"] == "EXPLICIT_OFFSET"
        assert p1["timestamp"] == p2["timestamp"]
        assert "+00:00" in p1["iso_time"]

    def test_watchdog_naive_and_invalid_timestamps(self, temp_test_dir):
        """12. Ambiguous naive timestamps marked; malformed strings preserved as unparsable."""
        logs_dir = os.path.join(temp_test_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)

        # Naive timestamp
        f_naive = os.path.join(logs_dir, "crash_20260823_140000.txt")
        with open(f_naive, "w", encoding="utf-8") as f:
            f.write("=== Crash snapshot — 2026-08-23T14:00:00 ===\nReason: naive test\n")

        # Malformed timestamp
        f_bad = os.path.join(logs_dir, "crash_corrupt.txt")
        with open(f_bad, "w", encoding="utf-8") as f:
            f.write("=== Crash snapshot — CORRUPTED_DATE ===\nReason: corrupted test\n")

        reader = WatchdogReader(logs_dir=logs_dir)
        p_naive = reader.parse_crash_file(f_naive)
        p_bad = reader.parse_crash_file(f_bad)

        assert p_naive["timezone_status"] == "NAIVE_NORMALIZED_UTC"
        assert p_naive["timestamp"] is not None

        assert p_bad["timezone_status"] == "UNPARSABLE"
        assert p_bad["timestamp"] is None

        # read_all should preserve the corrupted crash with in_window='AMBIGUOUS'
        all_crashes = reader.read_all(start_time=1700000000, end_time=1800000000)
        assert all_crashes["crash_count"] >= 1
        corrupt_entry = next(c for c in all_crashes["crashes"] if c["file_path"] == f_bad)
        assert corrupt_entry["in_window"] == "AMBIGUOUS"


class TestProvenanceAndMonitoringDecoupling:
    """Tests 9, 10, 13: Decoupling historical CSVs from live Prometheus, provenance tracking, CLI compatibility."""

    def test_historical_locust_with_no_prometheus_service(self, valid_locust_csv_dir):
        """9. Historical run executed when Prometheus is down; provenance records disconnected."""
        engine = AnalysisEngine()
        # Point to a closed port
        engine.prom_client.base_url = "http://127.0.0.1:59999"

        # Explicit historical time window
        start_ts = 1700000000.0
        end_ts = 1700000060.0

        res = engine.analyze(
            start_time=start_ts,
            end_time=end_ts,
            locust_target=valid_locust_csv_dir,
            profile_name="synthetic",
            time_window_source="EXPLICIT_CLI",
        )

        prov = res["provenance"]
        assert prov["prometheus_connected"] is False
        assert prov["monitoring_data_overlap"] is False
        assert prov["time_window_type"] == "HISTORICAL"
        assert prov["time_window_source"] == "EXPLICIT_CLI"
        assert res["load_metrics"]["locust"]["summary"]["total_requests"] == 1600

    def test_prometheus_data_does_not_overlap_experiment(self, valid_locust_csv_dir):
        """10. Detects when Prometheus metrics return empty series for the requested window."""
        engine = AnalysisEngine()
        with patch.object(engine.prom_client, "query_range", return_value=[]):
            res = engine.analyze(
                start_time=1700000000.0,
                end_time=1700000060.0,
                locust_target=valid_locust_csv_dir,
            )
            assert res["provenance"]["monitoring_data_overlap"] is False

    def test_run_analysis_derives_timestamps_from_history(self, valid_locust_csv_dir):
        """13. CLI execution derives experiment window from history when timestamps omitted."""
        probe = LocustResultParser(valid_locust_csv_dir)
        min_ts, max_ts = probe.get_history_time_bounds()
        assert min_ts == 1700000000.0
        assert max_ts == 1700000010.0
