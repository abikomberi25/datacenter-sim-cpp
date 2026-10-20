import os
import re
import math
import time
import inspect
import pytest
import matplotlib.pyplot as plt
import matplotlib.text as mtext
import matplotlib.table as mtable
from matplotlib.backends.backend_pdf import PdfPages
from unittest.mock import patch

from analysis.report_generator import ReportGenerator

def get_pdf_page_count(pdf_path: str) -> int:
    """Reads PDF binary content and counts /Type /Page objects."""
    with open(pdf_path, "rb") as f:
        content = f.read()
    return len(re.findall(rb"/Type\s*/Page\b", content))

def extract_figure_text(figure) -> str:
    """Extracts all text elements from figure titles, axes, and table cells."""
    texts = [t.get_text() for t in figure.findobj(match=mtext.Text)]
    for tbl in figure.findobj(match=mtable.Table):
        for cell in tbl.get_celld().values():
            txt = cell.get_text().get_text()
            if txt:
                texts.append(txt)
    return " ".join(texts)

@pytest.fixture
def sample_analysis_data():
    """Provides a realistic, fully populated analysis result dictionary."""
    now = 1787489781.0
    return {
        "experiment": {
            "profile": "normal_day",
            "start_time": now,
            "end_time": now + 300.0,
            "duration_seconds": 300.0,
            "time_window_source": "EXPLICIT_CLI",
            "is_historical": True,
        },
        "system_metrics": {
            "cpu": {
                "available": True,
                "peak": 68.5,
                "peak_timestamp": now + 120.0,
                "series": [
                    {"timestamp": now + i * 15, "value": 40.0 + i * 2.0}
                    for i in range(10)
                ],
            },
            "memory": {
                "available": True,
                "peak": 72.0,
                "peak_timestamp": now + 150.0,
                "series": [
                    {"timestamp": now + i * 15, "value": 55.0 + i * 1.5}
                    for i in range(10)
                ],
            },
            "network": {
                "available": True,
                "device": "eth0",
                "classification": "HOST_PHYSICAL",
                "total_rx_mib": 120.5,
                "total_tx_mib": 45.2,
                "peak_rx_mib_s": 8.4,
                "peak_tx_mib_s": 3.1,
                "peak_rx_MBps": 8.4,
                "peak_tx_MBps": 3.1,
                "rx_series": [
                    {"timestamp": now + i * 15, "value": 3.0 + (i % 3)}
                    for i in range(10)
                ],
                "tx_series": [
                    {"timestamp": now + i * 15, "value": 1.0 + (i % 2)}
                    for i in range(10)
                ],
            },
        },
        "load_metrics": {
            "locust": {
                "summary": {
                    "total_requests": 2500,
                    "successful_requests": 2490,
                    "failed_requests": 10,
                    "error_rate_pct": 0.4,
                    "throughput_rps": 25.0,
                    "p95_latency_ms": 180.0,
                    "is_empty": False,
                },
                "endpoints": [
                    {
                        "method": "GET",
                        "name": "/api/users",
                        "request_count": 1200,
                        "failure_count": 2,
                        "avg_response_time_ms": 45.0,
                        "p95_ms": 110.0,
                        "requests_per_s": 12.0,
                        "error_rate_pct": 0.17,
                    },
                    {
                        "method": "POST",
                        "name": "/api/login",
                        "request_count": 800,
                        "failure_count": 5,
                        "avg_response_time_ms": 85.0,
                        "p95_ms": 210.0,
                        "requests_per_s": 8.0,
                        "error_rate_pct": 0.62,
                    },
                ],
                "history_series": [
                    {
                        "timestamp": now + i * 15,
                        "requests_per_s": 20.0 + i,
                        "user_count": 10 + i * 5,
                        "p95_ms": 150.0 + i * 3,
                    }
                    for i in range(10)
                ],
            }
        },
        "sla": {
            "overall_status": "PASS",
            "passed_count": 4,
            "failed_count": 0,
            "unknown_count": 0,
            "total_checks": 4,
            "thresholds": {
                "p95_latency_ms": 500.0,
                "error_rate_pct": 1.0,
                "cpu_pct": 80.0,
                "memory_pct": 90.0,
            },
            "evaluations": {
                "p95_latency": {
                    "metric_name": "P95 Response Time",
                    "measured_value": 180.0,
                    "threshold": 500.0,
                    "unit": "ms",
                    "status": "PASS",
                    "margin": 320.0,
                    "evaluated": True,
                },
                "error_rate": {
                    "metric_name": "Error Rate",
                    "measured_value": 0.4,
                    "threshold": 1.0,
                    "unit": "%",
                    "status": "PASS",
                    "margin": 0.6,
                    "evaluated": True,
                },
                "cpu_utilization": {
                    "metric_name": "Peak CPU Utilization",
                    "measured_value": 68.5,
                    "threshold": 80.0,
                    "unit": "%",
                    "status": "PASS",
                    "margin": 11.5,
                    "evaluated": True,
                },
                "memory_utilization": {
                    "metric_name": "Peak Memory Utilization",
                    "measured_value": 72.0,
                    "threshold": 90.0,
                    "unit": "%",
                    "status": "PASS",
                    "margin": 18.0,
                    "evaluated": True,
                },
            },
            "violations": [],
        },
        "crashes": {"crash_detected": False, "crash_count": 0, "crashes": []},
        "bottleneck_analysis": {
            "primary_bottleneck": "None",
            "classification": "SYSTEM_HEALTHY",
            "confidence": "HIGH",
            "suspected_resources": [],
            "evidence": ["All measured system and load parameters remained within safe thresholds."],
        },
        "failure_analysis": {
            "failure_type": "NO_FAILURES",
            "severity": "NONE",
            "failure_count": 0,
            "evidence": [],
        },
        "timeline": [
            {
                "timestamp": now,
                "event_type": "EXPERIMENT_START",
                "source": "RUNNER",
                "category": "OBSERVED",
                "severity": "INFO",
                "description": f"Experiment started at T1 ({now})",
            },
            {
                "timestamp": now + 15.0,
                "event_type": "LOAD_STARTED",
                "source": "LOCUST",
                "category": "OBSERVED",
                "severity": "INFO",
                "description": "Workload generation began with 10 users",
            },
            {
                "timestamp": now + 300.0,
                "event_type": "EXPERIMENT_END",
                "source": "RUNNER",
                "category": "OBSERVED",
                "severity": "INFO",
                "description": f"Experiment completed at T2 ({now + 300.0})",
            },
        ],
        "conclusion": "The experiment executed 2500 requests with overall SLA status 'PASS' (4/4 checks satisfied). The system operated within all performance, reliability, and resource boundaries.",
    }


