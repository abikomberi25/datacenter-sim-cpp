import logging
import math
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SystemMonitor:
    """
    Monitors CPU and memory utilization using Prometheus node-exporter metrics.
    Preserves short-lived spikes using aligned rate windows and defensively handles
    multi-core aggregations and non-finite metric values.
    """

    def __init__(
        self,
        prom_client,
        mode: str = "bridge",
        sampling_interval_seconds: int = 5,
        rate_window_seconds: int = 15,
    ):
        """
        :param prom_client: PrometheusClient instance.
        :param mode: Deployment mode ('bridge' or 'host').
        :param sampling_interval_seconds: Resolution step for range queries.
        :param rate_window_seconds: Duration window for rate() calculations.
                                    Default 15s balances responsiveness to brief spikes
                                    with sufficient scrape sample density.
        """
        self.prom = prom_client
        self.mode = mode.lower()
        self.sampling_interval_seconds = sampling_interval_seconds
        self.rate_window_seconds = rate_window_seconds

    def get_cpu_utilization(
        self,
        start_time: Optional[float],
        end_time: Optional[float],
        step: Optional[str] = None,
        rate_window: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates aggregate CPU utilization across all cores.
        Handles multi-core node-exporter metrics and filters non-finite values.
        """
        step_str = f"{self.sampling_interval_seconds}s" if step is None else step
        window = f"{self.rate_window_seconds}s" if rate_window is None else rate_window
        query = f'100 - (avg(rate(node_cpu_seconds_total{{mode="idle"}}[{window}])) * 100)'

        try:
            results = self.prom.query_range(query, start_time, end_time, step_str)
        except Exception as e:
            logger.warning(f"Prometheus CPU query failed: {e}")
            return {
                "average": None,
                "peak": None,
                "peak_timestamp": None,
                "series": [],
                "available": False,
                "mode": self.mode,
            }

        series = []
        if results:
            for item in results:
                for ts, val in item.get("values", []):
                    try:
                        v = float(val)
                        if math.isfinite(v):
                            series.append({"timestamp": float(ts), "value": v})
                    except (ValueError, TypeError):
                        pass

        # Deduplicate and sort if multiple series returned
        if series:
            by_ts = {}
            for s in series:
                by_ts.setdefault(s["timestamp"], []).append(s["value"])
            series = [
                {"timestamp": ts, "value": sum(vals) / len(vals)}
                for ts, vals in sorted(by_ts.items())
            ]

        if not series:
            return {
                "average": None,
                "peak": None,
                "peak_timestamp": None,
                "series": [],
                "available": False,
                "mode": self.mode,
            }

        vals = [s["value"] for s in series]
        avg_val = sum(vals) / len(vals)
        peak_entry = max(series, key=lambda s: s["value"])
        return {
            "average": round(avg_val, 2),
            "peak": round(peak_entry["value"], 2),
            "peak_timestamp": peak_entry["timestamp"],
            "series": series,
            "available": True,
            "mode": self.mode,
        }

    def get_memory_utilization(
        self,
        start_time: Optional[float],
        end_time: Optional[float],
        step: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates memory utilization percentage defensively filtering NaN/empty results.
        """
        step_str = f"{self.sampling_interval_seconds}s" if step is None else step
        query = '100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))'

        try:
            results = self.prom.query_range(query, start_time, end_time, step_str)
        except Exception as e:
            logger.warning(f"Prometheus Memory query failed: {e}")
            return {
                "average": None,
                "peak": None,
                "peak_timestamp": None,
                "series": [],
                "available": False,
                "mode": self.mode,
            }

        series = []
        if results:
            for item in results:
                for ts, val in item.get("values", []):
                    try:
                        v = float(val)
                        if math.isfinite(v):
                            series.append({"timestamp": float(ts), "value": v})
                    except (ValueError, TypeError):
                        pass

        if series:
            by_ts = {}
            for s in series:
                by_ts.setdefault(s["timestamp"], []).append(s["value"])
            series = [
                {"timestamp": ts, "value": sum(vals) / len(vals)}
                for ts, vals in sorted(by_ts.items())
            ]

        if not series:
            return {
                "average": None,
                "peak": None,
                "peak_timestamp": None,
                "series": [],
                "available": False,
                "mode": self.mode,
            }

        vals = [s["value"] for s in series]
        avg_val = sum(vals) / len(vals)
        peak_entry = max(series, key=lambda s: s["value"])
        return {
            "average": round(avg_val, 2),
            "peak": round(peak_entry["value"], 2),
            "peak_timestamp": peak_entry["timestamp"],
            "series": series,
            "available": True,
            "mode": self.mode,
        }
