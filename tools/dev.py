"""Developer tools of Offshore Wind Studio, in one command (not part of the application).

    backend/.venv/Scripts/python.exe tools/dev.py <command> ...

    serve [--port 8765]            the built interface (frontend/dist) on an isolated workspace
                                   (.qa/, example project), never the user's data
    shots <out> <light|dark> <WxH> [options] name=<route>...
                                   screenshots of that server with a headless Edge (tools/shots.py)
    export-project <folder>        a project exported, read only, to dist/projects/ for the
                                   folder to send (packaging/make_distribution.py adds it)
    schema [version]               data/namelist_schema_<version>.json from WRF's sources
    variables <Registry> <out>     the WRF variable catalogue from a local WRF source tree
    turbines                       the turbine catalogue (data/turbines/) from NREL's library
    tests [pytest arguments]       the server tests in the WSL distribution OffshoreWindStudio-Build
                                   (about a minute; half an hour under Git Bash)

The farm display checks by zoom level are a Node script: node tools/check_map_display.mjs
"""

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))


def serve(port: int) -> None:
    import uvicorn
    from owstudio.api.app import create_app
    from owstudio.core.settings import Settings, save_settings

    folder = ROOT / ".qa"
    folder.mkdir(exist_ok=True)
    settings = folder / "settings.json"
    if not settings.exists():
        save_settings(
            Settings(data_root=str(folder / "data"), language="fr", profiles=[]),
            settings,
        )
    example = ROOT / "backend" / "src" / "owstudio" / "data" / "examples" / "horns-rev.yaml"
    app = create_app(settings, static_dir=ROOT / "frontend" / "dist", example=example)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def export_project(folder: Path) -> None:
    """Reads the project's case.yaml only (never writes into it) and checks that the export
    imports back to the same project."""
    from owstudio.core.case.model import Case
    from owstudio.core.case.transfer import export_name, read_project
    from owstudio.core.case.transfer import export_project as export

    source = folder / "case.yaml"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    case = Case.from_yaml(source)
    data = export(case, folder)
    assert read_project(data, "check.owstudio.zip").model_dump() == case.model_dump()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before, "the project changed"
    out = ROOT / "dist" / "projects" / export_name(case)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(out, len(data), "bytes")


def tests(arguments: list[str]) -> None:
    """The server tests in the build distribution, where the exported scripts run fast."""
    import subprocess

    drive, rest = str(ROOT).split(":", 1)
    repo = f"/mnt/{drive.lower()}{rest.replace(chr(92), '/')}"
    script = f"{repo}/packaging/linux/run-tests.sh"
    command = ["wsl.exe", "-d", "OffshoreWindStudio-Build", "-u", "root", "bash", script, repo]
    sys.exit(subprocess.call([*command, *arguments]))


def main() -> None:
    parser = argparse.ArgumentParser(prog="tools/dev.py", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve").add_argument("--port", type=int, default=8765)
    commands.add_parser("shots", add_help=False).add_argument("rest", nargs=argparse.REMAINDER)
    commands.add_parser("export-project").add_argument("folder", type=Path)
    commands.add_parser("schema").add_argument("version", nargs="?", default="4.8.0")
    variables = commands.add_parser("variables")
    variables.add_argument("registry", type=Path)
    variables.add_argument("target", type=Path)
    commands.add_parser("turbines")
    commands.add_parser("tests", add_help=False).add_argument("rest", nargs=argparse.REMAINDER)
    args, unknown = parser.parse_known_args()
    sys.path.insert(0, str(Path(__file__).parent))
    if args.command == "serve":
        serve(args.port)
    elif args.command == "shots":
        import shots

        shots.main(args.rest + unknown)
    elif args.command == "export-project":
        export_project(args.folder)
    elif args.command == "tests":
        tests(args.rest + unknown)
    else:
        import catalogs

        if args.command == "schema":
            catalogs.namelist_schema(args.version)
        elif args.command == "variables":
            catalogs.variable_catalog(args.registry, args.target)
        else:
            catalogs.turbine_catalog()


if __name__ == "__main__":
    main()
