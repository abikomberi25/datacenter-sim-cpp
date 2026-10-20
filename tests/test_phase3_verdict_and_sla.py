import os
import math
import pytest
from unittest.mock import MagicMock

from analysis.sla import SLAEvaluator
from analysis.analyse import AnalysisEngine
from analysis.network_monitor import NetworkMonitor
from analysis.system_monitor import SystemMonitor
from analysis.locust_results import LocustResultParser

@pytest.fixture
def base_sla_config():
    return {
        "sla": {
            "p95_latency_ms": 500.0,
            "error_rate_pct": 1.0,
            "cpu_pct": 80.0,
            "memory_pct": 90.0,
        }
    }

class TestDEF002VerdictCorrectnessAndSLA:
    """Tests for DEF-002: Prevent false PASS on empty or incomplete data."""

    def test_empty_locust_data_produces_incomplete_not_pass(self, base_sla_config):
        """Zero requests must not produce 0ms latency or PASS verdict."""
        evaluator = SLAEvaluator(base_sla_config)

        # Empty locust summary
        locust_summary = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "error_rate_pct": None,
            "p95_latency_ms": None,
            "is_empty": True,
        }
        cpu_metrics = {"available": True, "peak": 35.0}
        mem_metrics = {"available": True, "peak": 50.0}

        report = evaluator.evaluate(locust_summary, cpu_metrics, mem_metrics)

        assert report["overall_status"] == "INCOMPLETE"
        assert report["has_sufficient_evidence"] is False
        assert report["unknown_count"] == 2  # p95 and error_rate
        assert report["passed_count"] == 2   # cpu and memory
        assert report["failed_count"] == 0
        assert report["evaluations"]["p95_latency"]["status"] == "UNKNOWN"
        assert report["evaluations"]["p95_latency"]["evaluated"] is False
        assert report["evaluations"]["error_rate"]["status"] == "UNKNOWN"
        assert report["evaluations"]["error_rate"]["evaluated"] is False

    def test_zero_requests_with_healthy_system_never_passes(self, base_sla_config):
        """Even with 0% CPU and 0% memory, zero load requests must yield INCOMPLETE."""
        evaluator = SLAEvaluator(base_sla_config)

        locust_summary = {"total_requests": 0, "is_empty": True}
        cpu_metrics = {"available": True, "peak": 0.0}
        mem_metrics = {"available": True, "peak": 0.0}

        report = evaluator.evaluate(locust_summary, cpu_metrics, mem_metrics)
        assert report["overall_status"] == "INCOMPLETE"
        assert report["overall_status"] != "PASS"

    def test_coexisting_failure_and_missing_metric_yields_fail(self, base_sla_config):
        """When an evaluated metric fails while another is missing, overall must be FAIL with incomplete coverage noted."""
        evaluator = SLAEvaluator(base_sla_config)

        # Latency fails (1200ms > 500ms), but Prometheus CPU/Memory is missing
        locust_summary = {
            "total_requests": 500,
            "p95_latency_ms": 1200.0,
            "error_rate_pct": 0.2,
            "is_empty": False,
        }
        cpu_metrics = {"available": False}
        mem_metrics = {"available": False}

        report = evaluator.evaluate(locust_summary, cpu_metrics, mem_metrics)

        assert report["overall_status"] == "FAIL"
        assert report["failed_count"] == 1
        assert report["passed_count"] == 1  # error rate 0.2% <= 1.0%
        assert report["unknown_count"] == 2  # cpu, mem
        assert report["has_sufficient_evidence"] is False
        assert len(report["violations"]) == 1
        assert "P95 Response Time" in report["violations"][0]
        assert len(report["missing_evidence"]) == 2

    def test_all_metrics_pass_when_evidence_is_sufficient(self, base_sla_config):
        """All valid metrics within boundaries produce PASS."""
        evaluator = SLAEvaluator(base_sla_config)

        locust_summary = {
            "total_requests": 1500,
            "p95_latency_ms": 220.0,
            "error_rate_pct": 0.0,
            "is_empty": False,
        }
        cpu_metrics = {"available": True, "peak": 65.0}
        mem_metrics = {"available": True, "peak": 72.0}

        report = evaluator.evaluate(locust_summary, cpu_metrics, mem_metrics)

        assert report["overall_status"] == "PASS"
        assert report["has_sufficient_evidence"] is True
        assert report["passed_count"] == 4
        assert report["failed_count"] == 0
        assert report["unknown_count"] == 0
        assert len(report["violations"]) == 0
        assert len(report["missing_evidence"]) == 0

    def test_non_finite_nan_and_inf_handled_defensively(self, base_sla_config):
        """NaN and Inf metric values must be marked UNKNOWN, not parsed as valid numbers."""
        evaluator = SLAEvaluator(base_sla_config)

        locust_summary = {
            "total_requests": 200,
            "p95_latency_ms": float("nan"),
            "error_rate_pct": float("inf"),
            "is_empty": False,
        }
        cpu_metrics = {"available": True, "peak": "NaN"}
        mem_metrics = {"available": True, "peak": None}

        report = evaluator.evaluate(locust_summary, cpu_metrics, mem_metrics)

        assert report["overall_status"] == "INCOMPLETE"
        assert report["unknown_count"] == 4
        for ev in report["evaluations"].values():
            assert ev["status"] == "UNKNOWN"
            assert ev["evaluated"] is False


