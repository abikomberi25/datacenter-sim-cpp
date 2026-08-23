import os
import sys
import time
import json
import argparse
import datetime
import logging
from pathlib import Path

from analysis.analyse import AnalysisEngine
from analysis.report_generator import ReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("run_analysis")

def main():
    parser = argparse.ArgumentParser(
        description="Member 6: Data Center Simulation Analysis & Reporting Subsystem"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="normal_day",
        help="Workload profile name (e.g. normal_day, flash_event, stress_test)"
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Custom Locust results CSV prefix/path (default: results_<profile>)"
    )
    parser.add_argument(
        "--start-time",
        type=float,
        default=None,
        help="Experiment start time (Unix epoch seconds). Default: 10m before end time"
    )
    parser.add_argument(
        "--end-time",
        type=float,
        default=None,
        help="Experiment end time (Unix epoch seconds). Default: current time"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="analysis/config.yaml",
        help="Path to analysis configuration YAML file"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Base directory to save charts, PDF reports, and JSON analysis outputs"
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Optional custom filename to export JSON analysis report"
    )

    args = parser.parse_args()

    end_time = args.end_time or time.time()
    start_time = args.start_time or (end_time - 600.0) # default 10m window
    csv_target = args.csv or f"results_{args.profile}"

    logger.info("Initializing Analysis Engine...")
    engine = AnalysisEngine(config_path=args.config)

    logger.info(f"Running analysis for profile '{args.profile}' over [{start_time} -> {end_time}]")
    analysis_result = engine.analyze(
        start_time=start_time,
        end_time=end_time,
        locust_target=csv_target,
        profile_name=args.profile,
    )

    # Export Structured JSON Report & Visualizations into Profile Subdirectory
    timestamp_str = datetime.datetime.fromtimestamp(start_time).strftime("%Y%m%d_%H%M%S")
    profile_out_dir = os.path.join(args.output_dir, args.profile, timestamp_str)
    os.makedirs(profile_out_dir, exist_ok=True)

    json_filename = args.json_out or f"analysis_{args.profile}_{timestamp_str}.json"
    json_path = os.path.join(profile_out_dir, json_filename)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, indent=2)
    logger.info(f"Structured analysis report saved to: {json_path}")

    # Generate Visual Charts, PDF and HTML Reports
    logger.info("Generating charts, PDF and HTML reports...")
    report_gen = ReportGenerator(output_dir=profile_out_dir)
    charts = report_gen.generate_charts(analysis_result, prefix=f"{args.profile}_{timestamp_str}")
    pdf_path = report_gen.generate_pdf_report(
        analysis_result, filename=f"report_{args.profile}_{timestamp_str}.pdf"
    )
    html_path = report_gen.generate_html_report(
        analysis_result, filename=f"report_{args.profile}_{timestamp_str}.html", charts=charts
    )

    # Print Executive Summary to Console
    sla = analysis_result.get("sla", {})
    bn = analysis_result.get("bottleneck_analysis", {})
    fail = analysis_result.get("failure_analysis", {})

    print("\n" + "=" * 60)
    print("      DATA CENTER SIMULATION ANALYSIS REPORT (MEMBER 6)     ")
    print("=" * 60)
    print(f"Profile               : {args.profile}")
    print(f"Experiment Duration   : {analysis_result['experiment']['duration_seconds']} s")
    print(f"Overall SLA Status    : {sla.get('overall_status')}")
    print(f"SLA Checks Passed     : {sla.get('passed_count')} / {sla.get('total_checks')}")
    print(f"Primary Bottleneck    : {bn.get('primary_bottleneck')}")
    print(f"Classification        : {bn.get('classification')}")
    print(f"Confidence Level      : {bn.get('confidence')}")
    print(f"Failure Classification: {fail.get('failure_type')}")
    print(f"Crashes Detected      : {analysis_result['crashes'].get('crash_count', 0)}")
    print(f"Total Requests        : {analysis_result['load_metrics']['locust']['summary'].get('total_requests', 0)}")
    print(f"P95 Latency           : {analysis_result['load_metrics']['locust']['summary'].get('p95_latency_ms', 0)} ms")
    print(f"Error Rate            : {analysis_result['load_metrics']['locust']['summary'].get('error_rate_pct', 0)} %")
    print("-" * 60)
    print("EXECUTIVE CONCLUSION:")
    print(analysis_result.get("conclusion"))
    print("-" * 60)
    print(f"Generated HTML Report : {html_path}")
    print(f"Generated PDF Report  : {pdf_path}")
    print(f"Generated JSON Report : {json_path}")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()

