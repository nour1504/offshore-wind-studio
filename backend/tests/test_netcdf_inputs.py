"""NetCDF input files (ERA5 from the CDS, OSTIA SST) converted to WPS intermediate files: the
binary records, the fields and derived fields ungrib would write, time interpolation, grid
orientation, the checks before a run and the run itself on a simulated engine."""

import struct
from datetime import datetime, timedelta
from pathlib import Path

import ncmaker
import netCDF4
import numpy as np
import pytest
from helpers import make_client

from owstudio.core.case.model import Case, GribInput, SeaSurface
from owstudio.core.data import examine, intermediate, netcdf
from owstudio.core.data.intermediate import MISSING, LatLonGrid, Slab, file_date

DAY = datetime(2025, 10, 1)
TIMES = [DAY + timedelta(hours=6 * k) for k in range(5)]
LAT = np.arange(65.0, 44.99, -0.25)  # descending, as ERA5 writes them
LON = np.arange(-5.0, 20.01, 0.25)
AREA = (51.0, 60.0, 0.0, 15.6)
MISSING32 = float(np.float32(MISSING))


def by_field(path: Path) -> dict[tuple[str, float], Slab]:
    return {(s.field, s.level): s for s in intermediate.read(path)}


def at(slab: Slab, lat: float, lon: float) -> float:
    g = slab.grid
    row = round((lat - g.start_lat) / g.dlat)
    column = round((lon - g.start_lon) / g.dlon)
    return float(slab.data[row, column])


@pytest.fixture
def era5_files(tmp_path: Path) -> list[Path]:
    folder = tmp_path / "era5-nc"
    folder.mkdir()
    return [
        ncmaker.era5(folder / "pressure.nc", TIMES, LAT, LON, pressure=True),
        ncmaker.era5(folder / "single.nc", TIMES, LAT, LON, pressure=False),
    ]


# ------------------------------------------------------------ intermediate


def test_intermediate_records_are_those_of_wps(tmp_path: Path) -> None:
    grid = LatLonGrid(50.0, -2.0, 0.25, 0.5)
    data = np.arange(12, dtype=float).reshape(3, 4)
    data[0, 0] = np.nan
    slab = Slab(DAY + timedelta(hours=6), "TT", "K", "Temperature", 85000.0, grid, data)
    path = tmp_path / "FILE_2025-10-01_06"
    assert intermediate.write(path, [slab]) == 1
    raw = path.read_bytes()
    # Big-endian Fortran records with 4-byte markers: version 5, then a 156-byte header
    assert raw[:12] == struct.pack(">iii", 4, 5, 4)
    assert struct.unpack(">i", raw[12:16])[0] == 156
    header = raw[16:172]
    assert header[:24] == b"2025-10-01_06:00:00     " and header[60:69] == b"TT       "
    assert struct.unpack(">f", header[140:144])[0] == 85000.0
    assert struct.unpack(">iii", header[144:156]) == (4, 3, 0)
    (back,) = intermediate.read(path)
    assert (back.field, back.units, back.level, back.date) == ("TT", "K", 85000.0, slab.date)
    assert (back.grid.start_lat, back.grid.start_lon, back.grid.dlat, back.grid.dlon) == (
        50.0,
        -2.0,
        0.25,
        0.5,
    )
    assert back.grid.start_location == "SWCORNER" and not back.grid_relative_winds
    assert back.data[0, 0] == MISSING32 and back.data[2, 3] == 11.0
    assert file_date(DAY + timedelta(hours=6), 21600) == "2025-10-01_06"
    assert file_date(DAY + timedelta(hours=6), 1800) == "2025-10-01_06:00"
    assert file_date(DAY + timedelta(hours=6), 90) == "2025-10-01_06:00:00"


# --------------------------------------------------------------- conversion


