# Tools

Developer tools, not part of the application at run time. One command, run from the repository:

    backend/.venv/Scripts/python.exe tools/dev.py <command> ...

| Command | Purpose |
|---|---|
| `serve [--port 8765]` | Serves the built interface against an isolated workspace (`.qa/`), never the user's data |
| `shots <out> <light\|dark> <WxH> name=<route>...` | Screenshots of that server with a headless Edge; `--click`, `--type`, `--text`, `--timings`, `--block` (see `shots.py`) |
| `export-project <folder>` | Exports a project (read only) to `dist/projects/` for the folder to send |
| `schema [version]` | Builds `data/namelist_schema_<version>.json` from WRF's Registry and README.namelist |
| `variables <Registry> <out>` | Builds `data/variables_4.8.0.json`, the WRF output variable catalogue |
| `turbines` | Imports the turbine model catalogue (`data/turbines/`) |
| `tests [pytest arguments]` | Runs the server tests inside the WSL distribution `OffshoreWindStudio-Build` (about a minute) |

| File | Content |
|---|---|
| `dev.py` | The command: `serve` and `export-project`, and the entry of the others |
| `shots.py` | The screenshots (Edge over the DevTools protocol, its own temporary profile) |
| `catalogs.py` | The three catalogue generators |
| `check_map_display.mjs` | Checks of the farm display by zoom level: `node tools/check_map_display.mjs` |