class TestDEF001MethodConsolidation:
    """Tests for DEF-001: Consolidate duplicated PDF generation and helper code."""

    def test_single_generate_pdf_report_definition(self):
        """Verifies exactly one generate_pdf_report method exists on ReportGenerator."""
        members = [name for name, _ in inspect.getmembers(ReportGenerator, predicate=inspect.isfunction) if name == "generate_pdf_report"]
        assert len(members) == 1

        src = inspect.getsource(ReportGenerator)
        matches = re.findall(r"def\s+generate_pdf_report\s*\(", src)
        assert len(matches) == 1

    def test_single_val_or_na_definition(self):
        """Verifies exactly one _val_or_na helper exists on ReportGenerator."""
        src = inspect.getsource(ReportGenerator)
        matches = re.findall(r"def\s+_val_or_na\s*\(", src)
        assert len(matches) == 1

    def test_val_or_na_formatting(self):
        """Tests that _val_or_na formats strings, numbers, None, empty, and units properly."""
        assert ReportGenerator._val_or_na(None) == "N/A"
        assert ReportGenerator._val_or_na("") == "N/A"
        assert ReportGenerator._val_or_na("N/A") == "N/A"
        assert ReportGenerator._val_or_na(150.2, "ms") == "150.2 ms"
        assert ReportGenerator._val_or_na(0, "s") == "0 s"
        assert ReportGenerator._val_or_na("Normal") == "Normal"


