import logging

logger = logging.getLogger(__name__)

EXCLUDED_PREFIXES = ("lo", "docker", "br-", "veth", "virbr")
PHYSICAL_PREFIXES = ("eth", "en", "enp", "ens", "wlan", "wlp")

class NetworkMonitor:
    """
    Monitors network throughput and cumulative volume using Prometheus node-exporter metrics.
    All throughput rates and cumulative volumes use standard binary IEC units:
    - Rates: Mebibytes per second (MiB/s = 1,048,576 bytes/sec).
    - Cumulative volume: Mebibytes (MiB = 1,048,576 bytes).
    Legacy dictionary keys (*_mb, *_MBps) are preserved as exact binary aliases for backwards compatibility.
    """

    def __init__(self, prom_client, mode="bridge", fallback=True, rate_window_seconds=15, sampling_interval_seconds=5):
        self.prom = prom_client
        self.mode = mode.lower()
        self.fallback = fallback
        self.rate_window_seconds = rate_window_seconds
        self.sampling_interval_seconds = sampling_interval_seconds

    def discover_interface(self):
        devices = self.prom.get_label_values("device", match_metric="node_network_receive_bytes_total")
        filtered = [d for d in devices if not any(d.startswith(p) for p in EXCLUDED_PREFIXES)] if devices else []

        selected = None
        is_physical_name = False
        for d in filtered:
            if any(d.startswith(p) for p in PHYSICAL_PREFIXES):
                selected = d
                is_physical_name = True
                break

        warning_msg = None
        if not selected:
            if filtered:
                selected = filtered[0]
            elif self.fallback and devices:
                selected = devices[0]
                warning_msg = "Physical interface unavailable; container/bridge interface used as fallback."

        if not selected:
            raise RuntimeError("No network interfaces found in Prometheus node-exporter metrics.")

        if self.mode == "host" and is_physical_name:
            classification = "HOST_PHYSICAL"
        else:
            classification = "DOCKER_CONTAINER"
            if not warning_msg:
                warning_msg = "Node Exporter is running in bridge mode; metrics represent Docker container/bridge networking."

        return selected, classification, warning_msg

    def get_network_metrics(self, start_time, end_time, step=None):
        try:
            device, classification, warning_msg = self.discover_interface()
        except Exception as e:
            logger.warning(f"Could not discover network interface (Prometheus down?): {e}")
            return {
                "device": "unknown",
                "classification": "UNAVAILABLE",
                "mode": self.mode,
                "warning": str(e),
                "unit_total": "MiB",
                "unit_rate": "MiB/s",
                "total_rx_mib": None,
                "total_tx_mib": None,
                "peak_rx_mib_s": None,
                "peak_rx_timestamp": None,
                "peak_tx_mib_s": None,
                "peak_tx_timestamp": None,
                # Backward-compatible aliases
                "total_rx_mb": None,
                "total_tx_mb": None,
                "peak_rx_MBps": None,
                "peak_tx_MBps": None,
                "rx_series": [],
                "tx_series": [],
                "available": False,
            }

        start_str = f"@{int(start_time)}" if start_time else ""
        end_str = f"@{int(end_time)}" if end_time else ""

        rx_start_res = self.prom.query(f'node_network_receive_bytes_total{{device="{device}"}} {start_str}'.strip())
        tx_start_res = self.prom.query(f'node_network_transmit_bytes_total{{device="{device}"}} {start_str}'.strip())

        rx_start_val = float(rx_start_res[0]["value"][1]) if rx_start_res and "value" in rx_start_res[0] else None
        tx_start_val = float(tx_start_res[0]["value"][1]) if tx_start_res and "value" in tx_start_res[0] else None

        window = f"{self.rate_window_seconds}s"
        # 1 MiB = 1,048,576 bytes
        rx_rate_query = f'rate(node_network_receive_bytes_total{{device="{device}"}}[{window}]) / 1048576'
        tx_rate_query = f'rate(node_network_transmit_bytes_total{{device="{device}"}}[{window}]) / 1048576'

        step_str = f"{self.sampling_interval_seconds}s" if step is None else step
        rx_results = self.prom.query_range(rx_rate_query, start_time, end_time, step_str)
        tx_results = self.prom.query_range(tx_rate_query, start_time, end_time, step_str)

        rx_series = []
        if rx_results and "values" in rx_results[0]:
            for ts, val in rx_results[0]["values"]:
                rx_series.append({"timestamp": float(ts), "value": float(val)})

        tx_series = []
        if tx_results and "values" in tx_results[0]:
            for ts, val in tx_results[0]["values"]:
                tx_series.append({"timestamp": float(ts), "value": float(val)})

        if not rx_series and not tx_series:
            return {
                "device": device,
                "classification": classification,
                "mode": self.mode,
                "warning": warning_msg,
                "unit_total": "MiB",
                "unit_rate": "MiB/s",
                "total_rx_mib": None,
                "total_tx_mib": None,
                "peak_rx_mib_s": None,
                "peak_rx_timestamp": None,
                "peak_tx_mib_s": None,
                "peak_tx_timestamp": None,
                # Backward-compatible aliases
                "total_rx_mb": None,
                "total_tx_mb": None,
                "peak_rx_MBps": None,
                "peak_tx_MBps": None,
                "rx_series": [],
                "tx_series": [],
                "available": False,
            }

        peak_rx = max(rx_series, key=lambda s: s["value"]) if rx_series else {"value": None, "timestamp": None}
        peak_tx = max(tx_series, key=lambda s: s["value"]) if tx_series else {"value": None, "timestamp": None}

        rx_end_res = self.prom.query(f'node_network_receive_bytes_total{{device="{device}"}} {end_str}'.strip())
        tx_end_res = self.prom.query(f'node_network_transmit_bytes_total{{device="{device}"}} {end_str}'.strip())

        rx_end_val = float(rx_end_res[0]["value"][1]) if rx_end_res and "value" in rx_end_res[0] else None
        tx_end_val = float(tx_end_res[0]["value"][1]) if tx_end_res and "value" in tx_end_res[0] else None

        total_rx_mib = (
            max(0.0, (rx_end_val - rx_start_val) / 1048576.0)
            if rx_start_val is not None and rx_end_val is not None
            else None
        )
        total_tx_mib = (
            max(0.0, (tx_end_val - tx_start_val) / 1048576.0)
            if tx_start_val is not None and tx_end_val is not None
            else None
        )

        tot_rx_val = round(total_rx_mib, 2) if total_rx_mib is not None else None
        tot_tx_val = round(total_tx_mib, 2) if total_tx_mib is not None else None
        pk_rx_val = round(peak_rx["value"], 2) if peak_rx["value"] is not None else None
        pk_tx_val = round(peak_tx["value"], 2) if peak_tx["value"] is not None else None

        return {
            "device": device,
            "classification": classification,
            "mode": self.mode,
            "warning": warning_msg,
            "unit_total": "MiB",
            "unit_rate": "MiB/s",
            "total_rx_mib": tot_rx_val,
            "total_tx_mib": tot_tx_val,
            "peak_rx_mib_s": pk_rx_val,
            "peak_rx_timestamp": peak_rx["timestamp"],
            "peak_tx_mib_s": pk_tx_val,
            "peak_tx_timestamp": peak_tx["timestamp"],
            # Backward-compatible aliases
            "total_rx_mb": tot_rx_val,
            "total_tx_mb": tot_tx_val,
            "peak_rx_MBps": pk_rx_val,
            "peak_tx_MBps": pk_tx_val,
            "rx_series": rx_series,
            "tx_series": tx_series,
            "available": True,
        }
