"""Command-line entry points for running Phase 0 experiments.

    python -m phase0 browser   --trials 20 --out phase0/results
    python -m phase0 ax        --trials 15 --out phase0/results
    python -m phase0 control   --confirm
    python -m phase0 mac-app-capabilities [--app <key>] --out phase0/results
    python -m phase0 summarize --input phase0/results/<file>.jsonl

See phase0/README.md for full usage and interpretation of results.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def cmd_browser(args: argparse.Namespace) -> int:
    from phase0.experiments.browser_background.experiment import ExperimentBlocked, run_experiment

    run_id = args.run_id or _new_run_id()
    try:
        results_path, summary = run_experiment(
            trial_count=args.trials,
            output_dir=Path(args.out),
            run_id=run_id,
            headless=args.headless,
        )
    except ExperimentBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {summary['trials']} trial(s) to {results_path}")
    _print_summary(summary)
    return 0


def cmd_ax(args: argparse.Namespace) -> int:
    from phase0.experiments.macos_ax.experiment import ExperimentBlocked, run_experiment

    run_id = args.run_id or _new_run_id()
    try:
        results_path, summary = run_experiment(
            trial_count=args.trials,
            output_dir=Path(args.out),
            run_id=run_id,
        )
    except ExperimentBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(f"wrote {summary['trials']} trial(s) to {results_path}")
    _print_summary(summary)
    return 0


def cmd_control(args: argparse.Namespace) -> int:
    if not args.confirm:
        print(
            "The positive control deliberately moves your physical mouse cursor.\n"
            "Re-run with --confirm to actually execute it.",
            file=sys.stderr,
        )
        return 2

    from phase0.harness.control import build_positive_control_spec
    from phase0.harness.observers_macos import MacObserver, is_macos
    from phase0.harness.persistence import ResultWriter
    from phase0.harness.runner import ExperimentRunner

    if not is_macos():
        print("BLOCKED: positive control currently only implemented for macOS", file=sys.stderr)
        return 2

    run_id = args.run_id or _new_run_id()
    observer = MacObserver()
    runner = ExperimentRunner(experiment_id="positive_control", run_id=run_id, observer=observer)
    spec = build_positive_control_spec(observer, dx=args.dx, dy=args.dy)
    observation = runner.run_trial("trial-0000-cursor-warp", spec)

    results_path = Path(args.out) / f"positive_control-{run_id}.jsonl"
    ResultWriter(results_path).write(observation)

    print(f"classification: {observation.classification.value}")
    print(f"wrote result to {results_path}")
    return 0 if observation.classification.value == "CURSOR_INTERFERENCE" else 1


def cmd_mac_app_capabilities(args: argparse.Namespace) -> int:
    from phase0.experiments.mac_app_capabilities.matrix import MatrixBlocked, run_matrix

    run_id = args.run_id or _new_run_id()
    try:
        matrix_path, records = run_matrix(output_dir=Path(args.out), run_id=run_id, only_key=args.app)
    except MatrixBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print(f"wrote capability matrix for {len(records)} application(s) to {matrix_path}")
    for record in records:
        print(f"  {record.application}: installed={record.installed} pid={record.pid}")
        print(
            f"    discovery={record.ax_application_creation.value} read={record.semantic_read.value} "
            f"action_verified={record.semantic_action_verified.value} "
            f"mutation_verified={record.value_mutation_verified.value}"
        )
        print(
            f"    background_inspection={record.background_inspection.value} "
            f"occluded_inspection={record.occluded_inspection.value}"
        )
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    from phase0.harness.persistence import read_results, summarize, write_summary

    input_path = Path(args.input)
    observations = list(read_results(input_path))
    summary = summarize(observations)
    _print_summary(summary)

    if args.out:
        write_summary(summary, Path(args.out))
        print(f"wrote summary to {args.out}")
    return 0


def _print_summary(summary: dict) -> None:
    print(f"  trials:                    {summary['trials']}")
    print(f"  successful actions:        {summary['successful_actions']}")
    print(f"  verified postconditions:   {summary['verified_postconditions']}")
    print(f"  errors:                    {summary['error_count']}")
    print(f"  background_safe:           {summary['background_safe_count']} ({summary['background_safe_rate']:.1%})")
    print(
        f"  cursor interference:       {summary['cursor_interference_count']} "
        f"({summary['cursor_interference_rate']:.1%})"
    )
    print(
        f"  foreground interference:   {summary['foreground_interference_count']} "
        f"({summary['foreground_interference_rate']:.1%})"
    )
    print(
        f"  focus interference:        {summary['focus_interference_count']} "
        f"({summary['focus_interference_rate']:.1%})"
    )
    print(f"  multiple interference:     {summary['multiple_interference_count']}")
    print(f"  inconclusive:              {summary['inconclusive_count']}")
    print(f"  unsupported:               {summary['unsupported_count']}")
    lat = summary["latency_ms"]
    if lat["n"]:
        print(f"  latency ms (median/p95):   {lat['median']:.1f} / {lat['p95']:.1f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phase0", description="ComputerAgent Phase 0 capability harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_browser = sub.add_parser("browser", help="run the Playwright browser non-interference experiment")
    p_browser.add_argument("--trials", type=int, default=20)
    p_browser.add_argument("--out", type=str, default=str(DEFAULT_RESULTS_DIR))
    p_browser.add_argument("--run-id", type=str, default=None)
    p_browser.add_argument("--headless", action="store_true", help="run headless (NOT representative of real interference)")
    p_browser.set_defaults(func=cmd_browser)

    p_ax = sub.add_parser("ax", help="run the macOS Accessibility non-interference experiment")
    p_ax.add_argument("--trials", type=int, default=15)
    p_ax.add_argument("--out", type=str, default=str(DEFAULT_RESULTS_DIR))
    p_ax.add_argument("--run-id", type=str, default=None)
    p_ax.set_defaults(func=cmd_ax)

    p_control = sub.add_parser("control", help="run the positive control (visibly moves your cursor)")
    p_control.add_argument("--confirm", action="store_true")
    p_control.add_argument("--dx", type=float, default=80.0)
    p_control.add_argument("--dy", type=float, default=0.0)
    p_control.add_argument("--out", type=str, default=str(DEFAULT_RESULTS_DIR))
    p_control.add_argument("--run-id", type=str, default=None)
    p_control.set_defaults(func=cmd_control)

    p_mac_apps = sub.add_parser(
        "mac-app-capabilities", help="run the Mac Application Capability Matrix across representative real apps"
    )
    p_mac_apps.add_argument("--app", type=str, default=None, help="only probe this target key (e.g. safari, chrome, finder)")
    p_mac_apps.add_argument("--out", type=str, default=str(DEFAULT_RESULTS_DIR))
    p_mac_apps.add_argument("--run-id", type=str, default=None)
    p_mac_apps.set_defaults(func=cmd_mac_app_capabilities)

    p_summarize = sub.add_parser("summarize", help="aggregate an existing JSONL results file")
    p_summarize.add_argument("--input", type=str, required=True)
    p_summarize.add_argument("--out", type=str, default=None)
    p_summarize.set_defaults(func=cmd_summarize)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