class TestDEF013TableOverflowAndPagination:
    """Tests for DEF-013: Endpoint and timeline table overflow handling."""

    def test_compact_layout_for_small_tables(self, tmp_path, sample_analysis_data):
        """When endpoints <= 7 and timeline <= 12, exactly 4 pages are produced."""
        gen = ReportGenerator(output_dir=str(tmp_path))
        pdf_path = gen.generate_pdf_report(sample_analysis_data, filename="compact.pdf")

        assert os.path.exists(pdf_path)
        assert get_pdf_page_count(pdf_path) == 4

    def test_overflow_endpoints_pagination(self, tmp_path, sample_analysis_data):
        """When endpoints > 7, endpoints table is paginated across pages with repeated headers."""
        sample_analysis_data["load_metrics"]["locust"]["endpoints"] = [
            {
                "method": "GET",
                "name": f"/api/endpoint_{i}",
                "request_count": 100 * (i + 1),
                "failure_count": i,
                "avg_response_time_ms": 20.0 + i,
                "p95_ms": 50.0 + i,
                "requests_per_s": 5.0,
            }
            for i in range(16)
        ]

        captured_figures = []
        original_savefig = PdfPages.savefig

        def spy_savefig(self, figure=None, **kwargs):
            if figure is not None:
                captured_figures.append(extract_figure_text(figure))
            return original_savefig(self, figure, **kwargs)

        with patch.object(PdfPages, "savefig", spy_savefig):
            gen = ReportGenerator(output_dir=str(tmp_path))
            pdf_path = gen.generate_pdf_report(sample_analysis_data, filename="overflow_ep.pdf")

        # 3 base pages + 2 endpoint pages + 1 timeline page = 6 pages
        assert get_pdf_page_count(pdf_path) == 6
        assert len(captured_figures) == 6

        # Check page text contains continuation header and endpoint rows
        ep_page_1 = captured_figures[3]
        ep_page_2 = captured_figures[4]
        assert "HTTP Endpoint Performance Breakdown" in ep_page_1
        assert "Page 1 of 2" in ep_page_1
        assert "/api/endpoint_0" in ep_page_1
        assert "Page 2 of 2" in ep_page_2
        assert "/api/endpoint_15" in ep_page_2

    def test_overflow_timeline_pagination(self, tmp_path, sample_analysis_data):
        """When timeline events > 12, timeline is paginated cleanly across continuation pages."""
        now = 1000.0
        sample_analysis_data["timeline"] = [
            {
                "timestamp": now + i * 10,
                "event_type": f"EVENT_STEP_{i}",
                "source": "SIM",
                "category": "OBSERVED",
                "severity": "INFO",
                "description": f"Simulation test event sequence {i}",
            }
            for i in range(25)
        ]

        captured_figures = []
        original_savefig = PdfPages.savefig

        def spy_savefig(self, figure=None, **kwargs):
            if figure is not None:
                captured_figures.append(extract_figure_text(figure))
            return original_savefig(self, figure, **kwargs)

        with patch.object(PdfPages, "savefig", spy_savefig):
            gen = ReportGenerator(output_dir=str(tmp_path))
            pdf_path = gen.generate_pdf_report(sample_analysis_data, filename="overflow_tl.pdf")

        # 3 base pages + 1 endpoint page + 2 timeline pages = 6 pages
        assert get_pdf_page_count(pdf_path) == 6
        assert len(captured_figures) == 6

        tl_page_1 = captured_figures[4]
        tl_page_2 = captured_figures[5]
        assert "Chronological Event Timeline" in tl_page_1
        assert "Page 1 of 2" in tl_page_1
        assert "EVENT_STEP_0" in tl_page_1
        assert "Page 2 of 2" in tl_page_2
        assert "EVENT_STEP_24" in tl_page_2

    def test_empty_endpoints_and_timeline_messages(self, tmp_path, sample_analysis_data):
        """Empty endpoints and timeline render clear placeholder messages instead of blank space."""
        sample_analysis_data["load_metrics"]["locust"]["endpoints"] = []
        sample_analysis_data["timeline"] = []

        captured_figures = []
        original_savefig = PdfPages.savefig

        def spy_savefig(self, figure=None, **kwargs):
            if figure is not None:
                captured_figures.append(extract_figure_text(figure))
            return original_savefig(self, figure, **kwargs)

        with patch.object(PdfPages, "savefig", spy_savefig):
            gen = ReportGenerator(output_dir=str(tmp_path))
            pdf_path = gen.generate_pdf_report(sample_analysis_data, filename="empty_tables.pdf")

        p4_text = captured_figures[3]
        assert "No HTTP endpoint" in p4_text
        assert "No chronological event timeline" in p4_text