class TestDEF005ContradictoryBottlenecks:
    """Tests for DEF-005: Eliminate contradictory bottleneck classifications."""

    def test_cpu_breach_without_latency_breach_classified_as_resource_saturation(self):
        """CPU at 82.37% (> 80.0% SLA) with P95 at 110ms must NOT be classified as SYSTEM_HEALTHY."""
        engine = AnalysisEngine()

        cpu_metrics = {"available": True, "peak": 82.37}
        mem_metrics = {"available": True, "peak": 60.0}
        net_metrics = {"available": True}
        locust_summary = {"total_requests": 500, "p95_latency_ms": 110.0, "is_empty": False}
        sla_report = {
            "thresholds": {"p95_latency_ms": 500.0, "cpu_pct": 80.0, "memory_pct": 90.0},
            "overall_status": "FAIL",
            "passed_count": 3,
            "total_checks": 4,
            "violations": ["Peak CPU Utilization: measured 82.37 % exceeds limit 80.0 %"],
        }

        bn = engine._detect_bottlenecks(
            cpu_metrics, mem_metrics, net_metrics, locust_summary, [], sla_report
        )

        assert bn["classification"] == "RESOURCE_SATURATION"
        assert bn["primary_bottleneck"] == "CPU Utilization"
        assert "CPU" in bn["suspected_resources"]
        # Verify no contradictory statement was generated
        for ev in bn["evidence"]:
            assert "All measured system and load parameters remained within safe thresholds" not in ev

        conclusion = engine._generate_conclusion(
            sla_report, bn, {"failure_type": "SLA_NON_COMPLIANCE"}, {"crash_count": 0}, locust_summary
        )
        assert "Primary bottleneck assessed as 'CPU Utilization'" in conclusion
        assert "Primary bottleneck assessed as 'None'" not in conclusion
        assert "within all performance, reliability, and resource boundaries" not in conclusion

    def test_severe_cpu_and_latency_breach_confirmed_bottleneck(self):
        """CPU >= 90% and P95 > SLA must be classified as CONFIRMED_BOTTLENECK."""
        engine = AnalysisEngine()

        cpu_metrics = {"available": True, "peak": 94.5}
        mem_metrics = {"available": True, "peak": 70.0}
        net_metrics = {"available": True}
        locust_summary = {"total_requests": 1000, "p95_latency_ms": 850.0, "is_empty": False}
        sla_report = {
            "thresholds": {"p95_latency_ms": 500.0, "cpu_pct": 80.0, "memory_pct": 90.0},
            "overall_status": "FAIL",
            "passed_count": 2,
            "total_checks": 4,
        }

        bn = engine._detect_bottlenecks(
            cpu_metrics, mem_metrics, net_metrics, locust_summary, [], sla_report
        )

        assert bn["classification"] == "CONFIRMED_BOTTLENECK"
        assert bn["primary_bottleneck"] == "CPU Saturation & Application Concurrency"

    def test_correlated_cpu_breach_and_latency_breach(self):
        """CPU > 80% but < 90% and P95 > SLA must be classified as CORRELATED_BOTTLENECK."""
        engine = AnalysisEngine()

        cpu_metrics = {"available": True, "peak": 85.0}
        mem_metrics = {"available": True, "peak": 65.0}
        net_metrics = {"available": True}
        locust_summary = {"total_requests": 800, "p95_latency_ms": 650.0, "is_empty": False}
        sla_report = {
            "thresholds": {"p95_latency_ms": 500.0, "cpu_pct": 80.0, "memory_pct": 90.0},
            "overall_status": "FAIL",
            "passed_count": 2,
            "total_checks": 4,
        }

        bn = engine._detect_bottlenecks(
            cpu_metrics, mem_metrics, net_metrics, locust_summary, [], sla_report
        )

        assert bn["classification"] == "CORRELATED_BOTTLENECK"
        assert bn["primary_bottleneck"] == "CPU / Application Processing"

    def test_latency_breach_only_is_performance_degradation(self):
        """Latency > SLA with healthy system resources is PERFORMANCE_DEGRADATION."""
        engine = AnalysisEngine()

        cpu_metrics = {"available": True, "peak": 40.0}
        mem_metrics = {"available": True, "peak": 45.0}
        net_metrics = {"available": True}
        locust_summary = {"total_requests": 600, "p95_latency_ms": 750.0, "is_empty": False}
        sla_report = {
            "thresholds": {"p95_latency_ms": 500.0, "cpu_pct": 80.0, "memory_pct": 90.0},
            "overall_status": "FAIL",
            "passed_count": 3,
            "total_checks": 4,
        }

        bn = engine._detect_bottlenecks(
            cpu_metrics, mem_metrics, net_metrics, locust_summary, [], sla_report
        )

        assert bn["classification"] == "PERFORMANCE_DEGRADATION"
        assert bn["primary_bottleneck"] == "Application / Endpoint Latency"


