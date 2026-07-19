from __future__ import annotations

from image2svg.cli import main


def test_cli_help_exits_cleanly() -> None:
    try:
        main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("argparse --help should SystemExit(0)")