def test_era5_fields_and_derived_fields_as_ungrib_writes_them(
    tmp_path: Path, era5_files: list[Path]
) -> None:
    out = tmp_path / "converted"
    done = netcdf.convert(era5_files, "FILE", TIMES, 21600, out, AREA)
    assert done.names == [
        "FILE_2025-10-01_00",
        "FILE_2025-10-01_06",
        "FILE_2025-10-01_12",
        "FILE_2025-10-01_18",
        "FILE_2025-10-02_00",
    ]
    assert done.interpolated == [] and done.fields == 5 * 85
    slabs = by_field(out / "FILE_2025-10-01_06")
    t = TIMES[1]
    lat, lon = 55.0, 3.0
    point = (np.array([lat]), np.array([lon]))
    tt = slabs[("TT", 85000.0)]
    assert at(tt, lat, lon) == pytest.approx(ncmaker.value("t", t, *point, 850)[0, 0], abs=1e-3)
    # rrpr.F: HGT = GEOPT / 9.81, SOILHGT = SOILGEO / 9.81, SNOW = water equivalent x 1000
    assert at(slabs[("HGT", 50000.0)], lat, lon) == pytest.approx(
        ncmaker.value("z", t, *point, 500)[0, 0] / 9.81, abs=1e-2
    )
    assert at(slabs[("SOILHGT", 200100.0)], lat, lon) == pytest.approx(
        ncmaker.value("z_surface", t, *point)[0, 0] / 9.81, abs=1e-3
    )
    assert at(slabs[("SNOW", 200100.0)], lat, lon) == pytest.approx(
        ncmaker.value("sd", t, *point)[0, 0] * 1000, rel=1e-6
    )
    # 2 m relative humidity from the dew point (compute_rh_dewpt)
    t2, d2 = ncmaker.value("t2m", t, *point)[0, 0], ncmaker.value("d2m", t, *point)[0, 0]
    expected_rh = np.exp(2.5e6 / 461.5 * (1 / t2 - 1 / d2)) * 100
    assert at(slabs[("RH", 200100.0)], lat, lon) == pytest.approx(expected_rh, rel=1e-5)
    assert ("DEWPT", 200100.0) not in slabs  # read to derive RH only, as with Vtable.ECMWF
    # The ECMWF land-sea mask becomes a 0/1 flag; SST is missing over land
    assert (
        at(slabs[("LANDSEA", 200100.0)], lat, 10.0) == 1.0
        and at(slabs[("LANDSEA", 200100.0)], lat, lon) == 0.0
    )
    assert (
        at(slabs[("SST", 200100.0)], lat, 10.0) == MISSING32
        and at(slabs[("SST", 200100.0)], lat, lon) > 200
    )
    assert (
        ("PMSL", 201300.0) in slabs
        and ("ST000007", 200100.0) in slabs
        and ("SM100289", 200100.0) in slabs
    )
    # Every pressure level from 1000 to 1 hPa, in Pa
    assert sorted(level for name, level in slabs if name == "UU" and level < 200000) == sorted(
        p * 100.0 for p in ncmaker.LEVELS_HPA
    )
    # Rows south to north, columns eastwards, limited to the area with a margin
    grid = tt.grid
    assert grid.dlat == 0.25 and grid.dlon == 0.25 and grid.start_lat == pytest.approx(49.5)
    assert tt.data.shape[0] < len(LAT) and tt.data.shape[1] < len(LON) and grid.start_lon <= -1.0


def test_times_between_available_ones_are_interpolated(
    tmp_path: Path, era5_files: list[Path]
) -> None:
    three_hourly = [DAY + timedelta(hours=3 * k) for k in range(9)]
    done = netcdf.convert(era5_files, "FILE", three_hourly, 10800, tmp_path / "out", AREA)
    assert len(done.names) == 9 and done.interpolated == three_hourly[1::2]
    slab = by_field(tmp_path / "out" / "FILE_2025-10-01_03")[("TT", 85000.0)]
    point = (np.array([52.0]), np.array([3.75]))
    before, after = (ncmaker.value("t", t, *point, 850)[0, 0] for t in (TIMES[0], TIMES[1]))
    assert at(slab, 52.0, 3.75) == pytest.approx((before + after) / 2, abs=1e-3)


def test_conversion_is_kept_until_the_files_change(tmp_path: Path, era5_files: list[Path]) -> None:
    out = tmp_path / "out"
    netcdf.convert(era5_files, "FILE", TIMES, 21600, out, AREA)
    first = (out / "FILE_2025-10-01_00").stat().st_mtime_ns
    netcdf.convert(era5_files, "FILE", TIMES, 21600, out, AREA)
    assert (out / "FILE_2025-10-01_00").stat().st_mtime_ns == first
    assert netcdf.conversion_key(era5_files, "FILE", TIMES, AREA) != netcdf.conversion_key(
        era5_files, "FILE", TIMES[:-1], AREA
    )


