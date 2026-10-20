import os
import csv
import glob
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class LocustResultParser:
    """
    Parses Locust output CSV files:
    - {prefix}_stats.csv: Aggregate and per-endpoint summary statistics.
    - {prefix}_stats_history.csv: Time-series request rate, failure rate, and response times.
    - {prefix}_failures.csv: Specific failure occurrences and error messages.
    """

    def __init__(self, target_path: str):
        """
        :param target_path: Can be a CSV file path, a base prefix (e.g. 'results_normal_day'),
                            or a directory containing Locust CSV files.
        """
        self.target_path = target_path
        self.stats_file = None
        self.history_file = None
        self.failures_file = None
        self._discover_files()

    def _discover_files(self):
        """Discovers the relevant Locust CSV files based on target_path."""
        if os.path.isdir(self.target_path):
            stats_matches = glob.glob(os.path.join(self.target_path, "*_stats.csv"))
            if stats_matches:
                self.stats_file = stats_matches[0]
                base_prefix = self.stats_file[:-10]
                self.history_file = f"{base_prefix}_stats_history.csv" if os.path.exists(f"{base_prefix}_stats_history.csv") else None
                self.failures_file = f"{base_prefix}_failures.csv" if os.path.exists(f"{base_prefix}_failures.csv") else None
        elif self.target_path.endswith("_stats.csv"):
            self.stats_file = self.target_path
            base_prefix = self.target_path[:-10]
            self.history_file = f"{base_prefix}_stats_history.csv" if os.path.exists(f"{base_prefix}_stats_history.csv") else None
            self.failures_file = f"{base_prefix}_failures.csv" if os.path.exists(f"{base_prefix}_failures.csv") else None
        else:
            possible_stats = f"{self.target_path}_stats.csv"
            if os.path.exists(possible_stats):
                self.stats_file = possible_stats
                self.history_file = f"{self.target_path}_stats_history.csv" if os.path.exists(f"{self.target_path}_stats_history.csv") else None
                self.failures_file = f"{self.target_path}_failures.csv" if os.path.exists(f"{self.target_path}_failures.csv") else None
            elif os.path.exists(self.target_path):
                self.stats_file = self.target_path

        if not self.stats_file or not os.path.exists(self.stats_file):
            logger.warning(f"Locust stats file not found for target path: {self.target_path}")

    @staticmethod
    def _safe_float(val: Any, default: float = 0.0) -> float:
        if val is None or val == "" or val == "N/A":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_int(val: Any, default: int = 0) -> int:
        if val is None or val == "" or val == "N/A":
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    def parse(self) -> Dict[str, Any]:
        """
        Parses the discovered Locust CSV files and returns aggregated and endpoint metrics.
        """
        if not self.stats_file or not os.path.exists(self.stats_file):
            raise FileNotFoundError(f"Locust stats CSV file not found: {self.stats_file}")

        endpoints: List[Dict[str, Any]] = []
        aggregated_data: Optional[Dict[str, Any]] = None

        with open(self.stats_file, mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("Name", "").strip()
                method = row.get("Type", "").strip()
                req_count = self._safe_int(row.get("Request Count", 0))
                fail_count = self._safe_int(row.get("Failure Count", 0))
                avg_resp_time = self._safe_float(row.get("Average Response Time", 0.0))
                min_resp_time = self._safe_float(row.get("Min Response Time", 0.0))
                max_resp_time = self._safe_float(row.get("Max Response Time", 0.0))
                median_resp_time = self._safe_float(row.get("Median Response Time", 0.0))
                rps = self._safe_float(row.get("Requests/s", 0.0))
                failures_per_s = self._safe_float(row.get("Failures/s", 0.0))
                
                p50 = self._safe_float(row.get("50%", 0.0))
                p90 = self._safe_float(row.get("90%", 0.0))
                p95 = self._safe_float(row.get("95%", 0.0))
                p99 = self._safe_float(row.get("99%", 0.0))
                p99_9 = self._safe_float(row.get("99.9%", 0.0))

                success_count = max(0, req_count - fail_count)
                error_rate_pct = round((fail_count / req_count * 100.0), 2) if req_count > 0 else 0.0

                endpoint_obj = {
                    "method": method,
                    "name": name,
                    "request_count": req_count,
                    "success_count": success_count,
                    "failure_count": fail_count,
                    "error_rate_pct": error_rate_pct,
                    "requests_per_s": round(rps, 2),
                    "failures_per_s": round(failures_per_s, 2),
                    "avg_response_time_ms": round(avg_resp_time, 2),
                    "min_response_time_ms": round(min_resp_time, 2),
                    "max_response_time_ms": round(max_resp_time, 2),
                    "median_response_time_ms": round(median_resp_time, 2),
                    "p50_ms": round(p50, 2),
                    "p90_ms": round(p90, 2),
                    "p95_ms": round(p95, 2),
                    "p99_ms": round(p99, 2),
                    "p99_9_ms": round(p99_9, 2),
                }

                if name.lower() == "aggregated":
                    aggregated_data = endpoint_obj
                else:
                    endpoints.append(endpoint_obj)

        if not aggregated_data:
            total_reqs = sum(e["request_count"] for e in endpoints)
            total_fails = sum(e["failure_count"] for e in endpoints)
            total_success = total_reqs - total_fails
            overall_err = round((total_fails / total_reqs * 100.0), 2) if total_reqs > 0 else 0.0
            overall_rps = sum(e["requests_per_s"] for e in endpoints)
            avg_resp = (sum(e["avg_response_time_ms"] * e["request_count"] for e in endpoints) / total_reqs) if total_reqs > 0 else 0.0
            min_resp = min((e["min_response_time_ms"] for e in endpoints), default=0.0)
            max_resp = max((e["max_response_time_ms"] for e in endpoints), default=0.0)

            aggregated_data = {
                "method": "",
                "name": "Aggregated",
                "request_count": total_reqs,
                "success_count": total_success,
                "failure_count": total_fails,
                "error_rate_pct": overall_err,
                "requests_per_s": round(overall_rps, 2),
                "failures_per_s": 0.0,
                "avg_response_time_ms": round(avg_resp, 2),
                "min_response_time_ms": round(min_resp, 2),
                "max_response_time_ms": round(max_resp, 2),
                "median_response_time_ms": 0.0,
                "p50_ms": 0.0,
                "p90_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "p99_9_ms": 0.0,
            }

        failures: List[Dict[str, Any]] = []
        if self.failures_file and os.path.exists(self.failures_file):
            with open(self.failures_file, mode="r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    failures.append({
                        "method": row.get("Method", "").strip(),
                        "name": row.get("Name", "").strip(),
                        "error": row.get("Error", "").strip(),
                        "occurrences": self._safe_int(row.get("Occurrences", 0))
                    })

        history_series: List[Dict[str, Any]] = []
        if self.history_file and os.path.exists(self.history_file):
            with open(self.history_file, mode="r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Name", "").strip().lower() == "aggregated":
                        ts = self._safe_float(row.get("Timestamp", 0))
                        users = self._safe_int(row.get("User Count", 0))
                        rps = self._safe_float(row.get("Requests/s", 0.0))
                        fails_s = self._safe_float(row.get("Failures/s", 0.0))
                        p95_val = self._safe_float(row.get("95%", 0.0))
                        history_series.append({
                            "timestamp": ts,
                            "user_count": users,
                            "requests_per_s": rps,
                            "failures_per_s": fails_s,
                            "p95_ms": p95_val
                        })

        return {
            "summary": {
                "total_requests": aggregated_data["request_count"],
                "successful_requests": aggregated_data["success_count"],
                "failed_requests": aggregated_data["failure_count"],
                "error_rate_pct": aggregated_data["error_rate_pct"],
                "throughput_rps": aggregated_data["requests_per_s"],
                "avg_response_time_ms": aggregated_data["avg_response_time_ms"],
                "min_response_time_ms": aggregated_data["min_response_time_ms"],
                "max_response_time_ms": aggregated_data["max_response_time_ms"],
                "median_response_time_ms": aggregated_data["median_response_time_ms"],
                "p50_latency_ms": aggregated_data["p50_ms"],
                "p90_latency_ms": aggregated_data["p90_ms"],
                "p95_latency_ms": aggregated_data["p95_ms"],
                "p99_latency_ms": aggregated_data["p99_ms"],
                "p99_9_latency_ms": aggregated_data["p99_9_ms"],
            },
            "endpoints": endpoints,
            "failures": failures,
            "history_series": history_series,
            "discovered_files": {
                "stats_file": self.stats_file,
                "history_file": self.history_file,
                "failures_file": self.failures_file
            }
        }
