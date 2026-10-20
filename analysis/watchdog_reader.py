import os
import re
import glob
import datetime
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class WatchdogReader:
    """
    Reads and parses crash snapshot files written by monitor/crash_watch.py
    Snapshot path format: logs/crash_<YYYYMMDD_HHMMSS>.txt
    Content format:
        === Crash snapshot — <ISO timestamp> ===
        Reason: <failure reason>

        --- docker compose ps ---
        <docker compose ps output>

        --- last 200 lines of <server_log> ---
        <server log tail>
    """

    def __init__(self, logs_dir: str = "logs"):
        self.logs_dir = logs_dir

    def get_crash_files(self) -> List[str]:
        """Finds all crash snapshot files in logs_dir sorted by creation time."""
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
                "timestamp": None,
                "iso_time": None,
                "reason": f"Read error: {e}",
                "docker_ps": "",
                "server_log_tail": "",
            }

        # 1. Extract ISO timestamp from header
        iso_match = re.search(r"===\s*Crash snapshot\s*—\s*([^\s=]+)\s*===", content)
        iso_time_str = iso_match.group(1).strip() if iso_match else None
        
        timestamp_epoch: Optional[float] = None
        if iso_time_str:
            try:
                dt = datetime.datetime.fromisoformat(iso_time_str)
                timestamp_epoch = dt.timestamp()
            except Exception:
                pass

        # If ISO parsing failed, parse from filename: crash_YYYYMMDD_HHMMSS.txt
        if timestamp_epoch is None:
            fn_match = re.search(r"crash_(\d{8}_\d{6})\.txt", os.path.basename(file_path))
            if fn_match:
                try:
                    dt = datetime.datetime.strptime(fn_match.group(1), "%Y%m%d_%H%M%S")
                    timestamp_epoch = dt.timestamp()
                    if not iso_time_str:
                        iso_time_str = dt.isoformat()
                except Exception:
                    pass

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
            "iso_time": iso_time_str,
            "reason": reason,
            "docker_ps": docker_ps,
            "server_log_tail": server_log_tail,
        }

    def read_all(
        self, start_time: Optional[float] = None, end_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Reads all crash snapshots, optionally filtered by experiment time window [start_time, end_time].
        """
        crash_files = self.get_crash_files()
        crashes = []

        for cf in crash_files:
            parsed = self.parse_crash_file(cf)
            ts = parsed.get("timestamp")
            if ts is not None:
                if start_time is not None and ts < start_time:
                    continue
                if end_time is not None and ts > end_time:
                    continue
            crashes.append(parsed)

        return {
            "crash_detected": len(crashes) > 0,
            "crash_count": len(crashes),
            "crashes": crashes,
            "searched_directory": self.logs_dir,
            "total_files_found": len(crash_files),
        }