class TestTimelineTableColumnAlignment:
    """Regression tests for timeline table column alignment and text wrapping (compact and overflow paths)."""

    def _make_events(self, now: float, count: int) -> list:
        """Generate `count` realistic timeline events with varying description lengths."""
        templates = [
            ("EXPERIMENT_START", "RUNNER", "OBSERVED", "INFO",
             "Experiment started with a standard normal_day workload profile targeting 10 concurrent users"),
            ("CPU_SPIKE", "PROMETHEUS", "THRESHOLD", "WARNING",
             "CPU utilization crossed 80% for 3 consecutive samples — possible resource saturation detected"),
            ("LOAD_STARTED", "LOCUST", "OBSERVED", "INFO",
             "Workload generation commenced with 10 users ramping to peak over 60 seconds"),
            ("MEMORY_PRESSURE", "PROMETHEUS", "THRESHOLD", "CRITICAL",
             "Memory usage reached 92.4% — heap pressure may cause GC pauses and elevated latency"),
            ("HIGH_LATENCY", "LOCUST", "THRESHOLD", "WARNING",
             "P95 latency exceeded SLA limit of 500ms — measured value 612ms on /api/orders endpoint"),
            ("ERROR_RATE_OK", "LOCUST", "SLA", "INFO",
             "Error rate 0.8% is within the 1.0% limit — SLA check passed"),
            ("NETWORK_SATURATION", "PROMETHEUS", "THRESHOLD", "WARNING",
             "Network RX throughput reached 95 MiB/s which is close to estimated NIC capacity limit"),
            ("WATCHDOG_ALERT", "WATCHDOG", "CRASH", "CRITICAL",
             "Process watchdog detected unexpected container restart on datacenter-api service"),
            ("LOAD_RAMP_COMPLETE", "LOCUST", "OBSERVED", "INFO",
             "User ramp-up complete — all 10 virtual users are now active and generating steady-state load"),
            ("EXPERIMENT_END", "RUNNER", "OBSERVED", "INFO",
             "Experiment completed successfully — all metrics collected and written to output directory"),
        ]
        events = []
        for i in range(count):
            tpl = templates[i % len(templates)]
            events.append({
                "timestamp": now + i * 30.0,
                "event_type": tpl[0],
                "source": tpl[1],
                "category": tpl[2],
                "severity": tpl[3],
                "description": tpl[4],
            })
        return events

    def _capture_figures(self, gen, analysis_data, filename):
        """Generate a PDF and capture every figure's text content."""
        captured = []
        original_savefig = PdfPages.savefig

        def spy(self, figure=None, **kwargs):
            if figure is not None:
                captured.append(figure)
            return original_savefig(self, figure, **kwargs)

        with patch.object(PdfPages, "savefig", spy):
            pdf_path = gen.generate_pdf_report(analysis_data, filename=filename)
        return pdf_path, captured

    def _get_timeline_table(self, fig):
        """Return the timeline Table object found in a figure (identified by header 'Time'), or None."""
        import matplotlib.table as mtable
        tables = fig.findobj(match=mtable.Table)
        for tbl in tables:
            cell_0_0 = tbl.get_celld().get((0, 0))
            if cell_0_0 and cell_0_0.get_text().get_text() == "Time":
                return tbl
        return None

    # ------------------------------------------------------------------
    # compact path (≤7 endpoints, ≤12 timeline events)
    # ------------------------------------------------------------------

    def test_compact_colwidths_defined(self, tmp_path, sample_analysis_data):
        """Compact path: the timeline table must define explicit colWidths (5 columns, all > 0)."""
        now = sample_analysis_data["experiment"]["start_time"]
        sample_analysis_data["timeline"] = self._make_events(now, 10)
        # Keep endpoints ≤ 7 so the compact layout is used
        assert len(sample_analysis_data["load_metrics"]["locust"]["endpoints"]) <= 7

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "compact_col.pdf")

        p4_fig = figs[3]  # page 4 is index 3
        tbl = self._get_timeline_table(p4_fig)
        assert tbl is not None, "No Table object found on page 4"

        # Each column should have a defined (non-uniform) width
        col_widths = [tbl[0, c].get_width() for c in range(5)]
        # Time column must be narrower than Description column
        assert col_widths[0] < col_widths[4], (
            f"Time column ({col_widths[0]:.4f}) should be narrower than "
            f"Description column ({col_widths[4]:.4f})"
        )
        # All widths must be positive
        assert all(w > 0 for w in col_widths), f"All column widths must be positive: {col_widths}"

    def test_compact_no_truncation(self, tmp_path, sample_analysis_data):
        """Compact path: event descriptions must not be truncated with '...'."""
        now = sample_analysis_data["experiment"]["start_time"]
        sample_analysis_data["timeline"] = self._make_events(now, 10)

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "compact_no_trunc.pdf")

        p4_fig = figs[3]
        all_text = extract_figure_text(p4_fig)
        assert "..." not in all_text, (
            "Timeline table cells must not contain '...' truncation markers"
        )

    def test_compact_all_events_present(self, tmp_path, sample_analysis_data):
        """Compact path: all 10 events must appear — none silently dropped."""
        now = sample_analysis_data["experiment"]["start_time"]
        events = self._make_events(now, 10)
        sample_analysis_data["timeline"] = events

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "compact_events.pdf")

        p4_fig = figs[3]
        tbl = self._get_timeline_table(p4_fig)
        assert tbl is not None

        # Row 0 is the header; data rows are 1..N
        data_rows = {r for (r, _) in tbl.get_celld() if r > 0}
        assert len(data_rows) == 10, f"Expected 10 data rows, got {len(data_rows)}"

    def test_compact_top_valignment_on_data_cells(self, tmp_path, sample_analysis_data):
        """Compact path: data cells must use top vertical alignment."""
        now = sample_analysis_data["experiment"]["start_time"]
        sample_analysis_data["timeline"] = self._make_events(now, 6)

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "compact_va.pdf")

        p4_fig = figs[3]
        tbl = self._get_timeline_table(p4_fig)
        assert tbl is not None

        for (r, c), cell in tbl.get_celld().items():
            if r > 0:
                va = cell.get_text().get_va()
                assert va == "top", f"Cell ({r},{c}) has vertical alignment '{va}', expected 'top'"

    def test_compact_column_headers_present(self, tmp_path, sample_analysis_data):
        """Compact path: all 5 column headers must appear in the rendered table."""
        now = sample_analysis_data["experiment"]["start_time"]
        sample_analysis_data["timeline"] = self._make_events(now, 5)

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "compact_headers.pdf")

        p4_text = extract_figure_text(figs[3])
        for header in ("Time", "Event Source & Type", "Category", "Severity", "Description"):
            assert header in p4_text, f"Header '{header}' not found in page 4 text"

    # ------------------------------------------------------------------
    # overflow path (>12 timeline events)
    # ------------------------------------------------------------------

    def test_overflow_colwidths_defined(self, tmp_path, sample_analysis_data):
        """Overflow path: the timeline table must define explicit colWidths (5 columns, all > 0)."""
        now = sample_analysis_data["experiment"]["start_time"]
        sample_analysis_data["timeline"] = self._make_events(now, 15)
        # Keep endpoints ≤ 7 so only timeline causes overflow
        assert len(sample_analysis_data["load_metrics"]["locust"]["endpoints"]) <= 7

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "ovf_col.pdf")

        # Overflow: pages 0=p1, 1=p2, 2=p3, 3=ep-page, 4=tl-page-1, ...
        tl_fig = None
        for fig in figs[3:]:
            tbl = self._get_timeline_table(fig)
            if tbl is not None:
                tl_fig = fig
                tbl_found = tbl
                break
        assert tl_fig is not None, "No timeline table found in overflow pages"

        col_widths = [tbl_found[0, c].get_width() for c in range(5)]
        assert col_widths[0] < col_widths[4], (
            f"Time column ({col_widths[0]:.4f}) must be narrower than "
            f"Description column ({col_widths[4]:.4f})"
        )
        assert all(w > 0 for w in col_widths), f"All column widths must be positive: {col_widths}"

    def test_overflow_no_truncation(self, tmp_path, sample_analysis_data):
        """Overflow path: event descriptions must not be truncated with '...'."""
        now = sample_analysis_data["experiment"]["start_time"]
        sample_analysis_data["timeline"] = self._make_events(now, 15)

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "ovf_no_trunc.pdf")

        for fig in figs[3:]:
            page_text = extract_figure_text(fig)
            assert "..." not in page_text, (
                "Timeline table cells must not contain '...' truncation markers in overflow pages"
            )

    def test_overflow_top_valignment_on_data_cells(self, tmp_path, sample_analysis_data):
        """Overflow path: data cells must use top vertical alignment."""
        now = sample_analysis_data["experiment"]["start_time"]
        sample_analysis_data["timeline"] = self._make_events(now, 15)

        gen = ReportGenerator(output_dir=str(tmp_path))
        _, figs = self._capture_figures(gen, sample_analysis_data, "ovf_va.pdf")

        for fig in figs[3:]:
            tbl = self._get_timeline_table(fig)
            if tbl is None:
                continue
            for (r, c), cell in tbl.get_celld().items():
                if r > 0:
                    va = cell.get_text().get_va()
                    assert va == "top", (
                        f"Overflow cell ({r},{c}) has vertical alignment '{va}', expected 'top'"
                    )


