"""Own GRIB files (for example ERA5 downloaded by the user) and a separate SST product: from the
folder on this computer to ungrib, metgrid and the SST update, without any download."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import gribmaker
import pytest
from helpers import make_client

from owstudio.core.case.checks import check_case
from owstudio.core.case.model import Case, GribInput, SeaSurface
from owstudio.core.data import userfiles, vtables


def grib_file(path: Path, edition: int = 1, size: int = 64) -> Path:
    """Starts like a GRIB message of the given edition (ungrib is not run in the tests)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GRIB" + bytes([0, 0, 0, edition]) + b"\0" * (size - 8))
    return path


# The reference case: 2025-10-01 00:00 to 2025-10-02 00:00, boundary data every 6 h
PERIOD_TIMES = [datetime(2025, 10, 1) + timedelta(hours=6 * k) for k in range(5)]


@pytest.fixture
def era5_folder(tmp_path: Path) -> Path:
    """ERA5-like GRIB1 files (synthetic headers) covering the reference case."""
    folder = gribmaker.era5_folder(tmp_path / "my ERA5", PERIOD_TIMES)
    (folder / "notes.txt").write_text("downloaded from the CDS", encoding="utf-8")
    return folder


@pytest.fixture
def sst_folder(tmp_path: Path) -> Path:
    """Daily SST analyses (synthetic GRIB2) on 30 September and 2 October."""
    return gribmaker.sst_folder(tmp_path / "ostia", [datetime(2025, 9, 30), datetime(2025, 10, 2)])


def own_case(
    reference_case: Case, era5_folder: Path, sst_folder: Path | None = None, **sea: object
) -> Case:
    case = reference_case.model_copy(deep=True)
    # The files cover the period of the fixture; the useful period starts after the spin-up
    case.period.start += timedelta(hours=case.spin_up_hours)
    case.input_source = "grib"
    case.grib = GribInput(folder=str(era5_folder), pattern="era5-*", vtable="Vtable.ECMWF")
    if sst_folder is not None:
        case.sea_surface = SeaSurface(
            source="grib",
            grib=GribInput(folder=str(sst_folder), pattern="*.grb2", vtable="Vtable.SST"),
            **sea,
        )  # type: ignore[arg-type]
    return case


def test_formats_are_detected(tmp_path: Path) -> None:
    assert userfiles.sniff(grib_file(tmp_path / "a", 1)) == "grib1"
    assert userfiles.sniff(grib_file(tmp_path / "b", 2)) == "grib2"
    (tmp_path / "c.nc").write_bytes(b"\x89HDF\r\n\x1a\n")
    (tmp_path / "d.nc").write_bytes(b"CDF\x01")
    assert userfiles.sniff(tmp_path / "c.nc") == userfiles.sniff(tmp_path / "d.nc") == "netcdf"
    files = userfiles.list_files(str(tmp_path), "*.NC")  # case-insensitive pattern
    assert [f.name for f in files] == ["c.nc", "d.nc"]
    # NetCDF folders are converted before the run; a folder mixing both kinds is refused
    assert userfiles.all_netcdf(files) and userfiles.problems(files, "Input files") == []
    mixed = userfiles.list_files(str(tmp_path))
    assert "mix NetCDF" in userfiles.problems(mixed, "Input files")[0]


def test_standard_vtables_are_bundled() -> None:
    assert {"Vtable.GFS", "Vtable.ECMWF", "Vtable.SST"} <= set(vtables.names())
    ecmwf = vtables.fields(vtables.read("Vtable.ECMWF"))
    assert {"TT", "UU", "VV", "SST", "PSFC"} <= set(ecmwf)
    assert vtables.fields(vtables.read("Vtable.SST")) == ["SST"]
    assert vtables.validate(vtables.read("Vtable.ECMWF")) == []
    assert vtables.validate("SST | 1 | 0")  # no header, no separators


# ----------------------------------------------------------------- case files


def test_checks_of_own_files(
    reference_case: Case, era5_folder: Path, sst_folder: Path, tmp_path: Path
) -> None:
    case = own_case(reference_case, era5_folder, sst_folder)
    assert not [i for i in check_case(case) if i.severity == "error"]
    assert case.grib is not None
    case.grib.folder = str(tmp_path / "nowhere")
    assert any("folder not found" in i.message for i in check_case(case))
    netcdf = tmp_path / "netcdf"
    netcdf.mkdir()
    (netcdf / "era5.nc").write_bytes(b"\x89HDF\r\n\x1a\n")
    case.grib = GribInput(folder=str(netcdf), vtable="Vtable.ECMWF")
    assert any("NetCDF" in i.message and i.severity == "error" for i in check_case(case))
    case.grib = GribInput(folder=str(era5_folder), pattern="era5-*", vtable="Vtable.NOPE")
    assert any("unknown Vtable" in i.message for i in check_case(case))