def test_legacy_cds_files_packed_with_expver(tmp_path: Path) -> None:
    path = ncmaker.era5_legacy(tmp_path / "legacy.nc", TIMES, LAT, LON)
    the_plan = netcdf.plan([path])
    assert the_plan.levels(("TT", "pressure")) == [
        100000.0,
        85000.0,
        50000.0,
        10000.0,
        1000.0,
        100.0,
    ]
    out = tmp_path / "out"
    netcdf.convert([path], "FILE", TIMES, 21600, out, AREA)
    point = (np.array([58.0]), np.array([12.5]))
    for time in (TIMES[0], TIMES[-1]):  # the last time comes from ERA5T (expver 5)
        slab = by_field(out / f"FILE_{file_date(time, 21600)}")[("TT", 50000.0)]
        assert at(slab, 58.0, 12.5) == pytest.approx(
            ncmaker.value("t", time, *point, 500)[0, 0], abs=2e-3
        )


def test_ostia_sst_interpolated_to_the_boundary_times(tmp_path: Path) -> None:
    noon = [datetime(2025, 9, 30, 12), datetime(2025, 10, 1, 12), datetime(2025, 10, 2, 12)]
    lat, lon = np.arange(45.0, 65.01, 0.05), np.arange(-5.0, 20.01, 0.05)
    path = ncmaker.ostia(tmp_path / "ostia.nc", noon, lat, lon)
    the_plan = netcdf.plan([path], "sst")
    assert list(the_plan.fields) == [("SST", "surface")] and "mask" in the_plan.ignored
    out = tmp_path / "out"
    done = netcdf.convert([path], "SST", TIMES, 21600, out, AREA)
    assert done.names[0] == "SST_2025-10-01_00" and done.interpolated == [
        t for t in TIMES if t.hour != 12
    ]
    slabs = list(intermediate.read(out / "SST_2025-10-01_00"))
    assert [s.field for s in slabs] == ["SST"]
    point = (np.array([55.0]), np.array([3.0]))
    expected = (
        ncmaker.value("sst", noon[0], *point)[0, 0] + ncmaker.value("sst", noon[1], *point)[0, 0]
    ) / 2
    assert at(slabs[0], 55.0, 3.0) == pytest.approx(expected, abs=0.011)
    assert at(slabs[0], 55.0, 10.0) == MISSING32
    assert slabs[0].data.shape[1] < len(lon)  # limited to the domain and a margin


def test_global_grid_stays_continuous_across_greenwich(tmp_path: Path) -> None:
    path = tmp_path / "global.nc"
    lat, lon = np.arange(-90.0, 90.01, 2.0), np.arange(0.0, 359.9, 2.0)
    with netCDF4.Dataset(path, "w") as dataset:
        for name, values in (("latitude", lat), ("longitude", lon)):
            dataset.createDimension(name, len(values))
            dataset.createVariable(name, "f8", (name,))[:] = values
        dataset.createDimension("time", 1)
        time = dataset.createVariable("time", "f8", ("time",))
        time.units = "hours since 2025-10-01 00:00:00"
        time[:] = [0.0]
        sst = dataset.createVariable("sst", "f4", ("time", "latitude", "longitude"))
        sst.units = "K"
        sst[0] = np.broadcast_to(270.0 + np.mod(lon, 360.0) / 10.0, (len(lat), len(lon)))
    found = netcdf.layout(lat, lon, (51.0, 60.0, -3.0, 12.0))
    assert found.grid.start_lon < -3.0 and found.grid.start_lon + (found.shape[1] - 1) * 2.0 > 12.0
    lons = found.grid.start_lon + 2.0 * np.arange(found.shape[1])
    assert np.allclose(np.mod(lon[found.columns], 360.0), np.mod(lons, 360.0))
    out = tmp_path / "out"
    netcdf.convert([path], "SST", [DAY], 21600, out, (51.0, 60.0, -3.0, 12.0))
    (slab,) = intermediate.read(out / "SST_2025-10-01_00")
    assert at(slab, 54.0, -2.0) == pytest.approx(270.0 + 358.0 / 10.0)
    assert at(slab, 54.0, 2.0) == pytest.approx(270.2)


