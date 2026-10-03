"""Command-line entry point.

    terraform plan -out tfplan
    terraform show -json tfplan > plan.json
    finops-guard check plan.json

Exit code is 0 on pass (and on warn unless `--fail-on warn`), 1 when the gate
fails, 2 on a usage error — so CI blocks a merge exactly when the gate fails.
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import Config
from .engine import run_check
from .report import render_markdown, render_json
from . import __version__


def _load_plan(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="finops-guard",
        description="Shift-left cost, carbon and governance checks for Terraform plans.",
    )
    parser.add_argument("--version", action="version", version=f"finops-guard {__version__}")
    sub = parser.add_subparsers(dest="command")

    chk = sub.add_parser("check", help="Check a `terraform show -json` plan.")
    chk.add_argument("plan", help="Path to the plan JSON, or '-' for stdin.")
    chk.add_argument("--config", "-c", default=None, help="Path to .finops-guard.yml.")
    chk.add_argument("--format", "-f", choices=["md", "json"], default="md",
                     help="Output format (default: md).")
    chk.add_argument("--out", "-o", default=None, help="Write output to a file as well as stdout.")
    chk.add_argument("--fail-on", choices=["fail", "warn"], default=None,
                     help="Block on warnings too (overrides config).")
    chk.add_argument("--fx", type=float, default=None, help="USD->GBP rate override.")
    chk.add_argument("--quiet", "-q", action="store_true", help="Suppress stdout (still writes --out).")

    args = parser.parse_args(argv)
    if args.command != "check":
        parser.print_help()
        return 2

    try:
        plan_json = _load_plan(args.plan)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"finops-guard: could not read plan '{args.plan}': {exc}", file=sys.stderr)
        return 2

    try:
        config = Config.load(args.config)
    except (OSError, RuntimeError) as exc:
        print(f"finops-guard: config error: {exc}", file=sys.stderr)
        return 2
    if args.fail_on:
        config.fail_on = args.fail_on
    if args.fx:
        config.fx_usd_gbp = args.fx

    result = run_check(plan_json, config)
    rendered = render_json(result) if args.format == "json" else render_markdown(result)

    if not args.quiet:
        print(rendered)
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(rendered + "\n")
        except OSError as exc:
            print(f"finops-guard: could not write '{args.out}': {exc}", file=sys.stderr)
            return 2

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
