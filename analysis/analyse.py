import os
import time
import yaml
import logging
from typing import Dict, Any, List, Optional

from analysis.prometheus_client import PrometheusClient
from analysis.system_monitor import SystemMonitor
from analysis.network_monitor import NetworkMonitor
from analysis.locust_results import LocustResultParser
from analysis.sla import SLAEvaluator
from analysis.watchdog_reader import WatchdogReader
from analysis.event_timeline import EventTimelineBuilder

logger = logging.getLogger(__name__)

class AnalysisEngine:
    """
    Orchestrates the complete Member 6 Analysis & Reporting pipeline:
    - Ingests measurements across Prometheus, Locust, and Watchdog without inventing data.
    - Evaluates SLA compliance.
    - Performs evidence-based Bottleneck Detection with strict classification:
      (SLA_VIOLATION vs RESOURCE_SATURATION vs PERFORMANCE_DEGRADATION vs CONFIRMED_BOTTLENECK vs POSSIBLE_BOTTLENECK vs INSUFFICIENT_EVIDENCE).
    - Synthesizes multi-factor Failure Analysis.
    - Constructs the chronological Event Timeline.
    - Produces a unified structured analysis output dictionary.
    """

    def __init__(self, config_path: str = "analysis/config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()
        
        prom_url = self.config.get("prometheus_url", "http://localhost:9090")
        sampling_sec = self.config.get("sampling", {}).get("interval_seconds", 5)
        rate_window_sec = self.config.get("rate_window_seconds", 15)
        net_cfg = self.config.get("network", {})
        net_mode = net_cfg.get("node_exporter_mode", "bridge")
        net_fallback = net_cfg.get("fallback_to_container", True)

        self.prom_client = PrometheusClient(prom_url)
        self.sys_monitor = SystemMonitor(self.prom_client, mode=net_mode, sampling_interval_seconds=sampling_sec)
        self.net_monitor = NetworkMonitor(
            self.prom_client,
            mode=net_mode,
            fallback=net_fallback,
            rate_window_seconds=rate_window_sec,
            sampling_interval_seconds=sampling_sec,
        )
        self.sla_evaluator = SLAEvaluator(self.config)
        self.watchdog_reader = WatchdogReader(logs_dir="logs")
        self.timeline_builder = EventTimelineBuilder()

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file not found at {self.config_path}, using defaults.")
            return {}
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def analyze(
        self,
        start_time: float,
        end_time: float,
        locust_target: str,
        profile_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes the unified analysis over the experiment time window [start_time, end_time].
        """
        duration = max(0.0, round(end_time - start_time, 2))

        # 1. Capture Prometheus System & Network Metrics
        cpu_metrics = self.sys_monitor.get_cpu_utilization(start_time, end_time)
        memory_metrics = self.sys_monitor.get_memory_utilization(start_time, end_time)
        network_metrics = self.net_monitor.get_network_metrics(start_time, end_time)

        # 2. Parse Locust Performance Results
        locust_parser = LocustResultParser(locust_target)
        locust_data = locust_parser.parse()
        locust_summary = locust_data.get("summary", {})

        # 3. Read Watchdog Crash Logs
        watchdog_data = self.watchdog_reader.read_all(start_time=start_time, end_time=end_time)

        # 4. Evaluate SLA Compliance
        sla_report = self.sla_evaluator.evaluate(
            locust_summary=locust_summary,
            cpu_metrics=cpu_metrics,
            memory_metrics=memory_metrics,
        )

        # 5. Build Chronological Event Timeline
        timeline_events = self.timeline_builder.build(
            experiment_start=start_time,
            experiment_end=end_time,
            locust_data=locust_data,
            cpu_metrics=cpu_metrics,
            memory_metrics=memory_metrics,
            network_metrics=network_metrics,
            watchdog_data=watchdog_data,
            sla_data=sla_report,
        )

        # 6. Conduct Bottleneck Analysis
        bottleneck_analysis = self._detect_bottlenecks(
            cpu_metrics=cpu_metrics,
            memory_metrics=memory_metrics,
            network_metrics=network_metrics,
            locust_summary=locust_summary,
            locust_endpoints=locust_data.get("endpoints", []),
            sla_report=sla_report,
        )

        # 7. Conduct Failure Analysis
        failure_analysis = self._analyze_failures(
            locust_data=locust_data,
            watchdog_data=watchdog_data,
            sla_report=sla_report,
            cpu_metrics=cpu_metrics,
            memory_metrics=memory_metrics,
        )

        # 8. Synthesize Overall Conclusion
        conclusion = self._generate_conclusion(
            sla_report=sla_report,
            bottleneck_analysis=bottleneck_analysis,
            failure_analysis=failure_analysis,
            watchdog_data=watchdog_data,
            locust_summary=locust_summary,
        )

        return {
            "experiment": {
                "profile": profile_name or "unknown",
                "start_time": start_time,
                "end_time": end_time,
                "duration_seconds": duration,
            },
            "system_metrics": {
                "cpu": cpu_metrics,
                "memory": memory_metrics,
                "network": network_metrics,
            },
            "load_metrics": {
                "locust": locust_data,
            },
            "sla": sla_report,
            "crashes": watchdog_data,
            "bottleneck_analysis": bottleneck_analysis,
            "failure_analysis": failure_analysis,
            "timeline": timeline_events,
            "conclusion": conclusion,
        }

    def _detect_bottlenecks(
        self,
        cpu_metrics: Dict[str, Any],
        memory_metrics: Dict[str, Any],
        network_metrics: Dict[str, Any],
        locust_summary: Dict[str, Any],
        locust_endpoints: List[Dict[str, Any]],
        sla_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evidence-based bottleneck detection distinguishing:
        - Resource Saturation (CPU > 90%, Memory > 90%)
        - SLA Violations (CPU/P95 breaches)
        - Endpoint Latency Disparities
        - Statistical Confidence based on sample size
        """
        evidence: List[str] = []
        suspects: List[str] = []
        classification = "NO_BOTTLENECK_DETECTED"
        primary = "None"
        confidence = "HIGH"

        # Check sample size robustness
        total_reqs = locust_summary.get("total_requests", 0)
        if total_reqs < 100:
            confidence = "LOW_SAMPLE_SIZE"
            evidence.append(
                f"Low request volume ({total_reqs} requests); statistical latency metrics are tentative."
            )

        cpu_peak = cpu_metrics.get("peak")
        mem_peak = memory_metrics.get("peak")
        p95_latency = locust_summary.get("p95_latency_ms")
        p95_sla = sla_report.get("thresholds", {}).get("p95_latency_ms", 500.0)
        cpu_sla = sla_report.get("thresholds", {}).get("cpu_pct", 80.0)
        mem_sla = sla_report.get("thresholds", {}).get("memory_pct", 90.0)

        # 1. CPU Evaluation
        if cpu_peak is not None:
            if cpu_peak >= 90.0:
                suspects.append("CPU")
                evidence.append(f"Severe CPU saturation detected: peak reached {cpu_peak}% (>= 90%).")
            elif cpu_peak > cpu_sla:
                suspects.append("CPU")
                evidence.append(f"CPU SLA breach: peak {cpu_peak}% exceeded threshold {cpu_sla}%.")

        # 2. Memory Evaluation
        if mem_peak is not None:
            if mem_peak >= 90.0:
                suspects.append("MEMORY")
                evidence.append(f"Memory exhaustion risk: peak reached {mem_peak}% (>= 90%).")
            elif mem_peak > mem_sla:
                suspects.append("MEMORY")
                evidence.append(f"Memory SLA breach: peak {mem_peak}% exceeded threshold {mem_sla}%.")

        # 3. Latency Evaluation & Endpoint Disparity
        if p95_latency is not None and p95_latency > p95_sla:
            evidence.append(f"P95 response time ({p95_latency} ms) violated SLA target ({p95_sla} ms).")
            # Identify slow endpoints
            slow_endpoints = [
                ep for ep in locust_endpoints if ep.get("p95_ms", 0) > p95_sla
            ]
            if slow_endpoints:
                slowest = max(slow_endpoints, key=lambda ep: ep.get("p95_ms", 0))
                evidence.append(
                    f"Endpoint bottleneck identified on '{slowest['method']} {slowest['name']}' with P95 of {slowest['p95_ms']} ms."
                )

        # 4. Synthesize Primary Bottleneck and Classification
        if "CPU" in suspects and p95_latency and p95_latency > p95_sla:
            if cpu_peak and cpu_peak >= 90.0:
                classification = "CONFIRMED_BOTTLENECK"
                primary = "CPU Saturation & Application Concurrency"
            else:
                classification = "CORRELATED_BOTTLENECK"
                primary = "CPU / Application Processing"
        elif "MEMORY" in suspects:
            classification = "CONFIRMED_BOTTLENECK" if mem_peak >= 90.0 else "POSSIBLE_BOTTLENECK"
            primary = "Memory Pressure"
        elif p95_latency and p95_latency > p95_sla:
            classification = "PERFORMANCE_DEGRADATION"
            primary = "Application / Endpoint Latency"
        elif cpu_metrics.get("available") is False:
            classification = "INSUFFICIENT_EVIDENCE"
            primary = "Monitoring Unavailable"
            confidence = "LOW"
            evidence.append("Prometheus metrics unavailable to confirm hardware bottlenecks.")
        else:
            classification = "SYSTEM_HEALTHY"
            primary = "None"
            evidence.append("All measured system and load parameters remained within safe thresholds.")

        return {
            "primary_bottleneck": primary,
            "classification": classification,
            "confidence": confidence,
            "suspected_resources": suspects,
            "evidence": evidence,
        }

    def _analyze_failures(
        self,
        locust_data: Dict[str, Any],
        watchdog_data: Dict[str, Any],
        sla_report: Dict[str, Any],
        cpu_metrics: Dict[str, Any],
        memory_metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Synthesizes multi-factor failure analysis:
        - Crash Watchdog evidence
        - HTTP/Locust errors
        - SLA violations
        - Out-of-memory or timeout patterns
        """
        failure_types: List[str] = []
        evidence: List[str] = []
        severity = "NONE"

        # 1. Watchdog Crashes
        if watchdog_data.get("crash_detected"):
            severity = "FATAL"
            failure_types.append("SERVER_CRASH")
            for c in watchdog_data.get("crashes", []):
                evidence.append(f"Watchdog recorded crash event: {c.get('reason')}")
                if "Exited (137)" in c.get("docker_ps", "") or "Killed" in c.get("server_log_tail", ""):
                    failure_types.append("OUT_OF_MEMORY_KILL")
                    evidence.append("Docker container exited with status 137 (OOM Killed).")

        # 2. Locust HTTP / Connection Failures
        locust_summary = locust_data.get("summary", {})
        failed_reqs = locust_summary.get("failed_requests", 0)
        err_rate = locust_summary.get("error_rate_pct", 0.0)

        if failed_reqs > 0:
            if severity != "FATAL":
                severity = "HIGH"
            failure_types.append("HTTP_REQUEST_FAILURES")
            evidence.append(f"Locust recorded {failed_reqs} failed requests ({err_rate}% error rate).")
            for f in locust_data.get("failures", []):
                evidence.append(f"Failure on {f.get('method')} {f.get('name')}: {f.get('error')} ({f.get('occurrences')} occurrences)")

        # 3. SLA Breaches
        if sla_report.get("overall_status") == "FAIL":
            if severity == "NONE":
                severity = "MODERATE"
            failure_types.append("SLA_NON_COMPLIANCE")
            for v in sla_report.get("violations", []):
                evidence.append(f"SLA Target Violated: {v}")

        if not failure_types:
            failure_type_str = "NO_FAILURES"
            evidence.append("No system crashes, HTTP errors, or SLA violations detected.")
        else:
            failure_type_str = ", ".join(set(failure_types))

        return {
            "failure_type": failure_type_str,
            "severity": severity,
            "failure_count": len(failure_types) if failure_types else 0,
            "evidence": evidence,
        }

    def _generate_conclusion(
        self,
        sla_report: Dict[str, Any],
        bottleneck_analysis: Dict[str, Any],
        failure_analysis: Dict[str, Any],
        watchdog_data: Dict[str, Any],
        locust_summary: Dict[str, Any],
    ) -> str:
        """Generates an executive conclusion narrative based on verified facts."""
        overall_sla = sla_report.get("overall_status", "UNKNOWN")
        passed = sla_report.get("passed_count", 0)
        total = sla_report.get("total_checks", 4)
        crashes = watchdog_data.get("crash_count", 0)
        primary_bn = bottleneck_analysis.get("primary_bottleneck", "None")
        confidence = bottleneck_analysis.get("confidence", "HIGH")
        total_reqs = locust_summary.get("total_requests", 0)

        narrative = [
            f"The experiment executed {total_reqs} requests with overall SLA status '{overall_sla}' ({passed}/{total} checks satisfied)."
        ]

        if crashes > 0:
            narrative.append(f"CRITICAL: Watchdog detected {crashes} server crash event(s).")
        else:
            narrative.append("No container crashes or service interruptions were detected by the watchdog.")

        if overall_sla == "FAIL":
            if confidence == "LOW_SAMPLE_SIZE":
                narrative.append(f"Primary observed degradation candidate identified as '{primary_bn}' (tentative due to low request volume).")
            else:
                narrative.append(f"Primary bottleneck assessed as '{primary_bn}' (Confidence: {confidence}).")
        else:
            narrative.append("The system operated within all performance, reliability, and resource boundaries.")

        return " ".join(narrative)

