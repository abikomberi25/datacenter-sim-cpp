import os
import csv
import glob
import math
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

class AmbiguousRunError(ValueError):
    """Raised when multiple candidate Locust runs exist in a directory without an explicit prefix."""
    pass

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
        self.stats_file: Optional[str] = None
        self.history_file: Optional[str] = None
        self.failures_file: Optional[str] = None
        self.exceptions_file: Optional[str] = None
        self.base_prefix: Optional[str] = None
        self._discover_files()

    def _discover_files(self):
        """Discovers and deterministically validates relevant Locust CSV files."""
        if not self.target_path:
            raise ValueError("Target path for LocustResultParser cannot be empty.")

        norm_path = os.path.normpath(self.target_path)

        if os.path.isdir(norm_path):
            stats_matches = sorted(glob.glob(os.path.join(norm_path, "*_stats.csv")))
            if not stats_matches:
                raise FileNotFoundError(f"No Locust stats CSV files (*_stats.csv) found in directory: '{self.target_path}'")

            # Extract distinct base prefixes
            prefixes = sorted(list(set(f[:-10] for f in stats_matches)))
            if len(prefixes) > 1:
                prefix_names = [os.path.basename(p) for p in prefixes]
                raise AmbiguousRunError(
                    f"Ambiguous Locust runs in directory '{self.target_path}': found multiple runs {prefix_names}. "
                    f"Please specify an explicit run prefix (e.g. '--csv {prefix_names[0]}')."
                )

            base_prefix = prefixes[0]
            self.stats_file = f"{base_prefix}_stats.csv"
            self.base_prefix = base_prefix

        elif norm_path.endswith("_stats.csv"):
            if not os.path.exists(norm_path):
                raise FileNotFoundError(f"Locust stats CSV file not found: '{self.target_path}'")
            self.stats_file = norm_path
            self.base_prefix = norm_path[:-10]

        else:
            # Check if target_path is a prefix with an existing _stats.csv
            possible_stats = f"{norm_path}_stats.csv"
            if os.path.exists(possible_stats):
                self.stats_file = possible_stats
                self.base_prefix = norm_path
            elif os.path.exists(norm_path) and not os.path.isdir(norm_path):
                self.stats_file = norm_path
                self.base_prefix = norm_path[:-10] if norm_path.endswith("_stats.csv") else (norm_path[:-4] if norm_path.endswith(".csv") else norm_path)
            else:
                raise FileNotFoundError(f"Locust stats file not found for target prefix/path: '{self.target_path}'")

        # Discover companion files belonging to the exact same base prefix
        if self.base_prefix:
            history_candidate = f"{self.base_prefix}_stats_history.csv"
            failures_candidate = f"{self.base_prefix}_failures.csv"
            exceptions_candidate = f"{self.base_prefix}_exceptions.csv"

            self.history_file = history_candidate if os.path.exists(history_candidate) else None
            self.failures_file = failures_candidate if os.path.exists(failures_candidate) else None
            self.exceptions_file = exceptions_candidate if os.path.exists(exceptions_candidate) else None

        if not self.stats_file or not os.path.exists(self.stats_file):
            raise FileNotFoundError(f"Locust stats CSV file not found: '{self.stats_file}'")

    def get_history_time_bounds(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Reads min and max timestamp from companion _stats_history.csv file without full parse.
        Returns (min_timestamp, max_timestamp) in epoch seconds or (None, None) if unavailable.
        """
        if not self.history_file or not os.path.exists(self.history_file):
            return None, None

        min_ts: Optional[float] = None
        max_ts: Optional[float] = None

        try:
            with open(self.history_file, mode="r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    raw_ts = row.get("Timestamp")
                    if raw_ts:
                        try:
                            val = float(raw_ts)
                            if math.isfinite(val):
                                if min_ts is None or val < min_ts:
                                    min_ts = val
                                if max_ts is None or val > max_ts:
                                    max_ts = val
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            logger.warning(f"Error reading history time bounds from {self.history_file}: {e}")
            return None, None

        return min_ts, max_ts

    @staticmethod
    def _safe_float(val: Any, default: Optional[float] = 0.0) -> Optional[float]:
        if val is None or val == "" or val == "N/A" or val == "null":
            return default
        try:
            res = float(val)
            return res if math.isfinite(res) else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_int(val: Any, default: int = 0) -> int:
        if val is None or val == "" or val == "N/A" or val == "null":
            return default
        try:
            f = float(val)
            return int(f) if math.isfinite(f) else default
        except (ValueError, TypeError):
            return default

    def parse(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Parses the discovered Locust CSV files and returns aggregated and endpoint metrics.
        Filters history observations to the interval [start_time, end_time] when provided.
        """
        if not self.stats_file or not os.path.exists(self.stats_file):
            raise FileNotFoundError(f"Locust stats CSV file not found: {self.stats_file}")

        if start_time is not None and not math.isfinite(start_time):
            raise ValueError(f"Invalid start_time: {start_time}")
        if end_time is not None and not math.isfinite(end_time):
            raise ValueError(f"Invalid end_time: {end_time}")
        if start_time is not None and end_time is not None and end_time < start_time:
            raise ValueError(f"end_time ({end_time}) must be greater than or equal to start_time ({start_time})")

        endpoints: List[Dict[str, Any]] = []
        aggregated_data: Optional[Dict[str, Any]] = None
        has_stats_rows = False

        with open(self.stats_file, mode="r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                has_stats_rows = True
                name = row.get("Name", "").strip()
                method = row.get("Type", "").strip()
                req_count = self._safe_int(row.get("Request Count", 0))
                fail_count = self._safe_int(row.get("Failure Count", 0))
                avg_resp_time = self._safe_float(row.get("Average Response Time", 0.0)) or 0.0
                min_resp_time = self._safe_float(row.get("Min Response Time", 0.0)) or 0.0
                max_resp_time = self._safe_float(row.get("Max Response Time", 0.0)) or 0.0
                median_resp_time = self._safe_float(row.get("Median Response Time", 0.0)) or 0.0
                rps = self._safe_float(row.get("Requests/s", 0.0)) or 0.0
                failures_per_s = self._safe_float(row.get("Failures/s", 0.0)) or 0.0

                p50 = self._safe_float(row.get("50%", 0.0))
                p90 = self._safe_float(row.get("90%", 0.0))
                p95 = self._safe_float(row.get("95%", 0.0))
                p99 = self._safe_float(row.get("99%", 0.0))
                p99_9 = self._safe_float(row.get("99.9%", 0.0))

                success_count = max(0, req_count - fail_count)
                # Compute error rate with 4 decimal places to prevent premature rounding across SLA thresholds
                error_rate_pct = round((fail_count / req_count * 100.0), 4) if req_count > 0 else 0.0

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
                    "p50_ms": round(p50, 2) if p50 is not None else None,
                    "p90_ms": round(p90, 2) if p90 is not None else None,
                    "p95_ms": round(p95, 2) if p95 is not None else None,
                    "p99_ms": round(p99, 2) if p99 is not None else None,
                    "p99_9_ms": round(p99_9, 2) if p99_9 is not None else None,
                }

                if name.lower() == "aggregated":
                    aggregated_data = endpoint_obj
                else:
                    endpoints.append(endpoint_obj)

        is_empty_dataset = not has_stats_rows or (aggregated_data is None and len(endpoints) == 0) or (aggregated_data is not None and aggregated_data.get("request_count", 0) == 0)

        if not aggregated_data:
            total_reqs = sum(e["request_count"] for e in endpoints)
            total_fails = sum(e["failure_count"] for e in endpoints)
            total_success = total_reqs - total_fails
            overall_err = round((total_fails / total_reqs * 100.0), 4) if total_reqs > 0 else None
            overall_rps = sum(e["requests_per_s"] for e in endpoints)
            avg_resp = (sum(e["avg_response_time_ms"] * e["request_count"] for e in endpoints) / total_reqs) if total_reqs > 0 else None
            min_resp = min((e["min_response_time_ms"] for e in endpoints), default=None)
            max_resp = max((e["max_response_time_ms"] for e in endpoints), default=None)

            # For empty datasets with 0 requests, percentiles are None rather than 0.0
            aggregated_data = {
                "method": "",
                "name": "Aggregated",
                "request_count": total_reqs,
                "success_count": total_success,
                "failure_count": total_fails,
                "error_rate_pct": overall_err,
                "requests_per_s": round(overall_rps, 2),
                "failures_per_s": 0.0,
                "avg_response_time_ms": round(avg_resp, 2) if avg_resp is not None else None,
                "min_response_time_ms": round(min_resp, 2) if min_resp is not None else None,
                "max_response_time_ms": round(max_resp, 2) if max_resp is not None else None,
                "median_response_time_ms": None if is_empty_dataset else 0.0,
                "p50_ms": None,
                "p90_ms": None,
                "p95_ms": None,
                "p99_ms": None,
                "p99_9_ms": None,
            }
        elif aggregated_data.get("request_count", 0) == 0:
            is_empty_dataset = True
            aggregated_data["error_rate_pct"] = None
            aggregated_data["avg_response_time_ms"] = None
            aggregated_data["min_response_time_ms"] = None
            aggregated_data["max_response_time_ms"] = None
            aggregated_data["median_response_time_ms"] = None
            aggregated_data["p50_ms"] = None
            aggregated_data["p90_ms"] = None
            aggregated_data["p95_ms"] = None
            aggregated_data["p99_ms"] = None
            aggregated_data["p99_9_ms"] = None

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

        # History parsing and interval filtering
        history_series: List[Dict[str, Any]] = []
        discarded_before = 0
        discarded_after = 0
        discarded_invalid = 0
        total_history_rows = 0

        if self.history_file and os.path.exists(self.history_file):
            with open(self.history_file, mode="r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Name", "").strip().lower() == "aggregated":
                        total_history_rows += 1
                        raw_ts = row.get("Timestamp")
                        try:
                            ts = float(raw_ts)
                            if not math.isfinite(ts):
                                discarded_invalid += 1
                                continue
                        except (ValueError, TypeError):
                            discarded_invalid += 1
                            continue

                        # Boundary filtering [start_time, end_time]
                        if start_time is not None and ts < start_time:
                            discarded_before += 1
                            continue
                        if end_time is not None and ts > end_time:
                            discarded_after += 1
                            continue

                        users = self._safe_int(row.get("User Count", 0))
                        rps = self._safe_float(row.get("Requests/s", 0.0)) or 0.0
                        fails_s = self._safe_float(row.get("Failures/s", 0.0)) or 0.0
                        p95_val = self._safe_float(row.get("95%", 0.0))

                        history_series.append({
                            "timestamp": ts,
                            "user_count": users,
                            "requests_per_s": round(rps, 2),
                            "failures_per_s": round(fails_s, 2),
                            "p95_ms": round(p95_val, 2) if p95_val is not None else 0.0,
                        })

        # Deterministic chronological sort of retained history samples
        history_series.sort(key=lambda h: h["timestamp"])

        min_history_ts = history_series[0]["timestamp"] if history_series else None
        max_history_ts = history_series[-1]["timestamp"] if history_series else None

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
                "is_empty": is_empty_dataset,
            },
            "endpoints": endpoints,
            "failures": failures,
            "history_series": history_series,
            "discovered_files": {
                "base_prefix": self.base_prefix,
                "stats_file": self.stats_file,
                "history_file": self.history_file,
                "failures_file": self.failures_file,
                "exceptions_file": self.exceptions_file,
                "companion_history_found": self.history_file is not None,
                "companion_failures_found": self.failures_file is not None,
            },
            "history_provenance": {
                "total_samples_read": total_history_rows,
                "samples_retained": len(history_series),
                "samples_discarded_before": discarded_before,
                "samples_discarded_after": discarded_after,
                "samples_discarded_invalid": discarded_invalid,
                "filter_start_time": start_time,
                "filter_end_time": end_time,
                "min_timestamp": min_history_ts,
                "max_timestamp": max_history_ts,
            }
        }