def test_levels_split_across_files_are_read_from_the_right_file(tmp_path: Path) -> None:
    def pressure_file(path: Path, levels: tuple[int, ...]) -> Path:
        with netCDF4.Dataset(path, "w") as dataset:
            for name, values in (
                ("latitude", LAT),
                ("longitude", LON),
                ("pressure_level", np.array(levels, float)),
            ):
                dataset.createDimension(name, len(values))
                dataset.createVariable(name, "f8", (name,))[:] = values
            dataset.variables["pressure_level"].units = "hPa"
            dataset.createDimension("valid_time", 1)
            time = dataset.createVariable("valid_time", "i8", ("valid_time",))
            time.units = "seconds since 1970-01-01"
            time[:] = [int(ncmaker.hours(DAY) * 3600)]
            for name in ("t", "r", "q"):
                variable = dataset.createVariable(
                    name, "f4", ("valid_time", "pressure_level", "latitude", "longitude")
                )
                variable.units = ncmaker.UNITS[name]
                for k, level in enumerate(levels):
                    variable[0, k] = ncmaker.value(name, DAY, LAT, LON, level)
        return path

    files = [
        pressure_file(tmp_path / "low.nc", (1000, 850, 700)),
        pressure_file(tmp_path / "high.nc", (500, 300)),
    ]
    the_plan = netcdf.plan(files)
    assert the_plan.levels(("TT", "pressure")) == [100000.0, 85000.0, 70000.0, 50000.0, 30000.0]
    assert (
        "SPECHUMD",
        "pressure",
    ) not in the_plan.fields  # RH is there: Vtable.ECMWF reads RH only
    netcdf.convert(files, "FILE", [DAY], 21600, tmp_path / "out", AREA)
    slab = by_field(tmp_path / "out" / "FILE_2025-10-01_00")[("TT", 30000.0)]
    point = (np.array([56.0]), np.array([5.0]))
    assert at(slab, 56.0, 5.0) == pytest.approx(
        ncmaker.value("t", DAY, *point, 300)[0, 0], abs=1e-3
    )


# ---------------------------------------------------------- examination


def own(folder: Path) -> GribInput:
    return GribInput(folder=str(folder), pattern="*.nc", vtable="Vtable.GFS")


def context() -> examine.Context:
    return examine.Context(DAY, DAY + timedelta(days=1), 21600, examine.Box(*AREA))


def test_examination_of_netcdf_folders(tmp_path: Path, era5_files: list[Path]) -> None:
    report = examine.examine(own(era5_files[0].parent), "atmosphere", context())
    assert report.format == "netcdf" and not report.errors
    assert [f.severity for f in report.findings] == [
        "info"
    ] and "converted on this computer at export" in report.findings[0].message
    assert (
        report.centres == ["ECMWF"]
        and len(report.pressure_levels_hpa) == 13
        and len(report.soil_fields) == 8
    )
    short = tmp_path / "short"
    short.mkdir()
    ncmaker.era5(short / "pressure.nc", TIMES[:-1], LAT, LON, pressure=True)
    ncmaker.era5(short / "single.nc", TIMES[:-1], LAT, LON, pressure=False)
    late = examine.examine(own(short), "atmosphere", context())
    assert any("no data before or after 2025-10-02 00:00" in e for e in late.errors)
    unknown = tmp_path / "unknown"
    unknown.mkdir()
    with netCDF4.Dataset(unknown / "other.nc", "w") as dataset:
        for name in ("latitude", "longitude", "time"):
            dataset.createDimension(name, 2)
            dataset.createVariable(name, "f8", (name,))[:] = [0.0, 1.0]
        dataset.variables["time"].units = "hours since 2025-10-01"
        dataset.createVariable("foo", "f4", ("time", "latitude", "longitude"))[:] = 1.0
    nothing = examine.examine(own(unknown), "atmosphere", context())
    assert any(
        "no variable of the NetCDF files is known" in e and "foo" in e for e in nothing.errors
    )


def test_mixed_folders_are_refused(tmp_path: Path, era5_files: list[Path]) -> None:
    import gribmaker

    folder = era5_files[0].parent
    gribmaker.era5_folder(folder, TIMES[:1])
    report = examine.examine(
        GribInput(folder=str(folder), vtable="Vtable.ECMWF"), "atmosphere", context()
    )
    assert any("mix NetCDF" in e for e in report.errors)


# ------------------------------------------------------------------- runs


def netcdf_case(reference_case: Case, era5_folder: Path, sst_folder: Path | None = None) -> Case:
    case = reference_case.model_copy(deep=True)
    # The files cover the period of the fixture; the useful period starts after the spin-up
    case.period.start += timedelta(hours=case.spin_up_hours)
    case.input_source = "grib"
    case.grib = own(era5_folder)
    if sst_folder is not None:
        case.sea_surface = SeaSurface(
            source="grib", grib=GribInput(folder=str(sst_folder), pattern="*.nc")
        )
    return case


def test_api_examines_netcdf_cases(
    tmp_path: Path, reference_case: Case, era5_files: list[Path]
) -> None:
    client = make_client(tmp_path)
    body = netcdf_case(reference_case, era5_files[0].parent).model_dump(mode="json")
    result = client.post("/api/data/examine", json={"case": body}).json()
    assert result["format"] == "netcdf" and result["errors"] == [] and result["fields"]