class TestEmptyAndIncompleteChartHandling:
    """Tests for empty, malformed, or missing chart handling."""

    def test_missing_system_metrics_renders_placeholders(self, tmp_path, sample_analysis_data):
        """When Prometheus metrics are unavailable, charts render explicit placeholders."""
        sample_analysis_data["system_metrics"]["cpu"]["series"] = []
        sample_analysis_data["system_metrics"]["memory"]["series"] = []
        sample_analysis_data["system_metrics"]["network"]["rx_series"] = []
        sample_analysis_data["system_metrics"]["network"]["tx_series"] = []

        gen = ReportGenerator(output_dir=str(tmp_path))
        charts = gen.generate_charts(sample_analysis_data, prefix="test_empty_sys")

        assert os.path.exists(charts["system_chart"])
        assert os.path.getsize(charts["system_chart"]) > 1000

    def test_partially_missing_system_metrics_preserved(self, tmp_path, sample_analysis_data):
        """When CPU is present but memory is absent, CPU is still plotted."""
        sample_analysis_data["system_metrics"]["memory"]["series"] = []

        gen = ReportGenerator(output_dir=str(tmp_path))
        charts = gen.generate_charts(sample_analysis_data, prefix="test_partial_sys")
        assert os.path.exists(charts["system_chart"])

    def test_nan_and_inf_values_do_not_crash_chart_rendering(self, tmp_path, sample_analysis_data):
        """Series containing NaN, Inf, and non-numeric junk are filtered without crashing."""
        sample_analysis_data["system_metrics"]["cpu"]["series"] = [
            {"timestamp": 1000.0, "value": 50.0},
            {"timestamp": 1015.0, "value": float("nan")},
            {"timestamp": 1030.0, "value": float("inf")},
            {"timestamp": 1045.0, "value": "INVALID"},
            {"timestamp": 1060.0, "value": 60.0},
        ]
        sample_analysis_data["load_metrics"]["locust"]["history_series"] = [
            {"timestamp": 1000.0, "requests_per_s": 10.0, "user_count": 5, "p95_ms": 100.0},
            {"timestamp": 1015.0, "requests_per_s": float("nan"), "user_count": 5, "p95_ms": None},
            {"timestamp": float("nan"), "requests_per_s": 20.0, "user_count": 10, "p95_ms": 150.0},
            {"timestamp": 1045.0, "requests_per_s": 20.0, "user_count": 10, "p95_ms": 150.0},
        ]

        gen = ReportGenerator(output_dir=str(tmp_path))
        charts = gen.generate_charts(sample_analysis_data, prefix="test_nan_sys")
        pdf_path = gen.generate_pdf_report(sample_analysis_data, filename="test_nan.pdf")

        assert os.path.exists(charts["system_chart"])
        assert os.path.exists(charts["load_chart"])
        assert os.path.exists(pdf_path)