class TestDEF006MonitoringUnavailableEvidenceGap:
    """Tests for DEF-006: Missing monitoring data is an evidence gap, not an application bottleneck."""

    def test_missing_prometheus_is_insufficient_evidence_not_monitoring_bottleneck(self):
        """When Prometheus is down, primary bottleneck must NOT be 'Monitoring Unavailable'."""
        engine = AnalysisEngine()

        cpu_metrics = {"available": False}
        mem_metrics = {"available": False}
        net_metrics = {"available": False}
        locust_summary = {"total_requests": 500, "p95_latency_ms": 150.0, "is_empty": False}
        sla_report = {
            "thresholds": {"p95_latency_ms": 500.0, "cpu_pct": 80.0, "memory_pct": 90.0},
            "overall_status": "INCOMPLETE",
            "passed_count": 2,
            "total_checks": 4,
        }

        bn = engine._detect_bottlenecks(
            cpu_metrics, mem_metrics, net_metrics, locust_summary, [], sla_report
        )

        assert bn["classification"] == "INSUFFICIENT_EVIDENCE"
        assert bn["primary_bottleneck"] == "None"
        assert bn["primary_bottleneck"] != "Monitoring Unavailable"
        assert bn["confidence"] == "LOW"

        conclusion = engine._generate_conclusion(
            sla_report, bn, {"failure_type": "NO_FAILURES"}, {"crash_count": 0}, locust_summary
        )
        assert "Monitoring Unavailable" not in conclusion
        assert "INCOMPLETE" in conclusion


class TestDEF007NetworkMonitorUnits:
    """Tests for DEF-007: Binary IEC throughput units."""

    def test_network_monitor_binary_iec_units(self):
        """Verify binary units (MiB, MiB/s) and backward-compatible alias keys."""
        mock_prom = MagicMock()
        mock_prom.get_label_values.return_value = ["eth0"]
        # Start and end counters: 104,857,600 bytes difference = 100 MiB
        mock_prom.query.side_effect = [
            [{"value": [1000, "100000000"]}],  # rx_start
            [{"value": [1000, "50000000"]}],   # tx_start
            [{"value": [1100, "204857600"]}],  # rx_end (104,857,600 delta = 100 MiB)
            [{"value": [1100, "102428800"]}],  # tx_end (52,428,800 delta = 50 MiB)
        ]
        # Range queries: 10 MiB/s and 5 MiB/s
        mock_prom.query_range.side_effect = [
            [{"values": [[1050, "10.0"]]}],  # rx_rate
            [{"values": [[1050, "5.0"]]}],   # tx_rate
        ]

        net_mon = NetworkMonitor(mock_prom, mode="host")
        metrics = net_mon.get_network_metrics(1000, 1100)

        assert metrics["available"] is True
        assert metrics["unit_total"] == "MiB"
        assert metrics["unit_rate"] == "MiB/s"
        assert metrics["total_rx_mib"] == 100.0
        assert metrics["total_tx_mib"] == 50.0
        assert metrics["peak_rx_mib_s"] == 10.0
        assert metrics["peak_tx_mib_s"] == 5.0

        # Backward compatibility aliases
        assert metrics["total_rx_mb"] == metrics["total_rx_mib"]
        assert metrics["total_tx_mb"] == metrics["total_tx_mib"]
        assert metrics["peak_rx_MBps"] == metrics["peak_rx_mib_s"]
        assert metrics["peak_tx_MBps"] == metrics["peak_tx_mib_s"]


