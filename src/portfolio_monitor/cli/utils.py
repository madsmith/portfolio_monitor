import argparse


def help_on_error(parser: argparse.ArgumentParser) -> None:
    """Make parser print full help (not just usage) on any parse error."""
    parser.error = lambda msg: (parser.print_help(), parser.exit(2, f"\nerror: {msg}\n"))  # type: ignore[method-assign]