class TestResourceCleanupAndFigureManagement:
    """Tests for Matplotlib figure lifecycle and resource cleanup."""

    def test_no_accumulated_figures_after_pdf_and_chart_generation(self, tmp_path, sample_analysis_data):
        """Ensures that generating charts and PDF closes all Matplotlib figures."""
        plt.close("all")
        assert len(plt.get_fignums()) == 0

        gen = ReportGenerator(output_dir=str(tmp_path))
        for i in range(3):
            charts = gen.generate_charts(sample_analysis_data, prefix=f"run_{i}")
            pdf_path = gen.generate_pdf_report(sample_analysis_data, filename=f"run_{i}.pdf")
            html_path = gen.generate_html_report(sample_analysis_data, filename=f"run_{i}.html", charts=charts)

            assert os.path.exists(pdf_path)
            assert os.path.exists(html_path)

            # Assert strictly 0 lingering figures
            assert len(plt.get_fignums()) == 0

    def test_cleanup_on_rendering_failure(self, tmp_path, sample_analysis_data):
        """Ensures that exceptions during PDF building trigger cleanup of open figures."""
        plt.close("all")
        gen = ReportGenerator(output_dir=str(tmp_path))

        with patch.object(PdfPages, "savefig", side_effect=RuntimeError("Simulated write failure")):
            with pytest.raises(RuntimeError, match="Simulated write failure"):
                gen.generate_pdf_report(sample_analysis_data, filename="fail.pdf")

        # Must have cleaned up all figures
        assert len(plt.get_fignums()) == 0