class TestDEF008SystemMonitorMetrics:
    """Tests for DEF-008: Node CPU metrics interpretation and NaN resilience."""

    def test_cpu_rate_window_configuration(self):
        """SystemMonitor must allow configurable rate window and construct aligned query."""
        mock_prom = MagicMock()
        mock_prom.query_range.return_value = [{"values": [[1000, "45.0"], [1005, "55.0"]]}]

        mon = SystemMonitor(mock_prom, rate_window_seconds=15)
        res = mon.get_cpu_utilization(1000, 1050)

        assert res["available"] is True
        assert res["average"] == 50.0
        assert res["peak"] == 55.0

        # Verify rate window in Prometheus query
        call_query = mock_prom.query_range.call_args[0][0]
        assert "[15s]" in call_query

    def test_system_monitor_nan_and_inf_filtering(self):
        """SystemMonitor must ignore NaN and Inf values without crashing."""
        mock_prom = MagicMock()
        mock_prom.query_range.return_value = [
            {"values": [[1000, "40.0"], [1005, "NaN"], [1010, "inf"], [1015, "60.0"]]}
        ]

        mon = SystemMonitor(mock_prom)
        res = mon.get_cpu_utilization(1000, 1050)

        assert res["available"] is True
        assert len(res["series"]) == 2
        assert res["average"] == 50.0
        assert res["peak"] == 60.0


class TestSLAErrorRateBoundaryEvaluation:
    """Tests for SLA error-rate boundary conditions (exact, slightly below, slightly above)."""

    def test_error_rate_exactly_at_threshold_passes(self, base_sla_config):
        """When error rate is exactly at 1.0% (100 / 10000), verdict is PASS with margin 0.0."""
        evaluator = SLAEvaluator(base_sla_config)
        locust_summary = {
            "total_requests": 10000,
            "failed_requests": 100,
            "successful_requests": 9900,
            "error_rate_pct": 1.0,
            "p95_latency_ms": 100.0,
            "is_empty": False,
        }
        res = evaluator.evaluate(locust_summary, {"available": True, "peak": 10.0}, {"available": True, "peak": 10.0})
        ev = res["evaluations"]["error_rate"]
        assert ev["status"] == "PASS"
        assert ev["evaluated"] is True
        assert ev["measured_value"] == 1.0
        assert ev["margin"] == 0.0

    def test_error_rate_slightly_below_threshold_passes(self, base_sla_config):
        """When error rate is slightly below 1.0% (82 / 8275 = 0.9909%), verdict is PASS."""
        evaluator = SLAEvaluator(base_sla_config)
        locust_summary = {
            "total_requests": 8275,
            "failed_requests": 82,
            "successful_requests": 8193,
            "error_rate_pct": 0.9909,
            "p95_latency_ms": 100.0,
            "is_empty": False,
        }
        res = evaluator.evaluate(locust_summary, {"available": True, "peak": 10.0}, {"available": True, "peak": 10.0})
        ev = res["evaluations"]["error_rate"]
        assert ev["status"] == "PASS"
        assert ev["evaluated"] is True
        assert ev["measured_value"] == 0.9909
        assert ev["margin"] > 0.0

    def test_error_rate_slightly_above_threshold_fails_unrounded(self, base_sla_config):
        """When error rate is slightly above 1.0% (83 / 8275 = 1.003%), verdict is strictly FAIL."""
        evaluator = SLAEvaluator(base_sla_config)
        # Even if error_rate_pct in legacy input was pre-rounded to 1.0, exact counts trigger FAIL
        locust_summary = {
            "total_requests": 8275,
            "failed_requests": 83,
            "successful_requests": 8192,
            "error_rate_pct": 1.0,  # simulate legacy 2-decimal truncation
            "p95_latency_ms": 100.0,
            "is_empty": False,
        }
        res = evaluator.evaluate(locust_summary, {"available": True, "peak": 10.0}, {"available": True, "peak": 10.0})
        ev = res["evaluations"]["error_rate"]
        assert ev["status"] == "FAIL"
        assert ev["evaluated"] is True
        assert ev["measured_value"] == 1.003
        assert ev["margin"] == -0.003
        assert res["overall_status"] == "FAIL"
        assert any("Error Rate: measured 1.003 % exceeds limit 1.0 %" in v for v in res["violations"])

