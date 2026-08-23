import datetime
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class EventTimelineBuilder:
    """
    Constructs a unified, chronological timeline of events across:
    1. Experiment lifecycle boundaries (T1: EXPERIMENT_START, T2: EXPERIMENT_END)
    2. Locust load lifecycle (LOAD_STARTED, USER_PEAK, RATE_PEAK)
    3. Prometheus system monitoring (CPU_PEAK, MEMORY_PEAK, NETWORK_PEAK_RX, NETWORK_PEAK_TX)
    4. Watchdog events (SERVER_CRASH_DETECTED)
    5. SLA evaluation (SLA_BREACH_DETECTED)

    Strictly differentiates:
    - category: 'OBSERVED' (directly measured metric with timestamp)
    - category: 'INFERRED' (analytical conclusions drawn from observed data)
    """

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def add_event(
        self,
        timestamp: Optional[float],
        event_type: str,
        source: str,
        category: str,
        severity: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Adds an event to the timeline.
        :param timestamp: Unix epoch timestamp in seconds.
        :param event_type: E.g., 'EXPERIMENT_START', 'CPU_PEAK', 'SLA_BREACH', 'SERVER_CRASH'
        :param source: E.g., 'RUNNER', 'LOCUST', 'PROMETHEUS', 'WATCHDOG', 'SLA_ENGINE'
        :param category: 'OBSERVED' or 'INFERRED'
        :param severity: 'INFO', 'WARNING', 'CRITICAL', 'SUCCESS'
        :param description: Human-readable explanation.
        :param details: Optional auxiliary key-value pairs.
        """
        iso_str = (
            datetime.datetime.fromtimestamp(timestamp).isoformat()
            if timestamp is not None
            else None
        )

        self.events.append({
            "timestamp": timestamp,
            "iso_time": iso_str,
            "event_type": event_type,
            "source": source,
            "category": category,
            "severity": severity,
            "description": description,
            "details": details or {},
        })

    def build(
        self,
        experiment_start: float,
        experiment_end: float,
        locust_data: Optional[Dict[str, Any]] = None,
        cpu_metrics: Optional[Dict[str, Any]] = None,
        memory_metrics: Optional[Dict[str, Any]] = None,
        network_metrics: Optional[Dict[str, Any]] = None,
        watchdog_data: Optional[Dict[str, Any]] = None,
        sla_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Populates timeline from all provided subsystems and returns sorted events.
        """
        self.events = []

        # 1. Experiment Boundary T1
        self.add_event(
            timestamp=experiment_start,
            event_type="EXPERIMENT_START",
            source="RUNNER",
            category="OBSERVED",
            severity="INFO",
            description=f"Experiment started at T1 ({experiment_start})",
        )

        # 2. Locust Load Events (from stats_history series)
        if locust_data:
            history = locust_data.get("history_series", [])
            if history:
                first_h = history[0]
                self.add_event(
                    timestamp=first_h["timestamp"],
                    event_type="LOAD_STARTED",
                    source="LOCUST",
                    category="OBSERVED",
                    severity="INFO",
                    description=f"Workload generation began with {first_h['user_count']} users",
                    details={"users": first_h["user_count"]},
                )

                # Peak RPS in history
                peak_rps_entry = max(history, key=lambda h: h["requests_per_s"])
                if peak_rps_entry["requests_per_s"] > 0:
                    self.add_event(
                        timestamp=peak_rps_entry["timestamp"],
                        event_type="LOCUST_PEAK_RPS",
                        source="LOCUST",
                        category="OBSERVED",
                        severity="INFO",
                        description=f"Locust throughput reached peak of {peak_rps_entry['requests_per_s']} req/s",
                        details={"rps": peak_rps_entry["requests_per_s"], "users": peak_rps_entry["user_count"]},
                    )

                # Peak Users
                peak_user_entry = max(history, key=lambda h: h["user_count"])
                if peak_user_entry["user_count"] > 0:
                    self.add_event(
                        timestamp=peak_user_entry["timestamp"],
                        event_type="LOCUST_PEAK_USERS",
                        source="LOCUST",
                        category="OBSERVED",
                        severity="INFO",
                        description=f"Locust concurrency reached peak of {peak_user_entry['user_count']} active users",
                        details={"users": peak_user_entry["user_count"]},
                    )

        # 3. Prometheus System & Network Peaks
        sla_evals = sla_data.get("evaluations", {}) if sla_data else {}

        if cpu_metrics and cpu_metrics.get("peak_timestamp"):
            cpu_sla_status = sla_evals.get("cpu_utilization", {}).get("status", "INFO")
            cpu_sev = "WARNING" if cpu_sla_status == "FAIL" else "INFO"
            self.add_event(
                timestamp=cpu_metrics["peak_timestamp"],
                event_type="PROMETHEUS_CPU_PEAK",
                source="PROMETHEUS",
                category="OBSERVED",
                severity=cpu_sev,
                description=f"CPU utilization peaked at {cpu_metrics['peak']}%",
                details={"peak_cpu_pct": cpu_metrics["peak"], "average_cpu_pct": cpu_metrics.get("average", 0)},
            )

        if memory_metrics and memory_metrics.get("peak_timestamp"):
            mem_sla_status = sla_evals.get("memory_utilization", {}).get("status", "INFO")
            mem_sev = "WARNING" if mem_sla_status == "FAIL" else "INFO"
            self.add_event(
                timestamp=memory_metrics["peak_timestamp"],
                event_type="PROMETHEUS_MEMORY_PEAK",
                source="PROMETHEUS",
                category="OBSERVED",
                severity=mem_sev,
                description=f"Memory utilization peaked at {memory_metrics['peak']}%",
                details={"peak_memory_pct": memory_metrics["peak"], "average_memory_pct": memory_metrics.get("average", 0)},
            )

        if network_metrics:
            if network_metrics.get("peak_rx_timestamp"):
                self.add_event(
                    timestamp=network_metrics["peak_rx_timestamp"],
                    event_type="NETWORK_PEAK_RX",
                    source="PROMETHEUS",
                    category="OBSERVED",
                    severity="INFO",
                    description=f"Network receive rate peaked at {network_metrics['peak_rx_MBps']} MiB/s on {network_metrics.get('device')}",
                    details={"peak_rx_MBps": network_metrics["peak_rx_MBps"]},
                )
            if network_metrics.get("peak_tx_timestamp"):
                self.add_event(
                    timestamp=network_metrics["peak_tx_timestamp"],
                    event_type="NETWORK_PEAK_TX",
                    source="PROMETHEUS",
                    category="OBSERVED",
                    severity="INFO",
                    description=f"Network transmit rate peaked at {network_metrics['peak_tx_MBps']} MiB/s on {network_metrics.get('device')}",
                    details={"peak_tx_MBps": network_metrics["peak_tx_MBps"]},
                )

        # 4. Watchdog Crashes
        if watchdog_data and watchdog_data.get("crashes"):
            for crash in watchdog_data["crashes"]:
                self.add_event(
                    timestamp=crash.get("timestamp"),
                    event_type="SERVER_CRASH_DETECTED",
                    source="WATCHDOG",
                    category="OBSERVED",
                    severity="CRITICAL",
                    description=f"Crash watchdog captured server failure: {crash.get('reason')}",
                    details={
                        "filename": crash.get("filename"),
                        "reason": crash.get("reason"),
                    },
                )

        # 5. SLA Breaches
        if sla_data:
            evals = sla_data.get("evaluations", {})
            for metric_key, ev in evals.items():
                if ev.get("status") == "FAIL":
                    breach_ts = None
                    ts_source = "MEASURED_PEAK"
                    if metric_key == "cpu_utilization" and cpu_metrics:
                        breach_ts = cpu_metrics.get("peak_timestamp")
                    elif metric_key == "memory_utilization" and memory_metrics:
                        breach_ts = memory_metrics.get("peak_timestamp")
                    elif metric_key == "p95_latency" and locust_data:
                        for h in locust_data.get("history_series", []):
                            if h.get("p95_ms", 0) > ev.get("threshold", 0):
                                breach_ts = h["timestamp"]
                                ts_source = "FIRST_HISTORY_BREACH"
                                break
                    if breach_ts is None:
                        breach_ts = experiment_end
                        ts_source = "BOUNDARY_FALLBACK"

                    details_copy = dict(ev)
                    details_copy["timestamp_source"] = ts_source

                    desc_suffix = "" if ts_source != "BOUNDARY_FALLBACK" else " (exact timestamp unavailable; mapped to boundary T2)"
                    self.add_event(
                        timestamp=breach_ts,
                        event_type="SLA_BREACH_DETECTED",
                        source="SLA_ENGINE",
                        category="INFERRED",
                        severity="CRITICAL",
                        description=f"SLA Target Breached: {ev['metric_name']} was {ev['measured_value']} {ev['unit']} (Limit: {ev['threshold']} {ev['unit']}){desc_suffix}",
                        details=details_copy,
                    )

        # 6. Experiment Boundary T2
        self.add_event(
            timestamp=experiment_end,
            event_type="EXPERIMENT_END",
            source="RUNNER",
            category="OBSERVED",
            severity="INFO",
            description=f"Experiment completed at T2 ({experiment_end})",
        )

        # Sort chronologically by timestamp (handling None safely)
        self.events.sort(key=lambda e: (e["timestamp"] is None, e["timestamp"] or 0))
        return self.events