class TestCrossFormatConsistency:
    """Tests ensuring HTML, PDF, and analysis results display identical verdicts."""

    def test_cross_format_verdict_and_diagnostics(self, tmp_path, sample_analysis_data):
        """Verifies consistent overall status, checks count, and primary bottleneck in PDF and HTML."""
        sample_analysis_data["sla"]["overall_status"] = "FAIL"
        sample_analysis_data["sla"]["passed_count"] = 3
        sample_analysis_data["sla"]["failed_count"] = 1
        sample_analysis_data["bottleneck_analysis"]["primary_bottleneck"] = "CPU Utilization"
        sample_analysis_data["bottleneck_analysis"]["classification"] = "RESOURCE_SATURATION"
        sample_analysis_data["conclusion"] = "Overall SLA status 'FAIL'. Primary bottleneck assessed as 'CPU Utilization'."

        captured_figures = []
        original_savefig = PdfPages.savefig

        def spy_savefig(self, figure=None, **kwargs):
            if figure is not None:
                captured_figures.append(extract_figure_text(figure))
            return original_savefig(self, figure, **kwargs)

        with patch.object(PdfPages, "savefig", spy_savefig):
            gen = ReportGenerator(output_dir=str(tmp_path))
            charts = gen.generate_charts(sample_analysis_data, prefix="consistency")
            pdf_path = gen.generate_pdf_report(sample_analysis_data, filename="consistency.pdf")
            html_path = gen.generate_html_report(sample_analysis_data, filename="consistency.html", charts=charts)

        # PDF Verification
        p1_text = captured_figures[0]
        assert "OVERALL SLA VERDICT: FAIL" in p1_text
        assert "CPU Utilization" in p1_text

        # HTML Verification
        with open(html_path, "r", encoding="utf-8") as f:
            html_text = f.read()
        assert "OVERALL SLA VERDICT: FAIL" in html_text
        assert "CPU Utilization" in html_text
        assert "badge-fail" in html_text
