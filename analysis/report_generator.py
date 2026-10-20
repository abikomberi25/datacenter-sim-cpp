import os
import time
import math
import datetime
import logging
import textwrap
from typing import Dict, Any, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.ticker as ticker

logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    Generates visual charts and comprehensive multi-page PDF reports for Member 6:
    - Page 1: Executive Summary, Metadata, Overall SLA Verdict, Key Metrics, and Conclusion.
    - Page 2: System Metrics Visualizations (CPU, Memory, Network RX/TX over time).
    - Page 3: Locust Performance & Concurrency (RPS, Active Users, P95 Latency over time).
    - Page 4+: Detailed Breakdown (Endpoint Response Times, Failures, Watchdog Logs, and Event Timeline),
              with graceful continuation pagination for overflowing tables.
    """

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    @staticmethod
    def _val_or_na(val: Any, unit: str = "") -> str:
        """Formats a scalar metric value or returns 'N/A' if missing, None, or empty."""
        if val is None or val == "" or val == "N/A":
            return "N/A"
        return f"{val} {unit}".strip()

    @staticmethod
    def _filter_series(series: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Extracts and validates timestamp-value series, dropping non-finite or malformed entries."""
        clean = []
        for s in (series or []):
            if not isinstance(s, dict):
                continue
            ts = s.get("timestamp")
            val = s.get("value")
            if ts is not None and val is not None:
                try:
                    f_ts = float(ts)
                    f_val = float(val)
                    if math.isfinite(f_ts) and math.isfinite(f_val):
                        clean.append({"timestamp": f_ts, "value": f_val})
                except (ValueError, TypeError):
                    continue
        clean.sort(key=lambda x: x["timestamp"])
        return clean

    @staticmethod
    def _filter_history(history: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Extracts and validates Locust history entries, filtering non-finite timestamps and values."""
        clean = []
        for h in (history or []):
            if not isinstance(h, dict):
                continue
            ts = h.get("timestamp")
            if ts is None:
                continue
            try:
                f_ts = float(ts)
                if not math.isfinite(f_ts):
                    continue
                rps = float(h.get("requests_per_s", 0.0))
                rps_clean = rps if math.isfinite(rps) else 0.0

                p95 = h.get("p95_ms")
                p95_clean = None
                if p95 is not None:
                    p95_val = float(p95)
                    if math.isfinite(p95_val):
                        p95_clean = p95_val

                clean.append({
                    "timestamp": f_ts,
                    "requests_per_s": rps_clean,
                    "user_count": int(h.get("user_count", 0)),
                    "p95_ms": p95_clean,
                })
            except (ValueError, TypeError):
                continue
        clean.sort(key=lambda x: x["timestamp"])
        return clean

    def generate_charts(self, analysis_data: Dict[str, Any], prefix: str = "run") -> Dict[str, str]:
        """
        Generates standalone PNG visualization figures.
        """
        charts = {}
        plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

        # 1. System Metrics Chart (CPU & Memory, Network)
        cpu = analysis_data.get("system_metrics", {}).get("cpu", {})
        mem = analysis_data.get("system_metrics", {}).get("memory", {})
        net = analysis_data.get("system_metrics", {}).get("network", {})
        sla = analysis_data.get("sla", {})
        thresholds = sla.get("thresholds", {})
        
        cpu_limit = thresholds.get("cpu_pct")
        mem_limit = thresholds.get("memory_pct")
        p95_limit = thresholds.get("p95_latency_ms")

        cpu_series = self._filter_series(cpu.get("series", []))
        mem_series = self._filter_series(mem.get("series", []))
        rx_series = self._filter_series(net.get("rx_series", []))
        tx_series = self._filter_series(net.get("tx_series", []))

        cpu_peak = cpu.get("peak")
        cpu_label = f"CPU (Peak: {cpu_peak}%)" if cpu_peak is not None else "CPU (Data Unavailable)"
        mem_peak = mem.get("peak")
        mem_label = f"Memory (Peak: {mem_peak}%)" if mem_peak is not None else "Memory (Data Unavailable)"

        fig_sys, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        try:
            fig_sys.suptitle("System Resource Utilization Over Time", fontsize=14, fontweight="bold")

            has_cpu_mem = False
            if cpu_series:
                t_cpu = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in cpu_series]
                v_cpu = [s["value"] for s in cpu_series]
                ax1.plot(t_cpu, v_cpu, label=cpu_label, color="#d9534f", lw=2)
                has_cpu_mem = True
            if mem_series:
                t_mem = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in mem_series]
                v_mem = [s["value"] for s in mem_series]
                ax1.plot(t_mem, v_mem, label=mem_label, color="#0275d8", lw=2)
                has_cpu_mem = True

            ax1.set_ylabel("Utilization (%)")
            ax1.set_ylim(0, 105)
            if cpu_limit is not None and has_cpu_mem:
                ax1.axhline(cpu_limit, color="#d9534f", linestyle="--", alpha=0.7, label=f"CPU SLA Limit ({cpu_limit}%)")
            if mem_limit is not None and has_cpu_mem:
                ax1.axhline(mem_limit, color="#0275d8", linestyle="--", alpha=0.7, label=f"Memory SLA Limit ({mem_limit}%)")

            if has_cpu_mem:
                ax1.legend(loc="upper right", fontsize=9)
            else:
                ax1.text(0.5, 0.5, "No CPU / Memory telemetry recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=ax1.transAxes)
            ax1.grid(True, linestyle=":", alpha=0.6)

            # Network Subplot
            rx_peak = net.get("peak_rx_mib_s", net.get("peak_rx_MBps"))
            rx_label = f"RX Rate (Peak: {rx_peak} MiB/s)" if rx_peak is not None else "RX Rate (N/A)"
            tx_peak = net.get("peak_tx_mib_s", net.get("peak_tx_MBps"))
            tx_label = f"TX Rate (Peak: {tx_peak} MiB/s)" if tx_peak is not None else "TX Rate (N/A)"

            has_net = False
            if rx_series:
                t_rx = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in rx_series]
                v_rx = [s["value"] for s in rx_series]
                ax2.plot(t_rx, v_rx, label=rx_label, color="#5cb85c", lw=1.5)
                has_net = True
            if tx_series:
                t_tx = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in tx_series]
                v_tx = [s["value"] for s in tx_series]
                ax2.plot(t_tx, v_tx, label=tx_label, color="#f0ad4e", lw=1.5)
                has_net = True

            ax2.set_ylabel("Throughput (MiB/s)")
            ax2.set_xlabel("Time")
            if has_net:
                ax2.legend(loc="upper right", fontsize=9)
                ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            else:
                ax2.text(0.5, 0.5, "No network telemetry recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=ax2.transAxes)
            ax2.grid(True, linestyle=":", alpha=0.6)

            plt.tight_layout()
            sys_chart_path = os.path.join(self.output_dir, f"{prefix}_system_metrics.png")
            fig_sys.savefig(sys_chart_path, dpi=150)
            charts["system_chart"] = sys_chart_path
        finally:
            plt.close(fig_sys)

        # 2. Locust Load & Latency Chart
        locust = analysis_data.get("load_metrics", {}).get("locust", {})
        clean_history = self._filter_history(locust.get("history_series", []))

        fig_load, (lax1, lax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
        try:
            fig_load.suptitle("Locust Load Profile & Response Latency", fontsize=14, fontweight="bold")

            if clean_history:
                t_h = [datetime.datetime.fromtimestamp(h["timestamp"]) for h in clean_history]
                rps_h = [h["requests_per_s"] for h in clean_history]
                users_h = [h["user_count"] for h in clean_history]

                lax1.plot(t_h, rps_h, label="Throughput (Req/s)", color="#5bc0de", lw=2)
                lax1_twin = lax1.twinx()
                lax1_twin.plot(t_h, users_h, label="Active Users", color="#6f42c1", linestyle=":", lw=2)
                lax1.set_ylabel("Requests / sec")
                lax1_twin.set_ylabel("Concurrency (Users)")
                lax1.legend(loc="upper left", fontsize=9)
                lax1_twin.legend(loc="upper right", fontsize=9)
                lax1.grid(True, linestyle=":", alpha=0.6)

                history_with_p95 = [h for h in clean_history if h.get("p95_ms") is not None]
                if history_with_p95:
                    t_p95 = [datetime.datetime.fromtimestamp(h["timestamp"]) for h in history_with_p95]
                    v_p95 = [h["p95_ms"] for h in history_with_p95]
                    lax2.plot(t_p95, v_p95, label="P95 Latency (ms)", color="#d9534f", lw=2)
                    if p95_limit is not None:
                        lax2.axhline(p95_limit, color="#d9534f", linestyle="--", alpha=0.7, label=f"P95 SLA Limit ({p95_limit} ms)")
                    lax2.set_ylabel("P95 Latency (ms)")
                    lax2.set_xlabel("Time")
                    lax2.legend(loc="upper right", fontsize=9)
                else:
                    lax2.text(0.5, 0.5, "No latency samples recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=lax2.transAxes)
                    lax2.set_ylabel("P95 Latency (ms)")
                    lax2.set_xlabel("Time")

                lax2.grid(True, linestyle=":", alpha=0.6)
                lax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            else:
                lax1.text(0.5, 0.5, "No workload history recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=lax1.transAxes)
                lax1.set_ylabel("Requests / sec")
                lax1.grid(True, linestyle=":", alpha=0.6)

                lax2.text(0.5, 0.5, "No latency history recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=lax2.transAxes)
                lax2.set_ylabel("P95 Latency (ms)")
                lax2.set_xlabel("Time")
                lax2.grid(True, linestyle=":", alpha=0.6)

            plt.tight_layout()
            load_chart_path = os.path.join(self.output_dir, f"{prefix}_locust_performance.png")
            fig_load.savefig(load_chart_path, dpi=150)
            charts["load_chart"] = load_chart_path
        finally:
            plt.close(fig_load)

        return charts

    def generate_pdf_report(self, analysis_data: Dict[str, Any], filename: Optional[str] = None) -> str:
        """
        Compiles the multi-page PDF report with authoritative layout and resource management:
        - Page 1: Executive Summary, SLA Dashboard, Key Metrics, and Conclusion.
        - Page 2: System Metrics Visualizations (CPU, Memory, Network).
        - Page 3: Locust Performance & Latency Over Time.
        - Page 4+: Endpoint Performance and Event Timeline with overflow pagination.
        """
        exp = analysis_data.get("experiment", {})
        profile = exp.get("profile", "unknown")
        timestamp_str = datetime.datetime.fromtimestamp(exp.get("start_time", time.time())).strftime("%Y%m%d_%H%M%S")
        pdf_filename = filename or f"report_{profile}_{timestamp_str}.pdf"
        pdf_path = os.path.join(self.output_dir, pdf_filename)

        sla = analysis_data.get("sla", {})
        thresholds = sla.get("thresholds", {})
        cpu_limit = thresholds.get("cpu_pct")
        mem_limit = thresholds.get("memory_pct")
        p95_limit = thresholds.get("p95_latency_ms")

        bn = analysis_data.get("bottleneck_analysis", {})
        confidence = bn.get("confidence", "HIGH")
        bn_label_header = "Primary Bottleneck Candidate" if confidence == "LOW_SAMPLE_SIZE" else "Primary Bottleneck"

        with PdfPages(pdf_path) as pdf:
            # =========================================================================
            # PAGE 1: Executive Summary & SLA Dashboard (Structured GridSpec Layout)
            # =========================================================================
            fig_p1 = plt.figure(figsize=(8.5, 11))
            try:
                gs_p1 = fig_p1.add_gridspec(
                    nrows=6,
                    ncols=1,
                    height_ratios=[0.08, 0.07, 0.24, 0.22, 0.16, 0.17],
                    top=0.96,
                    bottom=0.04,
                    left=0.08,
                    right=0.92,
                    hspace=0.28,
                )

                # Row 0: Title & Header
                ax_title = fig_p1.add_subplot(gs_p1[0])
                ax_title.axis("off")
                ax_title.text(0.5, 0.70, "DATA CENTER SIMULATION PERFORMANCE REPORT", ha="center", va="center", fontsize=15, fontweight="bold", color="#1a202c")
                ax_title.text(0.5, 0.15, f"Workload Profile: {profile.upper()} | Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ha="center", va="center", fontsize=9.5, color="#718096")

                # Row 1: SLA Verdict Banner Box
                ax_banner = fig_p1.add_subplot(gs_p1[1])
                ax_banner.axis("off")
                overall_status = sla.get("overall_status", "UNKNOWN")
                banner_bg = "#28a745" if overall_status == "PASS" else ("#dc3545" if overall_status == "FAIL" else "#ffc107")
                banner_rect = plt.Rectangle((0, 0), 1, 1, color=banner_bg, transform=ax_banner.transAxes, clip_on=False)
                ax_banner.add_patch(banner_rect)
                ax_banner.text(0.5, 0.5, f"OVERALL SLA VERDICT: {overall_status} ({sla.get('passed_count', 0)}/{sla.get('total_checks', 4)} Checks Satisfied)", ha="center", va="center", fontsize=12, fontweight="bold", color="white")

                # Row 2: Experiment Summary Table
                ax_meta = fig_p1.add_subplot(gs_p1[2])
                ax_meta.axis("off")
                ax_meta.text(0.0, 1.05, "1. Experiment Summary & Identification", fontsize=11, fontweight="bold", color="#2d3748", transform=ax_meta.transAxes)
                
                locust_sum = analysis_data.get("load_metrics", {}).get("locust", {}).get("summary", {})
                meta_data = [
                    ["Profile / Workload", str(profile)],
                    ["Execution Duration", f"{exp.get('duration_seconds', 0)} s"],
                    ["Start Time (T1)", str(exp.get("start_time", "N/A"))],
                    ["End Time (T2)", str(exp.get("end_time", "N/A"))],
                    ["Total Requests Executed", self._val_or_na(locust_sum.get("total_requests"))],
                    [bn_label_header, str(bn.get("primary_bottleneck", "None"))],
                    ["Statistical Confidence", str(confidence)],
                    ["Failure Classification", str(analysis_data.get("failure_analysis", {}).get("failure_type", "NO_FAILURES"))],
                ]
                t_meta = ax_meta.table(cellText=meta_data, colLabels=["Parameter", "Value"], loc="center", bbox=[0, 0, 1, 0.92])
                t_meta.auto_set_font_size(False)
                t_meta.set_fontsize(8.5)
                for (r, c), cell in t_meta.get_celld().items():
                    if r == 0:
                        cell.set_facecolor("#edf2f7")
                        cell.set_text_props(weight="bold", color="#2d3748")

                # Row 3: SLA Scorecard Table
                ax_sla = fig_p1.add_subplot(gs_p1[3])
                ax_sla.axis("off")
                ax_sla.text(0.0, 1.05, "2. SLA Scorecard & Compliance Targets", fontsize=11, fontweight="bold", color="#2d3748", transform=ax_sla.transAxes)

                evals = sla.get("evaluations", {})
                sla_rows = []
                for k, ev in evals.items():
                    m_val = f"{ev.get('measured_value')} {ev.get('unit')}" if ev.get('measured_value') is not None else "N/A"
                    lim = f"{ev.get('threshold')} {ev.get('unit')}"
                    st = ev.get("status", "UNKNOWN")
                    sla_rows.append([ev.get("metric_name", k), m_val, lim, st])

                t_sla = ax_sla.table(cellText=sla_rows, colLabels=["SLA Metric", "Measured Value", "Target Limit", "Result"], loc="center", bbox=[0, 0, 1, 0.90])
                t_sla.auto_set_font_size(False)
                t_sla.set_fontsize(8.5)
                for (r, c), cell in t_sla.get_celld().items():
                    if r == 0:
                        cell.set_facecolor("#edf2f7")
                        cell.set_text_props(weight="bold", color="#2d3748")
                    elif c == 3:
                        res_val = cell.get_text().get_text()
                        cell.set_text_props(weight="bold", color="#28a745" if res_val == "PASS" else ("#dc3545" if res_val == "FAIL" else "#d97706"))

                # Row 4: Executive Conclusion
                ax_conc = fig_p1.add_subplot(gs_p1[4])
                ax_conc.axis("off")
                ax_conc.text(0.0, 1.05, "3. Executive Conclusion & Synthesis", fontsize=11, fontweight="bold", color="#2d3748", transform=ax_conc.transAxes)
                conclusion_txt = analysis_data.get("conclusion", "No conclusion narrative recorded.")
                ax_conc.text(
                    0.0, 0.85, conclusion_txt,
                    fontsize=8.5, wrap=True, va="top", transform=ax_conc.transAxes,
                    bbox=dict(boxstyle="round,pad=0.6", facecolor="#f8fafc", edgecolor="#cbd5e1")
                )

                # Row 5: Diagnostic Observations
                ax_obs = fig_p1.add_subplot(gs_p1[5])
                ax_obs.axis("off")
                ax_obs.text(0.0, 1.05, "4. Diagnostic Observations & Evidence", fontsize=11, fontweight="bold", color="#2d3748", transform=ax_obs.transAxes)
                ev_list = bn.get("evidence", []) + analysis_data.get("failure_analysis", {}).get("evidence", [])
                ev_txt = "\n".join([f"• {e}" for e in ev_list[:5]]) if ev_list else "• All monitored parameters remained within safe boundaries."
                ax_obs.text(0.0, 0.85, ev_txt, fontsize=8.0, wrap=True, va="top", transform=ax_obs.transAxes)

                pdf.savefig(fig_p1)
            finally:
                plt.close(fig_p1)

            # =========================================================================
            # PAGE 2: System & Hardware Resource Dynamics
            # =========================================================================
            fig_p2, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 11))
            try:
                fig_p2.suptitle("System & Hardware Resource Dynamics", fontsize=14, fontweight="bold")

                cpu = analysis_data.get("system_metrics", {}).get("cpu", {})
                mem = analysis_data.get("system_metrics", {}).get("memory", {})
                net = analysis_data.get("system_metrics", {}).get("network", {})
                cpu_series = self._filter_series(cpu.get("series", []))
                mem_series = self._filter_series(mem.get("series", []))
                rx_series = self._filter_series(net.get("rx_series", []))
                tx_series = self._filter_series(net.get("tx_series", []))

                cpu_peak = cpu.get("peak")
                cpu_label = f"CPU (Peak: {cpu_peak}%)" if cpu_peak is not None else "CPU (Data Unavailable)"
                mem_peak = mem.get("peak")
                mem_label = f"Memory (Peak: {mem_peak}%)" if mem_peak is not None else "Memory (Data Unavailable)"

                has_cpu_mem = False
                if cpu_series:
                    t_cpu = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in cpu_series]
                    v_cpu = [s["value"] for s in cpu_series]
                    ax1.plot(t_cpu, v_cpu, label=cpu_label, color="#d9534f", lw=2)
                    has_cpu_mem = True
                if mem_series:
                    t_mem = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in mem_series]
                    v_mem = [s["value"] for s in mem_series]
                    ax1.plot(t_mem, v_mem, label=mem_label, color="#0275d8", lw=2)
                    has_cpu_mem = True

                ax1.set_ylabel("Utilization (%)")
                ax1.set_ylim(0, 105)
                if cpu_limit is not None and has_cpu_mem:
                    ax1.axhline(cpu_limit, color="#d9534f", linestyle="--", alpha=0.7, label=f"CPU SLA ({cpu_limit}%)")
                if mem_limit is not None and has_cpu_mem:
                    ax1.axhline(mem_limit, color="#0275d8", linestyle="--", alpha=0.7, label=f"Memory SLA ({mem_limit}%)")

                if has_cpu_mem:
                    ax1.legend(loc="upper right", fontsize=8)
                else:
                    ax1.text(0.5, 0.5, "No CPU / Memory telemetry recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=ax1.transAxes)
                ax1.grid(True, linestyle=":", alpha=0.6)
                ax1.set_title("CPU and Memory Utilization Time Series", fontsize=11)

                rx_peak = net.get("peak_rx_mib_s", net.get("peak_rx_MBps"))
                rx_label = f"RX Rate (Peak: {rx_peak} MiB/s)" if rx_peak is not None else "RX Rate (N/A)"
                tx_peak = net.get("peak_tx_mib_s", net.get("peak_tx_MBps"))
                tx_label = f"TX Rate (Peak: {tx_peak} MiB/s)" if tx_peak is not None else "TX Rate (N/A)"

                has_net = False
                if rx_series:
                    t_rx = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in rx_series]
                    v_rx = [s["value"] for s in rx_series]
                    ax2.plot(t_rx, v_rx, label=rx_label, color="#5cb85c", lw=1.5)
                    has_net = True
                if tx_series:
                    t_tx = [datetime.datetime.fromtimestamp(s["timestamp"]) for s in tx_series]
                    v_tx = [s["value"] for s in tx_series]
                    ax2.plot(t_tx, v_tx, label=tx_label, color="#f0ad4e", lw=1.5)
                    has_net = True

                ax2.set_ylabel("Throughput (MiB/s)")
                ax2.set_xlabel("Time")
                if has_net:
                    ax2.legend(loc="upper right", fontsize=8)
                    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
                else:
                    ax2.text(0.5, 0.5, "No network telemetry recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=ax2.transAxes)
                ax2.grid(True, linestyle=":", alpha=0.6)
                ax2.set_title(f"Network Traffic ({net.get('device', 'eth0')} - {net.get('classification', 'CONTAINER')})", fontsize=11)

                plt.tight_layout(rect=[0, 0.03, 1, 0.95])
                pdf.savefig(fig_p2)
            finally:
                plt.close(fig_p2)

            # =========================================================================
            # PAGE 3: Locust Workload & Latency Profile
            # =========================================================================
            fig_p3, (lax1, lax2) = plt.subplots(2, 1, figsize=(8.5, 11))
            try:
                fig_p3.suptitle("Locust Workload & Latency Profile", fontsize=14, fontweight="bold")

                locust = analysis_data.get("load_metrics", {}).get("locust", {})
                clean_history = self._filter_history(locust.get("history_series", []))

                if clean_history:
                    t_h = [datetime.datetime.fromtimestamp(h["timestamp"]) for h in clean_history]
                    rps_h = [h["requests_per_s"] for h in clean_history]
                    users_h = [h["user_count"] for h in clean_history]

                    lax1.plot(t_h, rps_h, label="Throughput (Req/s)", color="#5bc0de", lw=2)
                    lax1_twin = lax1.twinx()
                    lax1_twin.plot(t_h, users_h, label="Active Users", color="#6f42c1", linestyle=":", lw=2)
                    lax1.set_ylabel("Requests / sec")
                    lax1_twin.set_ylabel("Active Users")
                    lax1.legend(loc="upper left", fontsize=8)
                    lax1_twin.legend(loc="upper right", fontsize=8)
                    lax1.grid(True, linestyle=":", alpha=0.6)
                    lax1.set_title("Request Rate vs Concurrency Ramp", fontsize=11)

                    history_with_p95 = [h for h in clean_history if h.get("p95_ms") is not None]
                    if history_with_p95:
                        t_p95 = [datetime.datetime.fromtimestamp(h["timestamp"]) for h in history_with_p95]
                        v_p95 = [h["p95_ms"] for h in history_with_p95]
                        lax2.plot(t_p95, v_p95, label="P95 Latency (ms)", color="#d9534f", lw=2)
                        if p95_limit is not None:
                            lax2.axhline(p95_limit, color="#d9534f", linestyle="--", alpha=0.7, label=f"P95 SLA Limit ({p95_limit} ms)")
                        lax2.set_ylabel("P95 Latency (ms)")
                        lax2.set_xlabel("Time")
                        lax2.legend(loc="upper right", fontsize=8)
                    else:
                        lax2.text(0.5, 0.5, "No latency samples recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=lax2.transAxes)
                        lax2.set_ylabel("P95 Latency (ms)")
                        lax2.set_xlabel("Time")

                    lax2.grid(True, linestyle=":", alpha=0.6)
                    lax2.set_title("P95 Response Latency Progression", fontsize=11)
                    lax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
                else:
                    lax1.text(0.5, 0.5, "No workload history recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=lax1.transAxes)
                    lax1.set_ylabel("Requests / sec")
                    lax1.grid(True, linestyle=":", alpha=0.6)
                    lax1.set_title("Request Rate vs Concurrency Ramp", fontsize=11)

                    lax2.text(0.5, 0.5, "No latency history recorded for this time window", ha="center", va="center", fontsize=10, color="#718096", style="italic", transform=lax2.transAxes)
                    lax2.set_ylabel("P95 Latency (ms)")
                    lax2.set_xlabel("Time")
                    lax2.grid(True, linestyle=":", alpha=0.6)
                    lax2.set_title("P95 Response Latency Progression", fontsize=11)

                plt.tight_layout(rect=[0, 0.03, 1, 0.95])
                pdf.savefig(fig_p3)
            finally:
                plt.close(fig_p3)

            # =========================================================================
            # PAGE 4+: Endpoint Performance & Chronological Event Timeline (DEF-013)
            # =========================================================================
            endpoints = locust.get("endpoints", [])
            timeline = analysis_data.get("timeline", [])

            # Check if both tables fit cleanly on a single 4th page (<= 7 endpoints AND <= 12 timeline events)
            if len(endpoints) <= 7 and len(timeline) <= 12:
                fig_p4 = plt.figure(figsize=(8.5, 11))
                try:
                    gs_p4 = fig_p4.add_gridspec(
                        nrows=3,
                        ncols=1,
                        height_ratios=[0.05, 0.38, 0.57],
                        top=0.96,
                        bottom=0.04,
                        left=0.08,
                        right=0.92,
                        hspace=0.25,
                    )

                    # Title
                    ax_p4_title = fig_p4.add_subplot(gs_p4[0])
                    ax_p4_title.axis("off")
                    ax_p4_title.text(0.5, 0.5, "Endpoint Breakdown & Chronological Event Timeline", ha="center", va="center", fontsize=14, fontweight="bold", color="#1a202c")

                    # Section 1: Endpoint Breakdown Table
                    ax_ep = fig_p4.add_subplot(gs_p4[1])
                    ax_ep.axis("off")
                    ax_ep.text(0.0, 1.03, f"1. HTTP Endpoint Performance Breakdown (Total: {len(endpoints)})", fontsize=11, fontweight="bold", color="#2d3748", transform=ax_ep.transAxes)

                    ep_rows = []
                    for ep in endpoints:
                        ep_rows.append([
                            f"{ep.get('method', '')} {ep.get('name', '')}",
                            self._val_or_na(ep.get("request_count")),
                            self._val_or_na(ep.get("failure_count")),
                            self._val_or_na(ep.get("avg_response_time_ms"), "ms"),
                            self._val_or_na(ep.get("p95_ms"), "ms"),
                            self._val_or_na(ep.get("requests_per_s")),
                        ])

                    if ep_rows:
                        t_ep = ax_ep.table(cellText=ep_rows, colLabels=["Endpoint", "Requests", "Failures", "Avg Latency", "P95 Latency", "RPS"], loc="center", bbox=[0, 0, 1, 0.92])
                        t_ep.auto_set_font_size(False)
                        t_ep.set_fontsize(8.0)
                        for (r, c), cell in t_ep.get_celld().items():
                            if r == 0:
                                cell.set_facecolor("#edf2f7")
                                cell.set_text_props(weight="bold", color="#2d3748")
                    else:
                        ax_ep.text(0.5, 0.5, "No HTTP endpoint performance data recorded for this run.", ha="center", va="center", fontsize=9.5, color="#718096", style="italic")

                    # Section 2: Chronological Event Timeline
                    ax_tl = fig_p4.add_subplot(gs_p4[2])
                    ax_tl.axis("off")
                    ax_tl.text(0.0, 1.02, f"2. Chronological Event Timeline (Total: {len(timeline)})", fontsize=11, fontweight="bold", color="#2d3748", transform=ax_tl.transAxes)

                    # Column proportions: Time | Event Source & Type | Category | Severity | Description
                    # Must sum to 1.0 (relative to bbox width)
                    _TL_COL_WIDTHS = [0.09, 0.25, 0.12, 0.10, 0.44]
                    _TL_BBOX = [0, 0, 1, 0.94]

                    tl_rows = []
                    for ev in timeline:
                        ts_label = datetime.datetime.fromtimestamp(ev["timestamp"]).strftime("%H:%M:%S") if ev.get("timestamp") else "N/A"
                        raw_desc = ev.get("description", "")
                        wrapped_desc = textwrap.fill(raw_desc, width=52)
                        wrapped_src = textwrap.fill(
                            f"[{ev.get('source', '')}] {ev.get('event_type', '')}",
                            width=28,
                        )
                        tl_rows.append([
                            ts_label,
                            wrapped_src,
                            ev.get("category", ""),
                            ev.get("severity", ""),
                            wrapped_desc,
                        ])

                    if tl_rows:
                        t_tl = ax_tl.table(
                            cellText=tl_rows,
                            colLabels=["Time", "Event Source & Type", "Category", "Severity", "Description"],
                            loc="center",
                            bbox=_TL_BBOX,
                            colWidths=_TL_COL_WIDTHS,
                        )
                        t_tl.auto_set_font_size(False)
                        t_tl.set_fontsize(7.5)

                        # Compute per-row heights based on max line count across columns
                        n_rows_total = len(tl_rows) + 1  # +1 for header row
                        base_h = _TL_BBOX[3] / n_rows_total
                        row_line_counts = {}
                        for (r, c), cell in t_tl.get_celld().items():
                            if r == 0:
                                continue
                            n_lines = max(1, len(cell.get_text().get_text().splitlines()))
                            row_line_counts[r] = max(row_line_counts.get(r, 1), n_lines)

                        for (r, c), cell in t_tl.get_celld().items():
                            if r == 0:
                                cell.set_facecolor("#edf2f7")
                                cell.set_text_props(weight="bold", color="#2d3748")
                                cell.set_height(base_h)
                            else:
                                n_lines = row_line_counts.get(r, 1)
                                cell.set_height(base_h * max(1, n_lines))
                                cell.set_text_props(va="top")
                                if c == 3:
                                    sev_val = cell.get_text().get_text()
                                    cell.set_text_props(weight="bold", color="#dc3545" if sev_val in ("CRITICAL", "WARNING") else "#2b6cb0", va="top")
                    else:
                        ax_tl.text(0.5, 0.5, "No chronological event timeline records found.", ha="center", va="center", fontsize=9.5, color="#718096", style="italic")

                    pdf.savefig(fig_p4)
                finally:
                    plt.close(fig_p4)
            else:
                # Overflow condition: Paginate Endpoints and Timeline across dedicated pages
                # 1. Paginate Endpoints
                ep_chunk_size = 14
                total_eps = len(endpoints)
                num_ep_pages = max(1, math.ceil(total_eps / ep_chunk_size)) if total_eps > 0 else 1

                for ep_page_idx in range(num_ep_pages):
                    fig_ep = plt.figure(figsize=(8.5, 11))
                    try:
                        ax = fig_ep.add_subplot(1, 1, 1)
                        ax.axis("off")

                        page_num_str = f" (Page {ep_page_idx + 1} of {num_ep_pages})" if num_ep_pages > 1 else ""
                        ax.text(0.5, 0.96, f"HTTP Endpoint Performance Breakdown{page_num_str}", ha="center", va="top", fontsize=14, fontweight="bold", color="#1a202c")

                        start_i = ep_page_idx * ep_chunk_size
                        end_i = min(start_i + ep_chunk_size, total_eps)
                        chunk_eps = endpoints[start_i:end_i]

                        sub_text = f"Showing endpoints {start_i + 1} to {end_i} of {total_eps} total endpoints" if total_eps > 0 else "No endpoint data recorded."
                        ax.text(0.5, 0.92, sub_text, ha="center", va="top", fontsize=9.5, color="#718096")

                        chunk_rows = []
                        for ep in chunk_eps:
                            chunk_rows.append([
                                f"{ep.get('method', '')} {ep.get('name', '')}",
                                self._val_or_na(ep.get("request_count")),
                                self._val_or_na(ep.get("failure_count")),
                                self._val_or_na(ep.get("avg_response_time_ms"), "ms"),
                                self._val_or_na(ep.get("p95_ms"), "ms"),
                                self._val_or_na(ep.get("requests_per_s")),
                            ])

                        if chunk_rows:
                            t_ep = ax.table(
                                cellText=chunk_rows,
                                colLabels=["Endpoint", "Requests", "Failures", "Avg Latency", "P95 Latency", "RPS"],
                                loc="top",
                                bbox=[0.05, 0.15, 0.90, 0.72]
                            )
                            t_ep.auto_set_font_size(False)
                            t_ep.set_fontsize(8.5)
                            for (r, c), cell in t_ep.get_celld().items():
                                if r == 0:
                                    cell.set_facecolor("#edf2f7")
                                    cell.set_text_props(weight="bold", color="#2d3748")
                        else:
                            ax.text(0.5, 0.5, "No HTTP endpoint performance data recorded for this run.", ha="center", va="center", fontsize=10, color="#718096", style="italic")

                        pdf.savefig(fig_ep)
                    finally:
                        plt.close(fig_ep)

                # 2. Paginate Timeline
                tl_chunk_size = 18
                max_tl_pages = 4
                total_events = len(timeline)
                # Sort chronologically by timestamp
                sorted_timeline = sorted(timeline, key=lambda e: (e.get("timestamp") is None, e.get("timestamp") or 0))

                max_displayable_events = tl_chunk_size * max_tl_pages
                display_events = sorted_timeline[:max_displayable_events]
                omitted_events_count = max(0, total_events - len(display_events))

                num_tl_pages = max(1, math.ceil(len(display_events) / tl_chunk_size)) if len(display_events) > 0 else 1

                for tl_page_idx in range(num_tl_pages):
                    fig_tl = plt.figure(figsize=(8.5, 11))
                    try:
                        ax = fig_tl.add_subplot(1, 1, 1)
                        ax.axis("off")

                        page_num_str = f" (Page {tl_page_idx + 1} of {num_tl_pages})" if num_tl_pages > 1 else ""
                        ax.text(0.5, 0.96, f"Chronological Event Timeline{page_num_str}", ha="center", va="top", fontsize=14, fontweight="bold", color="#1a202c")

                        start_i = tl_page_idx * tl_chunk_size
                        end_i = min(start_i + tl_chunk_size, len(display_events))
                        chunk_events = display_events[start_i:end_i]

                        sub_text = f"Showing events {start_i + 1} to {end_i} of {total_events} total events" if total_events > 0 else "No timeline events recorded."
                        if omitted_events_count > 0 and tl_page_idx == (num_tl_pages - 1):
                            sub_text += f" ({omitted_events_count} additional events omitted from PDF; see JSON report)"
                        ax.text(0.5, 0.92, sub_text, ha="center", va="top", fontsize=9.5, color="#718096")

                        # Column proportions: Time | Event Source & Type | Category | Severity | Description
                        # Must sum to 1.0 (relative to bbox width)
                        _TL_OVF_COL_WIDTHS = [0.09, 0.25, 0.12, 0.10, 0.44]
                        _TL_OVF_BBOX = [0.05, 0.10, 0.90, 0.78]

                        chunk_rows = []
                        for ev in chunk_events:
                            ts_label = datetime.datetime.fromtimestamp(ev["timestamp"]).strftime("%H:%M:%S") if ev.get("timestamp") else "N/A"
                            raw_desc = ev.get("description", "")
                            wrapped_desc = textwrap.fill(raw_desc, width=52)
                            wrapped_src = textwrap.fill(
                                f"[{ev.get('source', '')}] {ev.get('event_type', '')}",
                                width=28,
                            )
                            chunk_rows.append([
                                ts_label,
                                wrapped_src,
                                ev.get("category", ""),
                                ev.get("severity", ""),
                                wrapped_desc,
                            ])

                        if chunk_rows:
                            t_tl = ax.table(
                                cellText=chunk_rows,
                                colLabels=["Time", "Event Source & Type", "Category", "Severity", "Description"],
                                loc="top",
                                bbox=_TL_OVF_BBOX,
                                colWidths=_TL_OVF_COL_WIDTHS,
                            )
                            t_tl.auto_set_font_size(False)
                            t_tl.set_fontsize(7.5)

                            # Compute per-row heights based on max line count across columns
                            n_rows_total = len(chunk_rows) + 1  # +1 for header row
                            base_h = _TL_OVF_BBOX[3] / n_rows_total
                            row_line_counts = {}
                            for (r, c), cell in t_tl.get_celld().items():
                                if r == 0:
                                    continue
                                n_lines = max(1, len(cell.get_text().get_text().splitlines()))
                                row_line_counts[r] = max(row_line_counts.get(r, 1), n_lines)

                            for (r, c), cell in t_tl.get_celld().items():
                                if r == 0:
                                    cell.set_facecolor("#edf2f7")
                                    cell.set_text_props(weight="bold", color="#2d3748")
                                    cell.set_height(base_h)
                                else:
                                    n_lines = row_line_counts.get(r, 1)
                                    cell.set_height(base_h * max(1, n_lines))
                                    cell.set_text_props(va="top")
                                    if c == 3:
                                        sev_val = cell.get_text().get_text()
                                        cell.set_text_props(weight="bold", color="#dc3545" if sev_val in ("CRITICAL", "WARNING") else "#2b6cb0", va="top")
                        else:
                            ax.text(0.5, 0.5, "No chronological event timeline records found.", ha="center", va="center", fontsize=10, color="#718096", style="italic")

                        pdf.savefig(fig_tl)
                    finally:
                        plt.close(fig_tl)

        logger.info(f"PDF report generated at: {pdf_path}")
        return pdf_path

    def generate_html_report(self, analysis_data: Dict[str, Any], filename: Optional[str] = None, charts: Optional[Dict[str, str]] = None) -> str:
        """
        Compiles a self-contained, beautifully styled interactive HTML report.
        """
        exp = analysis_data.get("experiment", {})
        profile = exp.get("profile", "unknown")
        timestamp_str = datetime.datetime.fromtimestamp(exp.get("start_time", time.time())).strftime("%Y%m%d_%H%M%S")
        html_filename = filename or f"report_{profile}_{timestamp_str}.html"
        html_path = os.path.join(self.output_dir, html_filename)

        sla = analysis_data.get("sla", {})
        overall_status = sla.get("overall_status", "UNKNOWN")
        badge_class = "badge-pass" if overall_status == "PASS" else ("badge-fail" if overall_status == "FAIL" else "badge-unknown")
        
        bn = analysis_data.get("bottleneck_analysis", {})
        confidence = bn.get("confidence", "HIGH")
        bn_label_header = "Primary Bottleneck Candidate" if confidence == "LOW_SAMPLE_SIZE" else "Primary Bottleneck"

        fail = analysis_data.get("failure_analysis", {})
        locust = analysis_data.get("load_metrics", {}).get("locust", {})
        locust_sum = locust.get("summary", {})
        endpoints = locust.get("endpoints", [])
        timeline = analysis_data.get("timeline", [])
        crashes = analysis_data.get("crashes", {})

        # Determine relative paths for charts if available in the same directory
        sys_chart_rel = os.path.basename(charts.get("system_chart", "")) if charts and "system_chart" in charts else ""
        load_chart_rel = os.path.basename(charts.get("load_chart", "")) if charts and "load_chart" in charts else ""

        # Build SLA Rows HTML
        sla_rows_html = ""
        for k, ev in sla.get("evaluations", {}).items():
            m_val = f"{ev.get('measured_value')} {ev.get('unit')}" if ev.get('measured_value') is not None else '<span class="text-muted">N/A</span>'
            lim = f"{ev.get('threshold')} {ev.get('unit')}"
            st = ev.get("status", "UNKNOWN")
            st_class = "status-pass" if st == "PASS" else ("status-fail" if st == "FAIL" else "status-unknown")
            margin_str = f"{ev.get('margin')} {ev.get('unit')}" if ev.get('margin') is not None else "N/A"
            sla_rows_html += f"""
            <tr>
                <td><strong>{ev.get('metric_name', k)}</strong></td>
                <td>{m_val}</td>
                <td>{lim}</td>
                <td>{margin_str}</td>
                <td><span class="pill {st_class}">{st}</span></td>
            </tr>
            """

        # Build Endpoint Rows HTML
        endpoint_rows_html = ""
        if endpoints:
            for ep in endpoints:
                req_cnt = self._val_or_na(ep.get("request_count"))
                fail_cnt = self._val_or_na(ep.get("failure_count"))
                avg_lat = self._val_or_na(ep.get("avg_response_time_ms"), "ms")
                p95_lat = self._val_or_na(ep.get("p95_ms"), "ms")
                p99_lat = self._val_or_na(ep.get("p99_ms"), "ms")
                rps = self._val_or_na(ep.get("requests_per_s"))
                err_pct = ep.get("error_rate_pct", 0.0)
                err_class = "text-danger" if err_pct and err_pct > 0 else "text-success"
                
                endpoint_rows_html += f"""
                <tr>
                    <td><code>{ep.get('method', '')} {ep.get('name', '')}</code></td>
                    <td>{req_cnt}</td>
                    <td><span class="{err_class}">{fail_cnt} ({err_pct}%)</span></td>
                    <td>{avg_lat}</td>
                    <td><strong>{p95_lat}</strong></td>
                    <td>{p99_lat}</td>
                    <td>{rps}</td>
                </tr>
                """
        else:
            endpoint_rows_html = '<tr><td colspan="7" class="text-muted" style="text-align: center;">No HTTP endpoint data recorded.</td></tr>'

        # Build Timeline Rows HTML
        timeline_rows_html = ""
        if timeline:
            sorted_tl = sorted(timeline, key=lambda e: (e.get("timestamp") is None, e.get("timestamp") or 0))
            for ev in sorted_tl:
                ts_str = datetime.datetime.fromtimestamp(ev["timestamp"]).strftime("%H:%M:%S") if ev.get("timestamp") else "N/A"
                sev = ev.get("severity", "INFO")
                sev_class = "sev-critical" if sev in ("CRITICAL", "WARNING") else "sev-info"
                timeline_rows_html += f"""
                <tr>
                    <td class="text-nowrap">{ts_str}</td>
                    <td><span class="badge-source">{ev.get('source', '')}</span> <strong>{ev.get('event_type', '')}</strong></td>
                    <td><span class="pill pill-muted">{ev.get('category', '')}</span></td>
                    <td><span class="pill {sev_class}">{sev}</span></td>
                    <td>{ev.get('description', '')}</td>
                </tr>
                """
        else:
            timeline_rows_html = '<tr><td colspan="5" class="text-muted" style="text-align: center;">No timeline events recorded.</td></tr>'

        # Build Diagnostic Evidence List HTML
        evidence_items = bn.get("evidence", []) + fail.get("evidence", [])
        evidence_html = "".join([f"<li>{e}</li>" for e in evidence_items]) if evidence_items else "<li>All monitored parameters operated within acceptable operational thresholds.</li>"

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Data Center Simulation Performance Report - {profile.upper()}</title>
    <style>
        :root {{
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --border-color: #e2e8f0;
            --primary: #3b82f6;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            margin: 0;
            padding: 30px 20px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            margin-bottom: 25px;
        }}
        .header h1 {{
            margin: 0 0 8px 0;
            font-size: 26px;
            color: #0f172a;
        }}
        .header .subtitle {{
            color: var(--text-muted);
            font-size: 14px;
        }}
        .banner {{
            padding: 16px 20px;
            border-radius: 8px;
            color: white;
            font-size: 18px;
            font-weight: bold;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .badge-pass {{ background: linear-gradient(135deg, #10b981, #059669); }}
        .badge-fail {{ background: linear-gradient(135deg, #ef4444, #dc2626); }}
        .badge-unknown {{ background: linear-gradient(135deg, #f59e0b, #d97706); }}
        .card {{
            background: var(--card-bg);
            border-radius: 8px;
            border: 1px solid var(--border-color);
            padding: 22px;
            margin-bottom: 25px;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        }}
        .card h2 {{
            font-size: 18px;
            margin-top: 0;
            margin-bottom: 16px;
            color: #0f172a;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 8px;
        }}
        .grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 768px) {{
            .grid-2 {{ grid-template-columns: 1fr; }}
        }}
        .meta-list {{
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .meta-list li {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #f1f5f9;
            font-size: 14px;
        }}
        .meta-list li:last-child {{ border-bottom: none; }}
        .meta-label {{ color: var(--text-muted); font-weight: 500; }}
        .meta-val {{ font-weight: 600; color: #1e293b; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            text-align: left;
        }}
        th, td {{
            padding: 10px 14px;
            border-bottom: 1px solid var(--border-color);
        }}
        th {{
            background-color: #f8fafc;
            color: #475569;
            font-weight: 600;
        }}
        tr:hover {{ background-color: #f8fafc; }}
        .pill {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
        }}
        .status-pass, .sev-info {{ background-color: #d1fae5; color: #065f46; }}
        .status-fail, .sev-critical {{ background-color: #fee2e2; color: #991b1b; }}
        .status-unknown {{ background-color: #fef3c7; color: #92400e; }}
        .pill-muted {{ background-color: #f1f5f9; color: #475569; }}
        .badge-source {{
            background: #e0f2fe;
            color: #0369a1;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: bold;
        }}
        .conclusion-box {{
            background: #f1f5f9;
            border-left: 4px solid var(--primary);
            padding: 14px 18px;
            border-radius: 0 6px 6px 0;
            font-size: 14.5px;
            margin-bottom: 15px;
        }}
        .evidence-list {{
            margin: 0;
            padding-left: 20px;
            font-size: 14px;
            color: #334155;
        }}
        .evidence-list li {{ margin-bottom: 6px; }}
        .chart-container {{
            text-align: center;
            margin-top: 15px;
        }}
        .chart-img {{
            max-width: 100%;
            height: auto;
            border-radius: 6px;
            border: 1px solid var(--border-color);
        }}
        code {{
            background-color: #f1f5f9;
            padding: 2px 5px;
            border-radius: 4px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 13px;
        }}
        .text-danger {{ color: var(--danger); font-weight: bold; }}
        .text-success {{ color: var(--success); font-weight: bold; }}
        .text-muted {{ color: var(--text-muted); }}
        .text-nowrap {{ white-space: nowrap; }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>DATA CENTER SIMULATION PERFORMANCE REPORT</h1>
            <div class="subtitle">Profile: <strong>{profile.upper()}</strong> | Generated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        </div>

        <!-- Overall SLA Banner -->
        <div class="banner {badge_class}">
            <div>OVERALL SLA VERDICT: {overall_status}</div>
            <div style="font-size: 14px; font-weight: 500;">{sla.get('passed_count', 0)} of {sla.get('total_checks', 4)} SLA Targets Satisfied</div>
        </div>

        <!-- Executive Summary Grid -->
        <div class="grid-2">
            <div class="card">
                <h2>1. Experiment Overview</h2>
                <ul class="meta-list">
                    <li><span class="meta-label">Workload Profile</span><span class="meta-val">{profile}</span></li>
                    <li><span class="meta-label">Execution Duration</span><span class="meta-val">{exp.get('duration_seconds', 0)} seconds</span></li>
                    <li><span class="meta-label">Start Time (T1)</span><span class="meta-val">{exp.get('start_time', 'N/A')}</span></li>
                    <li><span class="meta-label">End Time (T2)</span><span class="meta-val">{exp.get('end_time', 'N/A')}</span></li>
                    <li><span class="meta-label">Total Requests</span><span class="meta-val">{self._val_or_na(locust_sum.get('total_requests'))}</span></li>
                    <li><span class="meta-label">Watchdog Crashes</span><span class="meta-val">{crashes.get('crash_count', 0)}</span></li>
                    <li><span class="meta-label">{bn_label_header}</span><span class="meta-val">{bn.get('primary_bottleneck', 'None')}</span></li>
                    <li><span class="meta-label">Statistical Confidence</span><span class="meta-val">{confidence}</span></li>
                    <li><span class="meta-label">Failure Classification</span><span class="meta-val">{fail.get('failure_type', 'NO_FAILURES')}</span></li>
                </ul>
            </div>

            <div class="card">
                <h2>2. Executive Conclusion & Findings</h2>
                <div class="conclusion-box">
                    {analysis_data.get('conclusion', 'No conclusion narrative recorded.')}
                </div>
                <h3 style="font-size: 14px; margin: 12px 0 8px 0; color: #475569;">Key Observations & Evidence:</h3>
                <ul class="evidence-list">
                    {evidence_html}
                </ul>
            </div>
        </div>

        <!-- SLA Scorecard Table -->
        <div class="card">
            <h2>3. Service Level Agreement (SLA) Scorecard</h2>
            <table>
                <thead>
                    <tr>
                        <th>Metric Target</th>
                        <th>Measured Value</th>
                        <th>Threshold Limit</th>
                        <th>Margin</th>
                        <th>Result</th>
                    </tr>
                </thead>
                <tbody>
                    {sla_rows_html}
                </tbody>
            </table>
        </div>

        <!-- Visual Charts Section -->
        {f'''
        <div class="card">
            <h2>4. Hardware & System Dynamics Over Time</h2>
            <div class="chart-container">
                <img class="chart-img" src="{sys_chart_rel}" alt="System Resource Metrics Chart">
            </div>
        </div>
        ''' if sys_chart_rel else ''}

        {f'''
        <div class="card">
            <h2>5. Locust Workload, RPS & Latency Progression</h2>
            <div class="chart-container">
                <img class="chart-img" src="{load_chart_rel}" alt="Locust Performance Chart">
            </div>
        </div>
        ''' if load_chart_rel else ''}

        <!-- HTTP Endpoint Breakdown Table -->
        <div class="card">
            <h2>6. HTTP Endpoint Breakdown</h2>
            <table>
                <thead>
                    <tr>
                        <th>HTTP Endpoint</th>
                        <th>Requests</th>
                        <th>Failures (Rate %)</th>
                        <th>Avg Latency</th>
                        <th>P95 Latency</th>
                        <th>P99 Latency</th>
                        <th>Throughput (RPS)</th>
                    </tr>
                </thead>
                <tbody>
                    {endpoint_rows_html}
                </tbody>
            </table>
        </div>

        <!-- Event Timeline Table -->
        <div class="card">
            <h2>7. Chronological Event Timeline</h2>
            <table>
                <thead>
                    <tr>
                        <th>Timestamp</th>
                        <th>Event Source & Type</th>
                        <th>Category</th>
                        <th>Severity</th>
                        <th>Description</th>
                    </tr>
                </thead>
                <tbody>
                    {timeline_rows_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"HTML report generated at: {html_path}")
        return html_path
