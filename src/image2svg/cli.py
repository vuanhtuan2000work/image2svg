"""Command-line entry points for batch conversion and the local web UI."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Sequence

from image2svg.convert import (
    DEFAULT_SHARPNESS,
    DEFAULT_SMOOTHING,
    SMOOTHING_PRESETS,
    convert_one,
    detect_optimizer,
    load_recipes,
    recipe_for,
)
from image2svg.paths import out_assets_dir, raw_assets_dir, repo_root


def _add_convert_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--part",
        help="Only process one part type (e.g. eye). Omit to process all folders under assets/raw/.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing SVG files.")
    parser.add_argument(
        "--smoothing",
        choices=list(SMOOTHING_PRESETS.keys()),
        default=DEFAULT_SMOOTHING,
        help="Edge smoothing level via Lanczos upscale before tracing. Default: %(default)s.",
    )
    parser.add_argument(
        "--color-precision",
        type=int,
        default=None,
        help="Color precision 1-8 (higher keeps more colors). Defaults to recipe value.",
    )
    parser.add_argument(
        "--sharpness",
        type=int,
        default=DEFAULT_SHARPNESS,
        help="Unsharp-mask amount 0-250 before tracing. Default: %(default)s.",
    )
    parser.add_argument("--remove-bg", action="store_true", help="Remove background (transparent).")
    parser.add_argument("--trim", action="store_true", help="Trim padding to content bounds.")


def run_convert(args: argparse.Namespace) -> int:
    recipes = load_recipes()
    optimizer = detect_optimizer()
    if optimizer == "none":
        print("[warn] Neither SVGO nor scour found — skipping SVG optimization.", file=sys.stderr)

    raw_dir = raw_assets_dir()
    out_dir = out_assets_dir()
    root = repo_root()

    if args.part:
        parts = [args.part]
    elif raw_dir.exists():
        parts = [d.name for d in raw_dir.iterdir() if d.is_dir()]
    else:
        parts = []

    total, skipped, t0 = 0, 0, time.time()

    for part in parts:
        part_dir = raw_dir / part
        if not part_dir.is_dir():
            print(f"[warn] Missing folder assets/raw/{part}/", file=sys.stderr)
            continue

        params = recipe_for(part, recipes)
        if args.color_precision is not None:
            params["color_precision"] = max(1, min(8, args.color_precision))

        for src in sorted(part_dir.glob("*.png")):
            dst = out_dir / part / f"{src.stem}.svg"
            if dst.exists() and not args.overwrite:
                skipped += 1
                continue
            try:
                rel = dst.relative_to(root)
            except ValueError:
                rel = dst
            print(f"[{part}] {src.name} -> {rel}")
            convert_one(
                src,
                dst,
                params,
                optimizer,
                smoothing=args.smoothing,
                sharpness=args.sharpness,
                remove_bg=args.remove_bg,
                trim=args.trim,
            )
            total += 1

    print(
        f"\nDone: {total} file(s) ({skipped} skipped) in {time.time() - t0:.1f}s "
        f"| optimizer={optimizer} | smoothing={args.smoothing}"
    )
    return 0


def run_serve(args: argparse.Namespace) -> int:
    from image2svg.web.app import main as serve_main

    if args.host:
        os.environ["HOST"] = args.host
    if args.port is not None:
        os.environ["PORT"] = str(args.port)
    serve_main()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)

    if argv_list and argv_list[0] == "serve":
        parser = argparse.ArgumentParser(prog="image2svg serve", description="Start the local web UI")
        parser.add_argument("--host", default=None, help="Bind host (default: HOST env or 127.0.0.1)")
        parser.add_argument("--port", type=int, default=None, help="Bind port (default: PORT env or 8765)")
        return run_serve(parser.parse_args(argv_list[1:]))

    # `image2svg convert ...` or legacy `image2svg --part eye`
    rest = argv_list[1:] if argv_list and argv_list[0] == "convert" else argv_list

    parser = argparse.ArgumentParser(
        prog="image2svg",
        description="Batch PNG -> SVG conversion (vtracer + optional SVGO/scour).",
    )
    _add_convert_arguments(parser)
    return run_convert(parser.parse_args(rest))


if __name__ == "__main__":
    raise SystemExit(main())
