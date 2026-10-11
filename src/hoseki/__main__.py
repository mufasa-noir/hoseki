"""Command-line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from hoseki import __version__
from hoseki.app import create_app
from hoseki.config import Config
from hoseki.errors import ConfigError, JailError


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hoseki",
        description="Hoseki — local tool bridge daemon.",
    )
    p.add_argument("--version", action="version", version=f"hoseki {__version__}")

    sub = p.add_subparsers(dest="cmd")

    serve = sub.add_parser("serve", help="Run the daemon.")
    serve.add_argument("--config", type=Path, default=None,
                       help="Path to config.toml")
    serve.add_argument("--workspace", type=Path, default=None,
                       help="Override [workspace].root")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--reload", action="store_true",
                       help="uvicorn auto-reload (development only)")

    mcp = sub.add_parser("mcp", help="Run an MCP server over stdio.")
    mcp.add_argument("--config", type=Path, default=None)
    mcp.add_argument("--workspace", type=Path, default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "mcp":
        overrides: dict = {}
        if getattr(args, "workspace", None) is not None:
            overrides["workspace_root"] = args.workspace
        try:
            config = Config.load(getattr(args, "config", None), overrides)
        except ConfigError as e:
            print(f"config error: {e}", file=sys.stderr)
            return 2
        from hoseki.mcp import serve_stdio
        return serve_stdio(config)

    if args.cmd in (None, "serve"):
        overrides = {}
        if getattr(args, "workspace", None) is not None:
            overrides["workspace_root"] = args.workspace
        if getattr(args, "host", None) is not None:
            overrides["host"] = args.host
        if getattr(args, "port", None) is not None:
            overrides["port"] = args.port

        try:
            config = Config.load(getattr(args, "config", None), overrides)
        except ConfigError as e:
            print(f"config error: {e}", file=sys.stderr)
            return 2
        except JailError as e:
            print(f"workspace error: {e}", file=sys.stderr)
            return 2

        try:
            app = create_app(config)
        except JailError as e:
            print(f"startup error: {e}", file=sys.stderr)
            return 2

        print(
            f"hoseki {__version__} listening on "
            f"http://{config.server.host}:{config.server.port}  "
            f"workspace={config.workspace_root}",
            file=sys.stderr,
        )
        uvicorn.run(
            app,
            host=config.server.host,
            port=config.server.port,
            log_level="info",
            reload=bool(getattr(args, "reload", False)),
        )
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())