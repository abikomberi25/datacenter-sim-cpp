import logging
import math
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
        Missing, non-finite, or empty metrics are marked as UNKNOWN / not evaluated (never silently passed).

        :param locust_summary: Dict from LocustResultParser['summary']
        :param cpu_metrics: Dict from SystemMonitor.get_cpu_utilization()
        :param memory_metrics: Dict from SystemMonitor.get_memory_utilization()
        :return: Structured SLA evaluation report with individual and overall verdicts.
        """
        locust_summary = locust_summary or {}
        cpu_metrics = cpu_metrics or {}
        memory_metrics = memory_metrics or {}

        total_reqs = locust_summary.get("total_requests")
        is_empty = bool(locust_summary.get("is_empty", False))
        has_valid_requests = bool(total_reqs is not None and total_reqs > 0 and not is_empty)

        # 1. P95 Latency
        p95_val = None
        if has_valid_requests:
            p95_raw = locust_summary.get("p95_latency_ms")
            try:
                if p95_raw is not None:
                    parsed = float(p95_raw)
                    if math.isfinite(parsed):
                        p95_val = parsed
            except (ValueError, TypeError):
                p95_val = None

        if p95_val is not None:
            p95_status = "PASS" if p95_val <= self.p95_latency_limit else "FAIL"
            p95_evaluated = True
            p95_margin = round(self.p95_latency_limit - p95_val, 2)
        else:
            p95_status = "UNKNOWN"
            p95_evaluated = False
            p95_margin = None

        # 2. Error Rate (unrounded numeric comparison)
        error_rate_val = None
        if has_valid_requests:
            # Prefer unrounded calculation from exact integer counts when available
            failed_reqs = locust_summary.get("failed_requests")
            total_reqs_val = locust_summary.get("total_requests")
            if total_reqs_val is not None and failed_reqs is not None and total_reqs_val > 0:
                try:
                    parsed_f = float(failed_reqs)
                    parsed_t = float(total_reqs_val)
                    if math.isfinite(parsed_f) and math.isfinite(parsed_t) and parsed_t > 0:
                        error_rate_val = (parsed_f / parsed_t) * 100.0
                except (ValueError, TypeError):
                    error_rate_val = None

            if error_rate_val is None:
                err_raw = locust_summary.get("error_rate_pct")
                try:
                    if err_raw is not None:
                        parsed = float(err_raw)
                        if math.isfinite(parsed):
                            error_rate_val = parsed
                except (ValueError, TypeError):
                    error_rate_val = None

        if error_rate_val is not None:
            # Unrounded numeric comparison: values strictly exceeding limit fail
            error_rate_status = "PASS" if error_rate_val <= self.error_rate_limit else "FAIL"
            error_rate_evaluated = True
            error_rate_margin = round(self.error_rate_limit - error_rate_val, 4)
            measured_error_rate = round(error_rate_val, 4)
        else:
            error_rate_status = "UNKNOWN"
            error_rate_evaluated = False
            error_rate_margin = None
            measured_error_rate = None

        # 3. Peak CPU Utilization
        cpu_available = bool(cpu_metrics.get("available", False))
        cpu_raw = cpu_metrics.get("peak") if cpu_available else None
        cpu_peak_val = None
        try:
            if cpu_raw is not None:
                parsed = float(cpu_raw)
                if math.isfinite(parsed):
                    cpu_peak_val = parsed
        except (ValueError, TypeError):
            cpu_peak_val = None

        if cpu_peak_val is not None:
            cpu_status = "PASS" if cpu_peak_val <= self.cpu_limit else "FAIL"
            cpu_evaluated = True
            cpu_margin = round(self.cpu_limit - cpu_peak_val, 2)
        else:
            cpu_status = "UNKNOWN"
            cpu_evaluated = False
            cpu_margin = None

        # 4. Peak Memory Utilization
        mem_available = bool(memory_metrics.get("available", False))
        mem_raw = memory_metrics.get("peak") if mem_available else None
        mem_peak_val = None
        try:
            if mem_raw is not None:
                parsed = float(mem_raw)
                if math.isfinite(parsed):
                    mem_peak_val = parsed
        except (ValueError, TypeError):
            mem_peak_val = None

        if mem_peak_val is not None:
            mem_status = "PASS" if mem_peak_val <= self.memory_limit else "FAIL"
            mem_evaluated = True
            mem_margin = round(self.memory_limit - mem_peak_val, 2)
        else:
            mem_status = "UNKNOWN"
            mem_evaluated = False
            mem_margin = None

        evaluations = {
            "p95_latency": {
                "metric_name": "P95 Response Time",
                "measured_value": p95_val,
                "threshold": self.p95_latency_limit,
                "unit": "ms",
                "status": p95_status,
                "evaluated": p95_evaluated,
                "margin": p95_margin,
            },
            "error_rate": {
                "metric_name": "Error Rate",
                "measured_value": measured_error_rate,
                "threshold": self.error_rate_limit,
                "unit": "%",
                "status": error_rate_status,
                "evaluated": error_rate_evaluated,
                "margin": error_rate_margin,
            },
            "cpu_utilization": {
                "metric_name": "Peak CPU Utilization",
                "measured_value": cpu_peak_val,
                "threshold": self.cpu_limit,
                "unit": "%",
                "status": cpu_status,
                "evaluated": cpu_evaluated,
                "margin": cpu_margin,
            },
            "memory_utilization": {
                "metric_name": "Peak Memory Utilization",
                "measured_value": mem_peak_val,
                "threshold": self.memory_limit,
                "unit": "%",
                "status": mem_status,
                "evaluated": mem_evaluated,
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
        missing_evidence = []
        for k, info in evaluations.items():
            if info["status"] == "FAIL":
                violations.append(
                    f"{info['metric_name']}: measured {info['measured_value']} {info['unit']} exceeds limit {info['threshold']} {info['unit']}"
                )
            elif info["status"] == "UNKNOWN":
                missing_evidence.append(
                    f"{info['metric_name']}: metric unavailable; cannot evaluate against limit {info['threshold']} {info['unit']}"
                )

        return {
            "overall_status": overall_status,
            "passed_count": sum(1 for v in evaluations.values() if v["status"] == "PASS"),
            "failed_count": sum(1 for v in evaluations.values() if v["status"] == "FAIL"),
            "unknown_count": sum(1 for v in evaluations.values() if v["status"] == "UNKNOWN"),
            "evaluated_count": sum(1 for v in evaluations.values() if v.get("evaluated", False)),
            "has_sufficient_evidence": not any_unknown,
            "total_checks": len(evaluations),
            "evaluations": evaluations,
            "violations": violations,
            "missing_evidence": missing_evidence,
            "thresholds": {
                "p95_latency_ms": self.p95_latency_limit,
                "error_rate_pct": self.error_rate_limit,
                "cpu_pct": self.cpu_limit,
                "memory_pct": self.memory_limit,
            },
        }
