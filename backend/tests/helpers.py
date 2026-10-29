"""Test helpers: isolated settings and data folders, a ready compute profile, and writers of
files the application itself no longer writes (fixtures)."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import f90nml
from fastapi.testclient import TestClient

from owstudio.api.app import create_app
from owstudio.core.case.model import Case
from owstudio.core.engine.profiles import ComputeProfile, EngineInstall
from owstudio.core.engine.windows import manifest
from owstudio.core.method.plan import Plan, Window
from owstudio.core.settings import Settings, save_settings
from owstudio.core.windfarm.files import LAYOUT_FILES, layout_text, turbine_rows, turbine_table

REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev" / "case.yaml"


def wsl_profile(**changes: Any) -> ComputeProfile:
    profile = ComputeProfile(
        id="wsl-test",
        name="WSL test",
        kind="wsl",
        wsl_distro="Ubuntu",
        install=EngineInstall(
            wrf_dir="/opt/WRF",
            wps_dir="/opt/WPS",
            geog_dir="/data/WPS_GEOG",
            work_dir="/scratch/ows",
            input_dir="/data/input",
        ),
    )
    return profile.model_copy(update=changes)


def write_settings(
    tmp_path: Path, profiles: list[ComputeProfile] | None = None, language: str = "en"
) -> Path:
    """Settings of a test: English unless asked, so that tests read the English texts."""
    path = tmp_path / "settings.json"
    save_settings(
        Settings(data_root=str(tmp_path / "data"), profiles=profiles or [], language=language),  # type: ignore[arg-type]
        path,
    )
    return path


def make_client(
    tmp_path: Path,
    profiles: list[ComputeProfile] | None = None,
    static_dir: Path | None = None,
) -> TestClient:
    return TestClient(create_app(write_settings(tmp_path, profiles), static_dir=static_dir))


def write_manifest(case: Case, output_root: Path, states: dict[str, str] | None = None) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / "windows.json.tmp"
    temporary.write_text(json.dumps(manifest(case, states), indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_root / "windows.json")


def write_namelist(nml: f90nml.Namelist, path: Path) -> None:
    # WRF runs on Linux: keep Unix line endings even when written from Windows
    with path.open("w", encoding="ascii", newline="\n") as f:
        nml.write(f)


def write_wind_farm_files(case: Case, directory: Path) -> list[Path]:
    """The layout file of the scheme, one table per custom turbine type in use, and
    turbines.csv recording the farm and label of each line."""
    if not case.farm_scheme:
        return []
    rows = turbine_rows(case)
    layout = directory / LAYOUT_FILES[case.farm_scheme.scheme]
    layout.write_text(layout_text(case), encoding="ascii", newline="\n")
    index = directory / "turbines.csv"
    lines = ["index,farm,farm_number,turbine,type,lat,lon"] + [
        f"{r['index']},{r['farm']},{r['farm_number']},{r['turbine']},{r['type']},{r['lat']:.6f},{r['lon']:.6f}"
        for r in rows
    ]
    index.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    written = [layout, index]
    used = {r["type"] for r in rows}
    for number, turbine in sorted(case.turbine_types.items()):
        if number in used:
            table = directory / f"wind-turbine-{number}.tbl"
            table.write_text(turbine_table(turbine), encoding="ascii", newline="\n")
            written.append(table)
    return written


def history_times(plan: Plan, interval: timedelta) -> list[datetime]:
    """History times expected at the end: [D, F] every ``interval`` from D."""
    times = []
    time = plan.start
    while time <= plan.end:
        times.append(time)
        time += interval
    return times


def history_source(plan: Plan, time: datetime) -> Window:
    """The window whose files remain at ``time`` once every window has run: the window whose
    useful interval ]start, end] holds it, or the first window for D itself."""
    for window in plan.windows:
        if window.useful_start < time <= window.useful_end:
            return window
    if time == plan.start:
        return plan.windows[0]
    raise ValueError(f"{time} is outside the study period")