def test_sst_checks(reference_case: Case, era5_folder: Path, sst_folder: Path) -> None:
    case = own_case(reference_case, era5_folder, sst_folder)
    assert case.sea_surface.grib is not None
    case.sea_surface.grib.vtable = "Vtable.GFS"  # no SST row
    assert any("does not produce the field SST" in i.message for i in check_case(case))
    long = reference_case.model_copy(deep=True)
    long.period.end = long.period.start.replace(day=20)
    # Each window is its own simulation: 72 useful hours after 12 h of spin-up stay short
    assert not any("without SST update" in i.message for i in check_case(long))
    long.windows.useful_hours = 240
    assert any("without SST update" in i.message for i in check_case(long))
    long.sea_surface = SeaSurface(update=True, update_interval_minutes=60)
    messages = [i.message for i in check_case(long)]
    assert not any("without SST update" in m for m in messages)
    assert any("intervals should match" in m for m in messages) and any(
        "usemonalb" in m for m in messages
    )


# -------------------------------------------------------------------- API


def test_data_api_lists_files_and_tables(tmp_path: Path, era5_folder: Path) -> None:
    client = make_client(tmp_path)
    listing = client.get(
        "/api/data/files", params={"folder": str(era5_folder), "pattern": "era5-*"}
    ).json()
    assert (
        listing["count"] == 4 and listing["formats"] == {"grib1": 4} and listing["problems"] == []
    )
    assert client.get("/api/data/files", params={"folder": str(tmp_path / "x")}).status_code == 404
    tables = client.get("/api/data/vtables").json()
    assert tables[0]["recommended"] and any(t["name"] == "Vtable.SST" for t in tables)
    assert client.get("/api/data/vtables/Vtable.SST").text.startswith("GRIB1|")
    checked = client.post(
        "/api/data/vtables/validate", json={"text": vtables.read("Vtable.SST")}
    ).json()
    assert checked == {"problems": [], "fields": ["SST"]}


def test_a_project_without_its_files_folder_yet_stays_valid_but_cannot_run(
    reference: dict, tmp_path: Path
) -> None:
    """Found on the Domains page: choosing own files left an empty folder, the whole project
    was refused and the map showed a validation error."""
    reference["input_source"] = "grib"
    reference["grib"] = {"folder": "", "vtable": "Vtable.ECMWF"}
    reference["sea_surface"] = {"source": "grib", "grib": {"folder": "", "vtable": "Vtable.SST"}}
    case = Case.model_validate(reference)
    messages = [i.message for i in check_case(case) if i.severity == "error"]
    assert any("folder of your weather files" in m for m in messages)
    assert any("folder of your sea temperature files" in m for m in messages)
    client = make_client(tmp_path)
    assert client.post("/api/geometry", json=reference).status_code == 200


def test_files_in_subfolders_are_found_and_summed_up_by_folder(tmp_path: Path) -> None:
    """Data kept by year (gfs/2025/...) are found below the chosen folder; hidden folders are
    not; the tree names the folders with their counts."""
    root = tmp_path / "gfs"
    for hour in ("2025093018", "2025100100", "2025100106"):
        grib_file(root / "2025" / f"gfs.{hour}.f000.grib2", edition=2)
    grib_file(root / "gfs.2024123118.f000.grib2", edition=2)
    grib_file(root / ".cache" / "gfs.hidden.grib2", edition=2)
    files = userfiles.list_files(str(root), "gfs.*.grib2")
    assert [f.name for f in files] == [
        "2025/gfs.2025093018.f000.grib2",
        "2025/gfs.2025100100.f000.grib2",
        "2025/gfs.2025100106.f000.grib2",
        "gfs.2024123118.f000.grib2",
    ]
    assert [f.name for f in userfiles.list_files(str(root), "2025/*")] == [
        f.name for f in files[:3]
    ]
    listing = make_client(tmp_path).get("/api/data/files", params={"folder": str(root)}).json()
    assert listing["count"] == 4 and listing["total_bytes"] == 4 * 64
    folders = {f["path"]: f for f in listing["tree"]["folders"]}
    assert folders["2025"]["files"] == 3 and folders["2025"]["first"] == "gfs.2025093018.f000.grib2"
    assert folders[""]["names"] == ["gfs.2024123118.f000.grib2"]


