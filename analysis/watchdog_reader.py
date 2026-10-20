import os
import re
import glob
import datetime
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class WatchdogReader:
    """
    Reads and parses crash snapshot files written by monitor/crash_watch.py.
    Snapshot path format: logs/crash_<YYYYMMDD_HHMMSS>.txt
    Content format:
        === Crash snapshot — <ISO timestamp> ===
        Reason: <failure reason>

        --- docker compose ps ---
        <docker compose ps output>

        --- last 200 lines of <server_log> ---
        <server log tail>

    Timestamp Policy:
    - Timezone-aware ISO strings (+HH:MM, -HH:MM, Z) are normalized to UTC epoch seconds.
    - Naive ISO strings (lacking explicit tz offset) are normalized to UTC via `default_timezone`
      and marked with `timezone_status = "NAIVE_NORMALIZED_UTC"` to record ambiguity.
    - Malformed or missing timestamps retain the crash evidence with `timestamp = None`
      and `timezone_status = "UNPARSABLE"`.
    """

    def __init__(
        self,
        logs_dir: str = "logs",
        default_timezone: Optional[datetime.tzinfo] = datetime.timezone.utc,
    ):
        self.logs_dir = logs_dir
        self.default_timezone = default_timezone or datetime.timezone.utc

    def get_crash_files(self) -> List[str]:
        """Finds all crash snapshot files in logs_dir sorted deterministically by filename."""
        if not os.path.exists(self.logs_dir):
            return []
        pattern = os.path.join(self.logs_dir, "crash_*.txt")
        files = glob.glob(pattern)
        return sorted(files)

    def parse_crash_file(self, file_path: str) -> Dict[str, Any]:
        """Parses an individual crash snapshot file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Crash log file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading crash log {file_path}: {e}")
            return {
                "file_path": file_path,
                "filename": os.path.basename(file_path),
                "timestamp": None,
                "iso_time": None,
                "timezone_status": "READ_ERROR",
                "reason": f"Read error: {e}",
                "docker_ps": "",
                "server_log_tail": "",
            }

        # 1. Extract ISO timestamp from header
        iso_match = re.search(r"===\s*Crash snapshot\s*—\s*([^\s=]+)\s*===", content)
        iso_time_str = iso_match.group(1).strip() if iso_match else None

        timestamp_epoch: Optional[float] = None
        normalized_iso_str: Optional[str] = None
        timezone_status: str = "UNKNOWN"

        if iso_time_str:
            try:
                # Handle standard ISO formats, including Z suffix
                clean_iso = iso_time_str.replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(clean_iso)
                if dt.tzinfo is not None:
                    utc_dt = dt.astimezone(datetime.timezone.utc)
                    timestamp_epoch = utc_dt.timestamp()
                    normalized_iso_str = utc_dt.isoformat()
                    timezone_status = "EXPLICIT_OFFSET"
                else:
                    # Naive datetime
                    aware_dt = dt.replace(tzinfo=self.default_timezone)
                    utc_dt = aware_dt.astimezone(datetime.timezone.utc)
                    timestamp_epoch = utc_dt.timestamp()
                    normalized_iso_str = utc_dt.isoformat()
                    timezone_status = "NAIVE_NORMALIZED_UTC"
            except Exception:
                pass

        # If header ISO parsing failed, attempt extraction from filename: crash_YYYYMMDD_HHMMSS.txt
        if timestamp_epoch is None:
            fn_match = re.search(r"crash_(\d{8}_\d{6})\.txt", os.path.basename(file_path))
            if fn_match:
                try:
                    dt = datetime.datetime.strptime(fn_match.group(1), "%Y%m%d_%H%M%S")
                    aware_dt = dt.replace(tzinfo=self.default_timezone)
                    utc_dt = aware_dt.astimezone(datetime.timezone.utc)
                    timestamp_epoch = utc_dt.timestamp()
                    normalized_iso_str = utc_dt.isoformat()
                    timezone_status = "FILENAME_NORMALIZED_UTC"
                except Exception:
                    pass

        if timestamp_epoch is None:
            timezone_status = "UNPARSABLE"

        # 2. Extract Reason
        reason_match = re.search(r"^Reason:\s*(.+)$", content, re.MULTILINE)
        reason = reason_match.group(1).strip() if reason_match else "Unknown reason"

        # 3. Extract Docker Compose ps section
        docker_ps = ""
        ps_match = re.search(
            r"---\s*docker compose ps\s*---\s*\n(.*?)(?=\n---\s*last \d+ lines|\Z)",
            content,
            re.DOTALL,
        )
        if ps_match:
            docker_ps = ps_match.group(1).strip()

        # 4. Extract Server log tail section
        server_log_tail = ""
        log_match = re.search(
            r"---\s*last \d+ lines of .*?\s*---\s*\n(.*)$", content, re.DOTALL
        )
        if log_match:
            server_log_tail = log_match.group(1).strip()

        return {
            "file_path": file_path,
            "filename": os.path.basename(file_path),
            "timestamp": timestamp_epoch,
            "iso_time": normalized_iso_str or iso_time_str,
            "timezone_status": timezone_status,
            "reason": reason,
            "docker_ps": docker_ps,
            "server_log_tail": server_log_tail,
        }

    def read_all(
        self, start_time: Optional[float] = None, end_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Reads all crash snapshots, filtered by experiment time window [start_time, end_time].
        Crashes with unparsable timestamps are preserved and marked with in_window='AMBIGUOUS'.
        """
        crash_files = self.get_crash_files()
        crashes = []
        discarded_outside_window = 0
        ambiguous_timestamps_count = 0

        for cf in crash_files:
            parsed = self.parse_crash_file(cf)
            ts = parsed.get("timestamp")
            if ts is not None:
                if start_time is not None and ts < start_time:
                    discarded_outside_window += 1
                    continue
                if end_time is not None and ts > end_time:
                    discarded_outside_window += 1
                    continue
                parsed["in_window"] = True
            else:
                parsed["in_window"] = "AMBIGUOUS"
                ambiguous_timestamps_count += 1

            crashes.append(parsed)

        return {
            "crash_detected": len(crashes) > 0,
            "crash_count": len(crashes),
            "crashes": crashes,
            "searched_directory": self.logs_dir,
            "total_files_found": len(crash_files),
            "discarded_outside_window": discarded_outside_window,
            "ambiguous_timestamps_count": ambiguous_timestamps_count,
        }
