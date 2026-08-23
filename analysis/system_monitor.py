import logging

logger = logging.getLogger(__name__)

class SystemMonitor:
    def __init__(self, prom_client, mode="bridge", sampling_interval_seconds=5):
        self.prom = prom_client
        self.mode = mode.lower()
        self.sampling_interval_seconds = sampling_interval_seconds

    def get_cpu_utilization(self, start_time, end_time, step=None):
        step_str = f"{self.sampling_interval_seconds}s" if step is None else step
        query = '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)'
        results = self.prom.query_range(query, start_time, end_time, step_str)
        series = []
        if results and "values" in results[0]:
            for ts, val in results[0]["values"]:
                try:
                    series.append({"timestamp": float(ts), "value": float(val)})
                except ValueError:
                    pass
        if not series:
            return {"average": None, "peak": None, "peak_timestamp": None, "series": [], "available": False, "mode": self.mode}

        vals = [s["value"] for s in series]
        avg_val = sum(vals) / len(vals)
        peak_entry = max(series, key=lambda s: s["value"])
        return {
            "average": round(avg_val, 2),
            "peak": round(peak_entry["value"], 2),
            "peak_timestamp": peak_entry["timestamp"],
            "series": series,
            "available": True,
            "mode": self.mode
        }

    def get_memory_utilization(self, start_time, end_time, step=None):
        step_str = f"{self.sampling_interval_seconds}s" if step is None else step
        query = '100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))'
        results = self.prom.query_range(query, start_time, end_time, step_str)
        series = []
        if results and "values" in results[0]:
            for ts, val in results[0]["values"]:
                try:
                    series.append({"timestamp": float(ts), "value": float(val)})
                except ValueError:
                    pass
        if not series:
            return {"average": None, "peak": None, "peak_timestamp": None, "series": [], "available": False, "mode": self.mode}

        vals = [s["value"] for s in series]
        avg_val = sum(vals) / len(vals)
        peak_entry = max(series, key=lambda s: s["value"])
        return {
            "average": round(avg_val, 2),
            "peak": round(peak_entry["value"], 2),
            "peak_timestamp": peak_entry["timestamp"],
            "series": series,
            "available": True,
            "mode": self.mode
        }