def test_a_long_folder_is_summed_up_by_its_first_and_last_file(tmp_path: Path) -> None:
    from owstudio.core.data import found

    files = [(tmp_path / "era5" / f"era5-{day:02d}.grib", 10) for day in range(1, 31)]
    summary = found.tree(files, tmp_path)
    (folder,) = summary["folders"]
    assert folder["path"] == "era5" and folder["files"] == 30 and folder["bytes"] == 300
    assert folder["names"] == [] and (folder["first"], folder["last"]) == (
        "era5-01.grib",
        "era5-30.grib",
    )


@pytest.mark.skipif(sys.platform == "win32", reason="the exported scripts run under Linux")
def test_the_scripts_find_the_files_of_subfolders_sorted_by_name(tmp_path: Path) -> None:
    """The exported WPS script links the same files as the interface lists, in time order."""
    import re
    import subprocess

    from owstudio.core.method import scripts_text

    for language, name in (("fr", "fichiers_source"), ("en", "source_files")):
        function = re.search(
            rf"{name}\(\)\n\{{.*?\n\}}", scripts_text.WPS_FUNCTIONS[language], re.DOTALL
        )
        assert function is not None
        root = tmp_path / language / "own files"
        grib_file(root / "b" / "era5-2025100106.grib")
        grib_file(root / "a" / "era5-2025100100.grib")
        grib_file(root / "era5-2025100112.grib")
        grib_file(root / ".old" / "era5-2025100100.grib")
        done = subprocess.run(
            ["bash", "-c", f'{function.group(0)}\n{name} "$1/era5-*" 2025 2025', "_", str(root)],
            capture_output=True,
            text=True,
            check=True,
        )
        assert done.stdout.splitlines() == [
            f"{root}/a/era5-2025100100.grib",
            f"{root}/b/era5-2025100106.grib",
            f"{root}/era5-2025100112.grib",
        ]


def test_found_files_on_several_drives_keep_their_whole_paths(tmp_path: Path, monkeypatch) -> None:
    """Windows has no common folder for C: and D: (commonpath and relpath raise ValueError): the
    tree keeps whole paths instead of failing."""
    import os

    from owstudio.core.data import found

    def several_drives(*args: object) -> str:
        raise ValueError("Paths don't have the same drive")

    monkeypatch.setattr(os.path, "commonpath", several_drives)
    summary = found.tree([(tmp_path / "a" / "x.nc", 1), (tmp_path / "b" / "y.nc", 2)])
    assert summary["root"] == "" and summary["files"] == 2
    assert {f["path"] for f in summary["folders"]} == {
        (tmp_path / "a").as_posix(),
        (tmp_path / "b").as_posix(),
    }


def test_too_many_files_are_said_instead_of_cut(tmp_path: Path, monkeypatch) -> None:
    """Above the limit the listing stops with the reason, instead of silently leaving files out
    (counts and sizes would be wrong while the scripts take every file)."""
    monkeypatch.setattr(userfiles, "MAX_FILES", 3)
    for hour in range(5):
        grib_file(tmp_path / "gfs" / f"gfs.{hour:03d}.grib2", edition=2)
    with pytest.raises(userfiles.TooManyFiles, match="3"):
        userfiles.list_files(str(tmp_path / "gfs"))
    assert len(userfiles.list_files(str(tmp_path / "gfs"), "gfs.00[0-2]*")) == 3
    listing = make_client(tmp_path).get("/api/data/files", params={"folder": str(tmp_path / "gfs")})
    assert listing.status_code == 422


def test_a_file_name_in_several_folders_is_pointed_out(tmp_path: Path) -> None:
    """A backup copy in a subfolder would be read twice by ungrib: a warning names it."""
    grib_file(tmp_path / "era5" / "era5-01.grib")
    grib_file(tmp_path / "era5" / "old" / "era5-01.grib")
    files = userfiles.list_files(str(tmp_path / "era5"))
    (warning,) = userfiles.repeated_names(files, "Files")
    assert "era5-01.grib" in warning and "old/era5-01.grib" in warning
    assert userfiles.repeated_names(files[:1], "Files") == []
