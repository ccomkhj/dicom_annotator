import argparse
import sys
from pathlib import Path

import uvicorn

from .api import create_app
from .config import load_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dicom-annotator")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="Run the local annotator server")
    serve.add_argument("--project", required=True, type=Path, help="Project root directory")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        project_root = args.project.resolve()
        if not project_root.is_dir():
            print(f"project root not found: {project_root}", file=sys.stderr)
            return 2
        project = load_project(project_root)
        app = create_app(project_root, project)
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
        return 0
    return 2
