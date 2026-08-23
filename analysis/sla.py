import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SLAEvaluator:
    """
    Evaluates system performance against configured Service Level Agreement (SLA) targets:
    - P95 Latency: <= p95_latency_ms (e.g. 500ms)
    - Error Rate: <= error_rate_pct (e.g. 1.0%)
    - CPU Utilization: Peak <= cpu_pct (e.g. 80.0%)
    - Memory Utilization: Peak <= memory_pct (e.g. 90.0%)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        :param config: Dictionary loaded from config.yaml or specific sla sub-dictionary.
        """
        sla_cfg = config.get("sla", config)
        self.p95_latency_limit = float(sla_cfg.get("p95_latency_ms", 500.0))
        self.error_rate_limit = float(sla_cfg.get("error_rate_pct", 1.0))
        self.cpu_limit = float(sla_cfg.get("cpu_pct", 80.0))
        self.memory_limit = float(sla_cfg.get("memory_pct", 90.0))

    def evaluate(
        self,
        locust_summary: Optional[Dict[str, Any]],
        cpu_metrics: Optional[Dict[str, Any]],
        memory_metrics: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluates metrics against SLA thresholds.
        Missing or empty metrics are marked as UNKNOWN (not silently passed).

        :param locust_summary: Dict from LocustResultParser['summary']
        :param cpu_metrics: Dict from SystemMonitor.get_cpu_utilization()
        :param memory_metrics: Dict from SystemMonitor.get_memory_utilization()
        :return: Structured SLA evaluation report with individual and overall verdicts.
        """
        locust_summary = locust_summary or {}
        cpu_metrics = cpu_metrics or {}
        memory_metrics = memory_metrics or {}

        # 1. P95 Latency
        p95_raw = locust_summary.get("p95_latency_ms")
        p95_val = float(p95_raw) if p95_raw is not None else None
        p95_status = "UNKNOWN" if p95_val is None else ("PASS" if p95_val <= self.p95_latency_limit else "FAIL")
        p95_margin = round(self.p95_latency_limit - p95_val, 2) if p95_val is not None else None

        # 2. Error Rate
        err_raw = locust_summary.get("error_rate_pct")
        error_rate_val = float(err_raw) if err_raw is not None else None
        error_rate_status = "UNKNOWN" if error_rate_val is None else ("PASS" if error_rate_val <= self.error_rate_limit else "FAIL")
        error_rate_margin = round(self.error_rate_limit - error_rate_val, 2) if error_rate_val is not None else None

        # 3. Peak CPU Utilization
        cpu_available = bool(cpu_metrics.get("available", False))
        cpu_raw = cpu_metrics.get("peak") if cpu_available else None
        cpu_peak_val = float(cpu_raw) if cpu_raw is not None else None
        cpu_status = "UNKNOWN" if cpu_peak_val is None else ("PASS" if cpu_peak_val <= self.cpu_limit else "FAIL")
        cpu_margin = round(self.cpu_limit - cpu_peak_val, 2) if cpu_peak_val is not None else None

        # 4. Peak Memory Utilization
        mem_available = bool(memory_metrics.get("available", False))
        mem_raw = memory_metrics.get("peak") if mem_available else None
        mem_peak_val = float(mem_raw) if mem_raw is not None else None
        mem_status = "UNKNOWN" if mem_peak_val is None else ("PASS" if mem_peak_val <= self.memory_limit else "FAIL")
        mem_margin = round(self.memory_limit - mem_peak_val, 2) if mem_peak_val is not None else None

        evaluations = {
            "p95_latency": {
                "metric_name": "P95 Response Time",
                "measured_value": p95_val,
                "threshold": self.p95_latency_limit,
                "unit": "ms",
                "status": p95_status,
                "margin": p95_margin,
            },
            "error_rate": {
                "metric_name": "Error Rate",
                "measured_value": error_rate_val,
                "threshold": self.error_rate_limit,
                "unit": "%",
                "status": error_rate_status,
                "margin": error_rate_margin,
            },
            "cpu_utilization": {
                "metric_name": "Peak CPU Utilization",
                "measured_value": cpu_peak_val,
                "threshold": self.cpu_limit,
                "unit": "%",
                "status": cpu_status,
                "margin": cpu_margin,
            },
            "memory_utilization": {
                "metric_name": "Peak Memory Utilization",
                "measured_value": mem_peak_val,
                "threshold": self.memory_limit,
                "unit": "%",
                "status": mem_status,
                "margin": mem_margin,
            },
        }

        # Status precedence: Any FAIL -> FAIL; else any UNKNOWN -> INCOMPLETE; else PASS
        any_failed = any(ev["status"] == "FAIL" for ev in evaluations.values())
        any_unknown = any(ev["status"] == "UNKNOWN" for ev in evaluations.values())

        if any_failed:
            overall_status = "FAIL"
        elif any_unknown:
            overall_status = "INCOMPLETE"
        else:
            overall_status = "PASS"

        violations = []
        for k, info in evaluations.items():
            if info["status"] == "FAIL":
                violations.append(
                    f"{info['metric_name']}: measured {info['measured_value']} {info['unit']} exceeds limit {info['threshold']} {info['unit']}"
                )
            elif info["status"] == "UNKNOWN":
                violations.append(
                    f"{info['metric_name']}: metric unavailable; cannot evaluate against limit {info['threshold']} {info['unit']}"
                )

        return {
            "overall_status": overall_status,
            "passed_count": sum(1 for v in evaluations.values() if v["status"] == "PASS"),
            "failed_count": sum(1 for v in evaluations.values() if v["status"] == "FAIL"),
            "unknown_count": sum(1 for v in evaluations.values() if v["status"] == "UNKNOWN"),
            "total_checks": len(evaluations),
            "evaluations": evaluations,
            "violations": violations,
            "thresholds": {
                "p95_latency_ms": self.p95_latency_limit,
                "error_rate_pct": self.error_rate_limit,
                "cpu_pct": self.cpu_limit,
                "memory_pct": self.memory_limit,
            },
        }

