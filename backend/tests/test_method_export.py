"""The exported files and scripts (core/method/export.py, scripts.py), run end to end.

WPS and WRF are replaced by small programs that behave like them where the method depends on it:
wrf.exe writes its time series after each step at n x dt from the simulation start (WRF 4.8
share/wrf_timeseries.F), steps until the end time is reached, recreates the time series files at
each run, writes one history file per output time named like WRF with the simulation start in
START_DATE, and SUCCESS COMPLETE in rsl.error.0000. With restart = .true. it starts from the
wrfrst of its start time, writes no history at that time, and a wrfrst every restart_interval;
CUMULATIVE=1 makes its time series and START_DATE count from the very first start instead.
No WRF, WPS, network or engine is used.
Every test runs in French and in English: the scripts of both languages must do the same.
"""

import itertools
import json
import os
import shutil
import subprocess
import zipfile
from collections.abc import Iterator
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

import pytest
from helpers import history_source, history_times

from owstudio.core import i18n
from owstudio.core.case.model import Case, GribInput, TimeSeries, TimeSeriesPoint, Windows
from owstudio.core.method import plan as method
from owstudio.core.method import timesteps
from owstudio.core.method.export import ExportOptions, export_files, export_zip, write_folder
from owstudio.core.method.scripts import names


@pytest.fixture(autouse=True, params=["fr", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    """The export in each language of the interface."""
    with i18n.using(request.param):
        yield request.param


def launcher_variable() -> str:
    return "LANCEUR" if i18n.current() == "fr" else "LAUNCHER"


def find_bash() -> str | None:
    """A real bash: /bin/bash on Linux, Git's bash on Windows (never the WSL launcher of
    System32, which would run in a Linux distribution)."""
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    candidates = []
    if git:
        root = Path(git).resolve().parent.parent
        candidates += [root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"]
    candidates.append(Path("C:/Program Files/Git/bin/bash.exe"))
    for candidate in candidates:
        if candidate.is_file() and "system32" not in str(candidate).lower():
            return str(candidate)
    return None


BASH = find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="bash is not available")


def posix(path: Path) -> str:
    """The path as bash sees it (/c/... with Git's bash on Windows)."""
    if os.name == "nt":
        text = path.resolve().as_posix()
        return f"/{text[0].lower()}{text[2:]}"
    return str(path.resolve())


def write_program(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("ascii"))
    path.chmod(0o755)


FAKE_MPIRUN = """#!/bin/bash
[ "$1" = "-np" ] && shift 2
exec "$@"
"""

FAKE_NCDUMP = """#!/bin/bash
[ "$1" = "-h" ] && shift
cat "$1"
"""

# Reads one value of a namelist option (first value of a list)
NAMELIST_VALUE = r"""
valeur()
{
	grep -iE "^[[:space:]]*$1[[:space:]]*=" "$2" | head -n 1 | sed -E "s/^[^=]*=[[:space:]]*//; s/[,[:space:]].*$//; s/'//g"
}
"""

FAKE_GEOGRID = """#!/bin/bash
echo '!  Successful completion of geogrid.        !'
"""

FAKE_UNGRIB = (
    """#!/bin/bash
"""
    + NAMELIST_VALUE
    + r"""
[ -e GRIBFILE.AAA ] || { echo "no GRIBFILE"; exit 1; }
[ -e Vtable ] || { echo "no Vtable"; exit 1; }
n=$(ls GRIBFILE.??? | wc -l)
echo "ungrib $(valeur prefix namelist.wps) $(valeur start_date namelist.wps) $(valeur end_date namelist.wps) $(head -n 1 Vtable) $n" >> ../calls.log
# One intermediate file per data time, as ungrib writes them (none with OWS_UNGRIB_WRITES=0)
debut=$(valeur start_date namelist.wps)
fin=$(valeur end_date namelist.wps)
t=$(date -u -d "${debut/_/ }" +%s)
f=$(date -u -d "${fin/_/ }" +%s)
while (( ${OWS_UNGRIB_WRITES:-1} && t <= f )); do
	: > "$(valeur prefix namelist.wps):$(date -u -d "@$t" +%Y-%m-%d_%H)"
	(( t += $(valeur interval_seconds namelist.wps) ))
done
echo '!  Successful completion of ungrib.   !'
"""
)

FAKE_METGRID = (
    """#!/bin/bash
"""
    + NAMELIST_VALUE
    + r"""
debut=$(valeur start_date namelist.wps)
fin=$(valeur end_date namelist.wps)
pas=$(valeur interval_seconds namelist.wps)
dossier=$(valeur opt_output_from_metgrid_path namelist.wps)
domaines=$(valeur max_dom namelist.wps)
noms=$(grep -iE "^[[:space:]]*fg_name" namelist.wps | sed -E "s/^[^=]*=[[:space:]]*//")
echo "metgrid $debut $fin $noms" >> ../calls.log
t=$(date -u -d "${debut/_/ }" +%s)
f=$(date -u -d "${fin/_/ }" +%s)
mkdir -p "$dossier"
while (( t <= f )); do
	for (( d = 1; d <= domaines; d++ )); do
		nom="${dossier}met_em.d0${d}.$(date -u -d "@$t" '+%Y-%m-%d_%H:%M:%S').nc"
		printf 'num_metgrid_levels = 38 ;\n\t\t:NUM_METGRID_SOIL_LEVELS = 4 ;\n' > "$nom"
	done
	(( t += pas ))
done
echo '!  Successful completion of metgrid.  !'
"""
)

FAKE_REAL = (
    """#!/bin/bash
"""
    + NAMELIST_VALUE
    + r"""
[ "$(valeur num_metgrid_levels namelist.input)" = 38 ] || { echo "levels" > rsl.error.0000; exit 1; }
debut=$(printf '%04d-%02d-%02d %02d:%02d:%02d' "$(valeur start_year namelist.input)" "$(valeur start_month namelist.input)" "$(valeur start_day namelist.input)" "$(valeur start_hour namelist.input)" "$(valeur start_minute namelist.input)" "$(valeur start_second namelist.input)")
ls met_em.d01."${debut/ /_}".nc > /dev/null || { echo "no met_em at $debut" > rsl.error.0000; exit 1; }
echo "real_em: SUCCESS COMPLETE REAL_EM INIT" > rsl.error.0000
"""
)

FAKE_WRF = (
    """#!/bin/bash
"""
    + NAMELIST_VALUE
    + r"""
nl=namelist.input
date_de()
{
	printf '%04d-%02d-%02d %02d:%02d:%02d' "$(valeur "${1}_year" $nl)" "$(valeur "${1}_month" $nl)" "$(valeur "${1}_day" $nl)" "$(valeur "${1}_hour" $nl)" "$(valeur "${1}_minute" $nl)" "$(valeur "${1}_second" $nl)"
}
debut=$(date_de start)
fin=$(date_de end)
t0=$(date -u -d "$debut" +%s)
t1=$(date -u -d "$fin" +%s)
duree=$(( $(valeur run_hours $nl) * 3600 + $(valeur run_minutes $nl) * 60 + $(valeur run_seconds $nl) + $(valeur run_days $nl) * 86400 ))
(( duree == t1 - t0 )) || { echo "run_* ($duree) and end_* ($((t1 - t0))) disagree" > rsl.error.0000; exit 1; }
origine="${debut/ /_}"
decalage=0
premier=$t0
if [ "$(valeur restart $nl)" = ".true." ]; then
	[ -f "wrfrst_d01_${debut/ /_}" ] || { echo "no wrfrst at $debut" > rsl.error.0000; exit 1; }
	if [ "${CUMULATIVE:-0}" = 1 ]; then
		origine=$(cat "wrfrst_d01_${debut/ /_}")
		decalage=$(( t0 - $(date -u -d "${origine/_/ }" +%s) ))
	fi
	premier=$(( t0 + $(valeur history_interval $nl) * 60 ))
fi
if [ -n "${ECHEC_A:-}" ] && [ "${debut/ /_}" = "$ECHEC_A" ]; then
	echo "simulated crash" > rsl.error.0000
	exit 1
fi
echo "wrf ${debut/ /_} ${fin/ /_}" >> calls.log
pas=$(valeur time_step $nl)
historique=$(valeur history_interval $nl)
domaines=$(valeur max_dom $nl)
ratios=$(grep -iE "^[[:space:]]*parent_time_step_ratio" $nl | sed -E "s/^[^=]*=//; s/,/ /g")
read -r -a ratio <<< "$ratios"
# History: one file per output time, START_DATE = simulation start
for (( d = 1; d <= domaines; d++ )); do
	for (( t = premier; t <= t1; t += historique * 60 )); do
		nom="wrfout_d0${d}_$(date -u -d "@$t" '+%Y-%m-%d_%H:%M:%S')"
		printf '\t\t:START_DATE = "%s" ;\n' "$origine" > "$nom"
	done
done
# Restart files every restart_interval from the start of this run
reprise=$(valeur restart_interval $nl)
for (( t = t0 + reprise * 60; t <= t1; t += reprise * 60 )); do
	for (( d = 1; d <= domaines; d++ )); do
		echo "$origine" > "wrfrst_d0${d}_$(date -u -d "@$t" '+%Y-%m-%d_%H:%M:%S')"
	done
done
# Time series: recreated, then one line per step at n x dt, until the end time is reached
tail -n +4 tslist | while IFS= read -r ligne; do
	prefixe=$(echo "${ligne:26:5}" | tr -d ' ')
	dt_num=$pas
	dt_den=1
	for (( d = 1; d <= domaines; d++ )); do
		(( d > 1 )) && dt_den=$(( dt_den * ${ratio[d-1]} ))
		base="${prefixe}.d0${d}"
		entete=$(printf '%-26s%2d%3d %-5s (%7.3f,%8.3f) (%4d,%4d) (%7.3f,%8.3f) %6.1f meters  %s' "Mat" "$d" 1 "$prefixe" 55.5 7.8 10 10 55.5 7.8 0.0 "${debut/ /_}")
		for v in TS UU VV; do echo "$entete" > "${base}.${v}"; done
		awk -v num="$dt_num" -v den="$dt_den" -v duree="$duree" -v d="$d" -v base="$base" -v off="$decalage" 'BEGIN {
			for (n = 1; n * num / den < duree + num / den; n++) {
				h = (off + n * num / den) / 3600
				printf "%2d%13.6f%5d%5d%5d %13.5f %13.5f\n", d, h, 1, 10, 10, n, 8.0 >> (base ".TS")
				printf "%13.6f %13.5f %13.5f\n", h, n, 7.0 >> (base ".UU")
				printf "%13.6f %13.5f %13.5f\n", h, n, 1.0 >> (base ".VV")
			}
		}'
	done
done
echo "wrf: SUCCESS COMPLETE WRF" > rsl.error.0000
"""
)


def fake_geography(root: Path) -> Path:
    """A geography as the NCAR archive unpacks it (WPS_GEOG/topo_gmted2010_30s/index...)."""
    for dataset in ("topo_gmted2010_30s", "topo_gmted2010_5m"):
        write_program(root / dataset / "index", "type=continuous\n")
    return root


def fake_engine(root: Path) -> tuple[Path, Path, Path]:
    """Fake WRF and WPS installations, a geography in geog/WPS_GEOG (the options give geog/, the
    folder above it, as on the work VM) and a folder of fake mpirun and ncdump."""
    wrf, wps, tools = root / "WRF", root / "WPS", root / "outils"
    fake_geography(root / "geog" / "WPS_GEOG")
    write_program(wrf / "main" / "real.exe", FAKE_REAL)
    write_program(wrf / "main" / "wrf.exe", FAKE_WRF)
    write_program(wrf / "run" / "LANDUSE.TBL", "table\n")
    write_program(wrf / "run" / "wind-turbine-1.tbl", "built-in\n")
    write_program(wps / "geogrid.exe", FAKE_GEOGRID)
    write_program(wps / "ungrib.exe", FAKE_UNGRIB)
    write_program(wps / "metgrid.exe", FAKE_METGRID)
    write_program(wps / "geogrid" / "GEOGRID.TBL", "table\n")
    write_program(wps / "metgrid" / "METGRID.TBL", "table\n")
    write_program(tools / "mpirun", FAKE_MPIRUN)
    write_program(tools / "ncdump", FAKE_NCDUMP)
    return wrf, wps, tools


def run(script: str, folder: Path, tools: Path, **env: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    environment = {**os.environ, **env}
    command = f'export PATH="{posix(tools)}:$PATH"; bash {script}'
    return subprocess.run(
        [BASH, "-c", command],
        cwd=folder,
        env=environment,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )


def study_case(reference_case: Case, time_step: int | None = None) -> Case:
    """Across the end of February and the start of March 2024 (leap year): two month blocks,
    the March block starting with a window as short as the spin-up."""
    case = reference_case.model_copy(deep=True)
    case.period.start = datetime(2024, 2, 27)
    case.period.end = datetime(2024, 3, 3)
    case.spin_up_hours = 12
    case.windows = Windows(useful_hours=36, grouping="month")
    turbine = case.farms[0].turbines[0]
    case.time_series = TimeSeries(
        turbines="none",
        points=[TimeSeriesPoint(name="Mat", prefix="MAT", lat=turbine.lat, lon=turbine.lon)],
    )
    if time_step is not None:
        case.namelist_input = {"domains": {"time_step": time_step}}
    return case


def options(wrf: Path, wps: Path, target: str = "local") -> ExportOptions:
    return ExportOptions(
        target=target,  # type: ignore[arg-type]
        cores=2,
        wps_cores=1,
        wrf_dir=posix(wrf),
        wps_dir=posix(wps),
        geog_dir=posix(wrf.parent / "geog"),
    )


# Git's bash on Windows stores ":" of file names as U+F03A; Linux keeps them
COLON = ""


def utc(text: str) -> datetime:
    return datetime.strptime(text.replace(COLON, ":"), "%Y-%m-%d_%H:%M:%S")


def disk_name(name: str) -> str:
    """A file name as bash writes it."""
    return name.replace(":", COLON) if os.name == "nt" else name


@needs_bash
def test_a_geography_path_too_long_for_geogrid_stops_before_it(
    reference_case: Case, tmp_path: Path
) -> None:
    """geogrid joins the geography path and each dataset folder in 128 characters: a longer
    path would end in a Fortran error, the script says what to do instead."""
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    long = fake_geography(tmp_path / ("g" * 95))
    chosen = options(wrf, wps).model_copy(update={"geog_dir": posix(long)})
    write_folder(study_case(reference_case), chosen, export)
    done = run("run_wps.sh", export / "wps", tools)
    said = done.stdout + done.stderr
    assert done.returncode != 0
    assert "90" in said and "ln -s" in said
    assert not list((export / "wps").glob("geo_em*"))


def test_plan_of_the_study_case(reference_case: Case) -> None:
    plan = method.plan(study_case(reference_case))
    assert [(w.block, w.useful_hours) for w in plan.windows] == [
        ("2024-02", 36),
        ("2024-02", 36),
        ("2024-03", 12),
        ("2024-03", 36),
    ]
    assert [w.index for w in plan.computation] == [4, 3, 2, 1]


@needs_bash
@pytest.mark.parametrize("time_step", [None, 35])
def test_exported_scripts_run_the_method_end_to_end(
    reference_case: Case, tmp_path: Path, time_step: int | None
) -> None:
    case = study_case(reference_case, time_step)
    plan = method.plan(case)
    steps = timesteps.time_steps(case)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    n = names()
    for year in (2024,):
        data = export / n["data"] / "gfs" / str(year)
        data.mkdir(parents=True)
        (data / "gfs.2024022612.f000.grib2").write_text("grib")

    done = run("run_wps.sh", export / "wps", tools)
    assert done.returncode == 0, done.stdout + done.stderr
    done = run("run_wrf.sh", export / "wrf", tools)
    assert done.returncode == 0, done.stdout + done.stderr

    # Windows in the order of computation, each with its own fresh dates
    calls = [line.split() for line in (export / "wrf" / "calls.log").read_text().splitlines()]
    assert [(utc(c[1]), utc(c[2])) for c in calls] == [
        (w.simulation_start, w.simulation_end) for w in plan.computation
    ]
    for window in plan.windows:
        namelist = (export / "wrf" / n["logs"] / f"namelist.input.{window.id}").read_text()
        assert "restart = .false." in namelist
        assert f"run_hours = {window.simulated_seconds // 3600}," in namelist
    assert not list((export / "wrf").glob("wrfrst*"))

    # History: exactly [D, F] every hour on each domain, each file from the window holding it
    expected = history_times(plan, timedelta(hours=1))
    for domain in (1, 2):
        files = sorted((export / "wrf").glob(f"wrfout_d0{domain}_*"))
        times = [utc(f.name[11:]) for f in files]
        assert times == expected
        for file, time in zip(files, times, strict=True):
            start = file.read_text().split('"')[1]
            source = history_source(plan, time)
            assert utc(start) == source.simulation_start
            assert time >= source.useful_start  # never a spin-up file
    spin = sorted((export / "wrf" / n["spin_up"]).glob("wrfout_d01_*"))
    assert [utc(f.name[11:]) for f in spin] == [
        plan.start - timedelta(hours=h) for h in range(12, 0, -1)
    ]

    # Time series: ]D, F] in hours since D, strictly increasing, no gap, exact count
    for domain in (1, 2):
        dt = steps.steps[domain - 1]
        for variable, column in (("TS", 1), ("UU", 0), ("VV", 0)):
            lines = (
                (export / "wrf" / n["tslist_period"] / f"MAT.d0{domain}.{variable}")
                .read_text()
                .splitlines()
            )
            assert lines[0].rstrip().endswith("2024-02-27_00:00:00")
            hours = [float(line.split()[column]) for line in lines[1:]]
            assert all(b > a for a, b in itertools.pairwise(hours))
            assert 0 < hours[0] <= float(dt) / 3600 + 1e-6
            assert hours[-1] <= 120 + 1e-6
            total = 0
            for window in plan.windows:
                first, last = method.kept_steps(window, dt)
                total += last - first + 1
            assert len(hours) == total
            if Fraction(12 * 3600) % dt == 0:
                # dt divides the spin-up and the windows: one step everywhere, (F - D) / dt lines
                assert len(hours) == int(Fraction(120 * 3600) / dt)
                gaps = {round((b - a) * 3600, 2) for a, b in itertools.pairwise(hours)}
                assert gaps == {round(float(dt), 2)}
            else:
                # Each window keeps the steps of ]start, end]; junctions are closer than 2 dt
                assert max(b - a for a, b in itertools.pairwise(hours)) * 3600 < 2 * float(dt)
    blocks = sorted(p.name for p in (export / "wrf" / n["tslist_blocks"]).iterdir())
    assert {name.rsplit(".", 1)[1] for name in blocks} == {"2024-02", "2024-03"}
    assert not list((export / "wrf" / n["tslist_windows"]).iterdir())


@needs_bash
def test_the_scripts_find_the_engine_below_the_folders_given(
    reference_case: Case, tmp_path: Path, lang: str
) -> None:
    """Found twice on the work VM: a folder one level too high (/app/ows/moteur for WRF,
    /app/ows/geog for the geography) stopped geogrid. The scripts look below the folder given,
    whatever the names, and say in the log which folder they took; nothing found stops them with
    the variable to correct."""
    wrf, wps, tools = fake_engine(tmp_path / "engine")
    export = tmp_path / "export"
    top = posix(tmp_path / "engine")
    chosen = options(wrf, wps).model_copy(update={"wrf_dir": top, "wps_dir": top})
    write_folder(study_case(reference_case), chosen, export)
    n = names()
    data = export / n["data"] / "gfs" / "2024"
    data.mkdir(parents=True)
    for day in ("2024022612", "2024022700"):
        (data / f"gfs.{day}.f000.grib2").write_text("grib")
    done = run("run_wps.sh", export / "wps", tools)
    said = done.stdout + done.stderr
    assert done.returncode == 0, said
    assert (
        f"= {posix(wps)}" in said
        and f"= {posix(tmp_path / 'engine' / 'geog' / 'WPS_GEOG')}" in said
    )
    namelist = (export / "wps" / "namelist.wps").read_text(encoding="utf-8")
    assert f"'{posix(tmp_path / 'engine' / 'geog' / 'WPS_GEOG')}/'" in namelist
    wrong = options(wrf, wps).model_copy(update={"geog_dir": posix(tmp_path / "nothing")})
    write_folder(study_case(reference_case), wrong, tmp_path / "wrong")
    stopped = run("run_wps.sh", tmp_path / "wrong" / "wps", tools)
    assert stopped.returncode != 0
    assert ("DOSSIER_GEOG" if lang == "fr" else "GEOG_DIR") in stopped.stdout + stopped.stderr


@needs_bash
def test_the_high_resolution_is_taken_when_one_domain_reads_it(
    reference_case: Case, tmp_path: Path
) -> None:
    """d01 in lowres and d02 in default: geogrid needs the high resolution geography, even when
    a low resolution one comes first below the folder given."""
    case = study_case(reference_case)
    case.grid.domains[0].geog_data_res = "lowres"
    case.grid.domains[1].geog_data_res = "default"
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    geog = tmp_path / "moteur" / "geog"
    write_program(geog / "A_low" / "topo_gmted2010_5m" / "index", "type=continuous\n")
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    data = export / names()["data"] / "gfs" / "2024"
    data.mkdir(parents=True)
    (data / "gfs.2024022612.f000.grib2").write_text("grib")
    done = run("run_wps.sh", export / "wps", tools)
    assert done.returncode == 0, done.stdout + done.stderr
    namelist = (export / "wps" / "namelist.wps").read_text(encoding="utf-8")
    assert f"'{posix(geog / 'WPS_GEOG')}/'" in namelist


@needs_bash
def test_wps_reads_the_data_of_the_shared_folder(reference_case: Case, tmp_path: Path) -> None:
    """Data downloaded once into the engine's shared folder: ungrib of any calculation reads
    them there, and the package's own data folder stays empty."""
    case = study_case(reference_case)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    shared = tmp_path / "donnees"
    export = tmp_path / "export"
    chosen = options(wrf, wps).model_copy(update={"data_dir": posix(shared)})
    write_folder(case, chosen, export)
    (shared / "gfs" / "2024").mkdir(parents=True)
    (shared / "gfs" / "2024" / "gfs.2024022612.f000.grib2").write_text("grib")

    done = run("run_wps.sh", export / "wps", tools)
    assert done.returncode == 0, done.stdout + done.stderr
    assert not (export / names()["data"] / "gfs").exists()


@needs_bash
def test_a_ten_minute_simulation_prepares_between_data_times(
    reference_case: Case, tmp_path: Path
) -> None:
    """Any length WRF accepts: real.exe from the data time before the spin-up to the one after
    the end (GFS every 6 h), wrf.exe stopped at the end by run_minutes."""
    case = study_case(reference_case)
    case.period.start = datetime(2024, 2, 27)
    case.period.end = datetime(2024, 2, 27, 0, 10)
    case.history_interval_minutes = 10
    plan = method.plan(case)
    (window,) = plan.windows
    assert window.simulation_start == datetime(2024, 2, 26, 12)
    assert window.preparation_end == datetime(2024, 2, 27, 6)
    assert plan.wps_passes[0].end == datetime(2024, 2, 27, 6)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    n = names()
    data = export / n["data"] / "gfs" / "2024"
    data.mkdir(parents=True)
    (data / "gfs.2024022612.f000.grib2").write_text("grib")
    assert run("run_wps.sh", export / "wps", tools).returncode == 0
    done = run("run_wrf.sh", export / "wrf", tools)
    assert done.returncode == 0, done.stdout + done.stderr

    calls = [line.split() for line in (export / "wrf" / "calls.log").read_text().splitlines()]
    assert [(utc(c[1]), utc(c[2])) for c in calls] == [
        (datetime(2024, 2, 26, 12), datetime(2024, 2, 27, 0, 10))
    ]
    namelist = (export / "wrf" / n["logs"] / f"namelist.input.{window.id}").read_text()
    assert "run_hours = 12," in namelist and "run_minutes = 10," in namelist
    for domain in (1, 2):
        files = sorted((export / "wrf").glob(f"wrfout_d0{domain}_*"))
        assert [utc(f.name[11:]) for f in files] == [plan.start, plan.end]
    steps = timesteps.time_steps(case)
    for domain in (1, 2):
        first, last = method.kept_steps(window, steps.steps[domain - 1])
        lines = (
            (export / "wrf" / n["tslist_period"] / f"MAT.d0{domain}.TS").read_text().splitlines()
        )
        assert len(lines) - 1 == last - first + 1
        assert float(lines[-1].split()[1]) <= 10 / 60 + 1e-6


@needs_bash
@pytest.mark.parametrize("cumulative", ["0", "1"])
def test_continuous_windows_chain_restart_files_end_to_end(
    reference_case: Case, tmp_path: Path, cumulative: str
) -> None:
    case = study_case(reference_case)
    case.windows = Windows(useful_hours=36, grouping="month", restart=True)
    plan = method.plan(case)
    assert plan.restart and [w.index for w in plan.computation] == [1, 2, 3, 4]
    assert [w.spin_up.total_seconds() for w in plan.windows] == [12 * 3600, 0, 0, 0]
    steps = timesteps.time_steps(case)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    n = names()
    data = export / n["data"] / "gfs" / "2024"
    data.mkdir(parents=True)
    (data / "gfs.2024022612.f000.grib2").write_text("grib")
    assert run("run_wps.sh", export / "wps", tools).returncode == 0
    done = run("run_wrf.sh", export / "wrf", tools, CUMULATIVE=cumulative)
    assert done.returncode == 0, done.stdout + done.stderr

    # Chronological, the first from a cold start after the spin-up, the others from a restart
    calls = [line.split() for line in (export / "wrf" / "calls.log").read_text().splitlines()]
    assert [(utc(c[1]), utc(c[2])) for c in calls] == [
        (w.simulation_start, w.simulation_end) for w in plan.windows
    ]
    for window in plan.windows:
        namelist = (export / "wrf" / n["logs"] / f"namelist.input.{window.id}").read_text()
        assert f"restart = .{str(window.restart).lower()}." in namelist
        assert f"restart_interval = {window.simulated_seconds // 60}," in namelist
    # Only the restart files of the last time are kept
    assert {utc(f.name[11:]) for f in (export / "wrf").glob("wrfrst_d0*")} == {plan.end}

    # History: exactly [D, F], from the window holding each time (or the very first start)
    expected = history_times(plan, timedelta(hours=1))
    for domain in (1, 2):
        files = sorted((export / "wrf").glob(f"wrfout_d0{domain}_*"))
        assert [utc(f.name[11:]) for f in files] == expected
        for file in files:
            start = utc(file.read_text().split('"')[1])
            source = history_source(plan, utc(file.name[11:]))
            assert start in (source.simulation_start, plan.windows[0].simulation_start)
    spin = sorted((export / "wrf" / n["spin_up"]).glob("wrfout_d01_*"))
    assert len(spin) == 12

    # Time series: ]D, F] in hours since D, one step everywhere, whatever WRF's time origin
    for domain in (1, 2):
        dt = steps.steps[domain - 1]
        lines = (
            (export / "wrf" / n["tslist_period"] / f"MAT.d0{domain}.TS").read_text().splitlines()
        )
        hours = [float(line.split()[1]) for line in lines[1:]]
        assert len(hours) == int(Fraction(120 * 3600) / dt)
        gaps = {round((b - a) * 3600, 2) for a, b in itertools.pairwise(hours)}
        assert gaps == {round(float(dt), 2)}
        assert 0 < hours[0] <= float(dt) / 3600 + 1e-6


def wps_ready(case: Case, tmp_path: Path) -> tuple[Path, Path]:
    """An exported folder with one GFS file per data time of its WPS pass, and fake tools."""
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    data = export / names()["data"] / "gfs" / "2024"
    data.mkdir(parents=True)
    for hour in range(0, 24 * 8, 6):
        (data / f"gfs.{hour:03d}.grib2").write_bytes(b"g" * 1000)
    return export, tools


@needs_bash
def test_ungrib_stops_before_filling_the_disk(reference_case: Case, tmp_path: Path) -> None:
    """ungrib says nothing when the disk fills up: the space is checked before it runs."""
    export, tools = wps_ready(study_case(reference_case), tmp_path)
    write_program(
        tools / "df",
        "#!/bin/bash\necho 'Filesystem 1024-blocks Used Available Capacity Mounted'\n"
        "echo 'disk 100 99 1 99% /'\n",
    )
    done = run("run_wps.sh", export / "wps", tools)
    assert done.returncode != 0
    assert "ungrib" in done.stderr and ("Go" in done.stderr or "GB" in done.stderr)
    calls = export / "calls.log"
    assert not calls.exists() or "ungrib" not in calls.read_text()


@needs_bash
def test_ungrib_stops_when_its_files_are_missing(reference_case: Case, tmp_path: Path) -> None:
    """A time ungrib did not write stops WPS before metgrid, with the reason; files left by an
    earlier run in the same folder are not counted."""
    export, tools = wps_ready(study_case(reference_case), tmp_path)
    earlier = export / "wps" / "ungrib" / "2024"
    earlier.mkdir(parents=True)
    for day in range(1, 31):
        (earlier / f"FILE:2024-01-{day:02d}_00").write_text("earlier run")
    done = run("run_wps.sh", export / "wps", tools, OWS_UNGRIB_WRITES="0")
    assert done.returncode != 0
    assert "ungrib" in done.stderr and " 0 " in done.stderr
    calls = (export / "calls.log").read_text().splitlines()
    assert not [line for line in calls if line.startswith("metgrid")]


@needs_bash
def test_wps_runs_once_per_year_with_the_spin_up_before_each(
    reference_case: Case, tmp_path: Path
) -> None:
    case = study_case(reference_case)
    case.period.start, case.period.end = datetime(2023, 12, 30), datetime(2024, 1, 2)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    for year in (2023, 2024):
        data = export / names()["data"] / "gfs" / str(year)
        data.mkdir(parents=True)
        (data / f"gfs.{year}.f000.grib2").write_text("grib")
    done = run("run_wps.sh", export / "wps", tools)
    assert done.returncode == 0, done.stdout + done.stderr
    calls = [line.split() for line in (export / "calls.log").read_text().splitlines()]
    ungrib = [c for c in calls if c[0] == "ungrib"]
    metgrid = [c for c in calls if c[0] == "metgrid"]
    assert [(c[1], c[2]) for c in metgrid] == [
        ("2023-12-29_12:00:00", "2024-01-01_00:00:00"),
        ("2023-12-31_12:00:00", "2024-01-02_00:00:00"),
    ]
    assert [c[1].rsplit("/", 2)[1:] for c in ungrib] == [["2023", "FILE"], ["2024", "FILE"]]
    # Each pass reads the files of the years it covers: 2023 ends on 1 January 2024 00:00,
    # 2024 starts on 31 December 2023 at 12:00
    assert [c[-1] for c in ungrib] == ["2", "2"]
    assert all("ungrib/2024/FILE" in c[-1] or "ungrib/2023/FILE" in c[-1] for c in metgrid)
    met_em = sorted(
        p.name.replace(COLON, ":") for p in (export / "wps" / "met_em").glob("met_em.d01.*")
    )
    expected = []
    time = datetime(2023, 12, 29, 12)
    while time <= datetime(2024, 1, 2):
        expected.append(f"met_em.d01.{time:%Y-%m-%d_%H:%M:%S}.nc")
        time += timedelta(seconds=case.period.interval_seconds)
    assert met_em == expected


@needs_bash
def test_a_failed_wrf_stops_before_touching_outputs(reference_case: Case, tmp_path: Path) -> None:
    case = study_case(reference_case)
    plan = method.plan(case)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    met_em = export / "wps" / "met_em"
    met_em.mkdir(parents=True)
    time = plan.forcing_start
    while time <= plan.end:
        for domain in (1, 2):
            (met_em / disk_name(f"met_em.d0{domain}.{time:%Y-%m-%d_%H:%M:%S}.nc")).write_text(
                "num_metgrid_levels = 38 ;\n\t\t:NUM_METGRID_SOIL_LEVELS = 4 ;\n"
            )
        time += timedelta(seconds=case.period.interval_seconds)
    second = plan.computation[1]
    done = run(
        "run_wrf.sh",
        export / "wrf",
        tools,
        ECHEC_A=second.simulation_start.strftime("%Y-%m-%d_%H:%M:%S"),
    )
    assert done.returncode != 0
    assert "wrf.exe" in done.stderr and "SUCCESS COMPLETE WRF" in done.stderr
    # The first window was processed; nothing of the failed one, no assembled period
    n = names()
    assert list((export / "wrf" / n["tslist_windows"]).glob(f"*.{plan.computation[0].id}"))
    assert not list((export / "wrf" / n["tslist_windows"]).glob(f"*.{second.id}"))
    assert not (export / "wrf" / n["tslist_period"]).exists()


def test_one_wrf_script_the_same_on_a_cluster_and_a_computer(
    reference_case: Case, tmp_path: Path
) -> None:
    case = study_case(reference_case)
    wrf, wps, _ = fake_engine(tmp_path / "moteur")
    settings = options(wrf, wps, "cluster")
    settings.environment = ["module load impi/2019.9.304"]
    settings.slurm.wckey = "P1259:WRF"
    files = export_files(case, settings)
    n = names()
    assert [p for p in files if "run_wrf" in p] == ["wrf/run_wrf.sh"]
    assert not [p for p in files if p.endswith(("submit.sh", "soumettre.sh"))]
    assert n["common"] in files
    cluster = files["wrf/run_wrf.sh"][0]
    assert "#SBATCH --wckey=P1259:WRF" in cluster and "#SBATCH --exclusive" in cluster
    assert "#SBATCH --output=WRF_%j.out" in cluster
    assert f'{launcher_variable()}="srun -n 2"' in cluster
    assert "module load impi/2019.9.304" in cluster
    assert cluster.rstrip().endswith("exit 0")
    # Editor mode: the raw header as written
    settings.slurm.raw = "#SBATCH --nodes=3\n#SBATCH --job-name={job}"
    files = export_files(case, settings)
    assert "#SBATCH --job-name=WRF" in files["wrf/run_wrf.sh"][0]
    assert "#SBATCH --nodes=3" in files["wps/run_wps.sh"][0]
    local = export_files(case, options(wrf, wps))["wrf/run_wrf.sh"][0]
    assert "#SBATCH" not in local and "module load" not in local
    assert f'{launcher_variable()}="mpirun -np 2"' in local
    # The body is the same line for line: only the header differs
    title = "### PARAMETRES AVANCES ###" if i18n.current() == "fr" else "### ADVANCED SETTINGS ###"
    cluster = export_files(case, options(wrf, wps, "cluster"))["wrf/run_wrf.sh"][0]
    assert local[local.index(title) :] == cluster[cluster.index(title) :]


FAKE_SQUEUE = """#!/bin/bash
cat "$TEMPS_RESTANT_FICHIER"
"""

FAKE_SBATCH = """#!/bin/bash
echo "sbatch $*" >> sbatch.log
echo "Submitted batch job 124"
"""


@needs_bash
def test_on_slurm_the_script_submits_itself_again_and_resumes(
    reference_case: Case, tmp_path: Path
) -> None:
    """Before each window, the script checks the time left in the Slurm job: when the next
    window would not fit, it submits itself again (after this job) and stops; the next job
    resumes at the next window and the results are those of a single run."""
    case = study_case(reference_case)
    plan = method.plan(case)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    write_program(tools / "squeue", FAKE_SQUEUE)
    write_program(tools / "sbatch", FAKE_SBATCH)
    export = tmp_path / "export"
    settings = options(wrf, wps, "cluster")
    write_folder(case, settings, export)
    for script in (export / "wrf" / "run_wrf.sh", export / "wps" / "run_wps.sh"):
        text = (
            script.read_text().replace('"srun -n 2"', '"mpirun -np 2"').replace('"srun -n 1"', '""')
        )
        script.write_text(text)
    met_em = export / "wps" / "met_em"
    met_em.mkdir(parents=True)
    time = plan.forcing_start
    while time <= plan.end:
        for domain in (1, 2):
            (met_em / disk_name(f"met_em.d0{domain}.{time:%Y-%m-%d_%H:%M:%S}.nc")).write_text(
                "num_metgrid_levels = 38 ;\n\t\t:NUM_METGRID_SOIL_LEVELS = 4 ;\n"
            )
        time += timedelta(seconds=case.period.interval_seconds)
    left = tmp_path / "left.txt"
    # 1st job: 5 minutes left, less than the 10 min margin: one window, then a new submission
    left.write_text("05:00\n")
    done = run(
        "run_wrf.sh", export / "wrf", tools, SLURM_JOB_ID="123", TEMPS_RESTANT_FICHIER=posix(left)
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert (export / "wrf" / "sbatch.log").read_text().split() == [
        "sbatch",
        "--dependency=afterany:123",
        "run_wrf.sh",
    ]
    calls = (export / "wrf" / "calls.log").read_text().splitlines()
    assert len(calls) == 1
    assert not (export / "wrf" / names()["tslist_period"]).exists()
    # 2nd job: two days left: it resumes at the next window and ends with the assembly
    left.write_text("2-00:00:00\n")
    done = run(
        "run_wrf.sh", export / "wrf", tools, SLURM_JOB_ID="124", TEMPS_RESTANT_FICHIER=posix(left)
    )
    assert done.returncode == 0, done.stdout + done.stderr
    calls = [line.split() for line in (export / "wrf" / "calls.log").read_text().splitlines()]
    assert [(utc(c[1]), utc(c[2])) for c in calls] == [
        (w.simulation_start, w.simulation_end) for w in plan.computation
    ]
    assert len((export / "wrf" / "sbatch.log").read_text().splitlines()) == 1
    for domain in (1, 2):
        files = sorted((export / "wrf").glob(f"wrfout_d0{domain}_*"))
        assert [utc(f.name[11:]) for f in files] == history_times(plan, timedelta(hours=1))
    period = export / "wrf" / names()["tslist_period"] / "MAT.d01.TS"
    assert period.is_file()
    # Run once more: nothing is computed again
    done = run("run_wrf.sh", export / "wrf", tools)
    assert done.returncode == 0, done.stdout + done.stderr
    assert len((export / "wrf" / "calls.log").read_text().splitlines()) == len(plan.windows)


@needs_bash
def test_a_window_longer_than_a_slurm_job_stops_with_a_clear_message(
    reference_case: Case, tmp_path: Path
) -> None:
    case = study_case(reference_case)
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    write_program(tools / "squeue", FAKE_SQUEUE)
    write_program(tools / "sbatch", FAKE_SBATCH)
    export = tmp_path / "export"
    write_folder(case, options(wrf, wps), export)
    (export / "wps" / "met_em").mkdir(parents=True)
    plan = method.plan(case)
    time = plan.forcing_start
    while time <= plan.end:
        for domain in (1, 2):
            (
                export
                / "wps"
                / "met_em"
                / disk_name(f"met_em.d0{domain}.{time:%Y-%m-%d_%H:%M:%S}.nc")
            ).write_text("num_metgrid_levels = 38 ;\n\t\t:NUM_METGRID_SOIL_LEVELS = 4 ;\n")
        time += timedelta(seconds=case.period.interval_seconds)
    state = export / "wrf" / names()["logs"] / names()["state"]
    state.parent.mkdir(parents=True)
    word = "fenetre" if i18n.current() == "fr" else "window"
    state.write_text(f"{word} 004 7200 43200\n")  # a window took 2 h of real time for 12 h
    left = tmp_path / "left.txt"
    left.write_text("01:00:00\n")  # a fresh job of 1 h cannot hold the next one
    done = run(
        "run_wrf.sh", export / "wrf", tools, SLURM_JOB_ID="7", TEMPS_RESTANT_FICHIER=posix(left)
    )
    assert done.returncode != 0
    assert "--time" in done.stderr
    assert not (export / "wrf" / "sbatch.log").exists()


def test_export_contents_formats_and_permissions(reference_case: Case, tmp_path: Path) -> None:
    case = study_case(reference_case)
    case.time_series = TimeSeries(turbines="cells")
    case.input_source = "era5"
    name, data = export_zip(case, ExportOptions(target="cluster"))
    assert name == "Horns-Rev-reference-WRF.zip"
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
        infos = {info.filename.split("/", 1)[1]: info for info in archive.infolist()}
        for path, info in infos.items():
            content = archive.read(info)
            assert b"\r" not in content, path  # LF only, even exported from Windows
            content.decode("ascii")
            mode = info.external_attr >> 16
            executable = path.endswith((".sh", ".py"))
            assert bool(mode & 0o111) == executable, path
    n = names()
    for required in (
        n["readme"],
        "manifest.json",
        n["plan"],
        "wps/namelist.wps",
        "wps/Vtable.ECMWF",
        "wps/run_wps.sh",
        "wrf/namelist.input",
        "wrf/windturbines.txt",
        "wrf/turbines.csv",
        "wrf/tslist",
        f"wrf/{n['cells']}",
        "wrf/run_wrf.sh",
        n["common"],
        f"{n['data']}/{n['download_era5']}",
    ):
        assert required in infos, required
    files = export_files(case, ExportOptions())
    manifest = json.loads(files["manifest.json"][0])
    plan = method.plan(case)
    assert [w["id"] for w in manifest["windows"]] == [w.id for w in plan.windows]
    assert manifest["conventions"]["time_series"] == "]D, F]"
    points = files["wrf/tslist"][0].splitlines()[3:]
    namelist = files["wrf/namelist.input"][0]
    assert f"max_ts_locs = {len(points)}" in namelist and len(points) >= 1
    assert "frames_per_outfile = 1, 1" in namelist and "restart = .false." in namelist
    first = plan.computation[0]
    assert f"start_day = {first.simulation_start.day}, {first.simulation_start.day}" in namelist
    cells = files[f"wrf/{n['cells']}"][0].splitlines()
    assert cells[0] == (
        "prefixe_tslist,domaine,i,j,nombre_eoliennes,eoliennes,parcs"
        if i18n.current() == "fr"
        else "tslist_prefix,domain,i,j,turbine_count,turbines,farms"
    )
    assert sum(int(line.split(",")[4]) for line in cells[1:]) == sum(
        len(f.turbines) for f in case.farms
    )


def test_the_shared_data_folder_is_where_the_data_go_and_ungrib_reads(
    reference_case: Case,
) -> None:
    case = study_case(reference_case)
    case.input_source = "gfs"
    n = names()
    files = export_files(case, ExportOptions(target="local", data_dir="/app/ows/donnees/"))
    assert "/app/ows/donnees/gfs/%Y/gfs.*.grib2" in files["wps/run_wps.sh"][0]
    script = files[f"{n['data']}/{n['download_gfs']}"][0]
    assert '="/app/ows/donnees"\t#' in script and "/gfs/$" in script
    readme = files[n["readme"]][0]
    assert "/app/ows/donnees/gfs/<" in readme
    # Without it (a cluster), the package's own data folder, as before
    cluster = export_files(case, ExportOptions(target="cluster"))
    assert f"../{n['data']}/gfs/%Y/gfs.*.grib2" in cluster["wps/run_wps.sh"][0]
    assert "=.\t#" in cluster[f"{n['data']}/{n['download_gfs']}"][0]


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
@pytest.mark.parametrize("target", ["cluster", "local"])
def test_generated_scripts_pass_shellcheck(
    reference_case: Case, tmp_path: Path, target: str
) -> None:
    case = study_case(reference_case)
    case.input_source = "gfs"
    # A separate sea temperature: two sources, so two variables of each kind read by their name
    case.sea_surface.source = "grib"
    case.sea_surface.grib = GribInput(folder="/data/sst", pattern="*.grb", vtable="Vtable.SST")
    # A computer downloads into the shared data folder of the engine
    data_dir = "/app/ows/donnees" if target == "local" else ""
    names = write_folder(case, ExportOptions(target=target, data_dir=data_dir), tmp_path)  # type: ignore[arg-type]
    scripts = [str(tmp_path / name) for name in names if name.endswith(".sh")]
    shellcheck = shutil.which("shellcheck")
    assert shellcheck
    done = subprocess.run(
        [shellcheck, "-x", "-s", "bash", "-S", "style", *scripts],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout


def test_api_plan_preview_zip_and_folder(reference_case: Case, tmp_path: Path, lang: str) -> None:
    from helpers import make_client

    client = make_client(tmp_path)
    client.headers["X-OWS-Lang"] = lang
    case = study_case(reference_case)
    body = case.model_dump(mode="json")
    plan = client.post("/api/method/plan", json=body).json()
    assert [w["order"] for w in plan["windows"]] == [4, 3, 2, 1]
    assert [b["id"] for b in plan["blocks"]] == ["2024-02", "2024-03"]
    preview = client.post("/api/method/files", json={"case": body}).json()
    paths = {f["path"] for f in preview["files"]}
    assert "wrf/run_wrf.sh" in paths and names()["common"] in paths
    assert preview["issues"] == []
    case_id = client.post("/api/cases", json=body).json()["id"]
    response = client.get(
        f"/api/cases/{case_id}/method/files.zip",
        params={"options": json.dumps({"target": "local", "cores": 4})},
    )
    assert response.status_code == 200 and response.content.startswith(b"PK")
    with zipfile.ZipFile(__import__("io").BytesIO(response.content)) as archive:
        script = archive.read("Horns-Rev-reference-WRF/wrf/run_wrf.sh").decode()
    assert f'{launcher_variable()}="mpirun -np 4"' in script
    destination = tmp_path / "sortie"
    destination.mkdir()
    written = client.post(f"/api/cases/{case_id}/method/folder", json={"folder": str(destination)})
    assert written.status_code == 200
    assert (destination / "Horns-Rev-reference-WRF" / "wrf" / "namelist.input").is_file()
    again = client.post(f"/api/cases/{case_id}/method/folder", json={"folder": str(destination)})
    assert again.status_code == 409
    # Replaced: the downloaded data stay, the rest is written again
    extracted = destination / "Horns-Rev-reference-WRF"
    (extracted / names()["data"]).mkdir(exist_ok=True)
    (extracted / names()["data"] / "gfs.grib2").write_text("x")
    (extracted / "wrf" / "old.txt").write_text("x")
    known = client.get(f"/api/cases/{case_id}/method/folder", params={"folder": str(destination)})
    assert known.json()["exists"] and known.json()["ours"]
    replaced = client.post(
        f"/api/cases/{case_id}/method/folder", json={"folder": str(destination), "replace": True}
    )
    assert replaced.status_code == 200
    assert (extracted / names()["data"] / "gfs.grib2").is_file()
    assert not (extracted / "wrf" / "old.txt").exists()
    assert (extracted / "wrf" / "namelist.input").is_file()
    deleted = client.delete(
        f"/api/cases/{case_id}/method/folder", params={"folder": str(destination)}
    )
    assert deleted.json()["deleted"] and not extracted.exists()
    # A folder that no extraction wrote is never replaced nor deleted
    extracted.mkdir()
    (extracted / "mine.txt").write_text("x")
    kept = client.delete(f"/api/cases/{case_id}/method/folder", params={"folder": str(destination)})
    assert kept.status_code == 409 and (extracted / "mine.txt").is_file()
    bad = client.get(f"/api/cases/{case_id}/method/files.zip", params={"options": '{"cores": 0}'})
    assert bad.status_code == 422


def test_vtables_are_named_after_their_table(reference_case: Case) -> None:
    """A Vtable keeps the name of its source (Vtable.GFS, Vtable.SST...); run_wps links each
    source's own table as Vtable before ungrib."""
    files = export_files(reference_case, ExportOptions())
    tables = sorted(name for name in files if name.startswith("wps/Vtable"))
    assert tables and "wps/Vtable.FILE" not in tables
    assert all(
        name.split("/")[1] in {"Vtable.GFS", "Vtable.ECMWF", "Vtable.SST"} or ".perso" in name
        for name in tables
    )
    script = files["wps/run_wps.sh"][0]
    for name in tables:
        assert name.split("/")[1] in script
    assert 'ln -sf "${!table_variable}" Vtable' in script


@needs_bash
def test_own_netcdf_files_are_converted_at_export(reference_case: Case, tmp_path: Path) -> None:
    """ungrib reads only GRIB: the user's NetCDF files are converted on this computer into WPS
    intermediate files of the package, and metgrid reads them without ungrib."""
    import ncmaker
    import numpy as np

    folder = tmp_path / "era5-nc"
    folder.mkdir()
    day = datetime(2025, 10, 1)
    times = [day + timedelta(hours=6 * k) for k in range(5)]
    lat, lon = np.arange(65.0, 44.99, -0.25), np.arange(-5.0, 20.01, 0.25)
    ncmaker.era5(folder / "pressure.nc", times, lat, lon, pressure=True)
    ncmaker.era5(folder / "single.nc", times, lat, lon, pressure=False)
    case = reference_case.model_copy(deep=True)
    case.period.start += timedelta(hours=case.spin_up_hours)
    case.period.interval_seconds = 21600
    case.input_source = "grib"
    case.grib = GribInput(folder=str(folder), pattern="*.nc", vtable="Vtable.ECMWF")
    wrf, wps, tools = fake_engine(tmp_path / "moteur")
    export = tmp_path / "export"
    written = write_folder(case, options(wrf, wps), export)
    converted = export / "wps" / names()["intermediate"] / "FILE"
    expected = [f"FILE_{t:%Y-%m-%d_%H}" for t in times]
    assert sorted(p.name for p in converted.iterdir()) == expected
    assert all(f"wps/{names()['intermediate']}/FILE/{name}" in written for name in expected)
    assert not (export / "wps" / "Vtable.ECMWF").exists()
    script = (export / "wps" / "run_wps.sh").read_text()
    assert ("CONVERTIS=(FILE)" if i18n.current() == "fr" else "CONVERTED=(FILE)") in script
    done = run("run_wps.sh", export / "wps", tools)
    assert done.returncode == 0, done.stdout + done.stderr
    calls = [line.split() for line in (export / "calls.log").read_text().splitlines()]
    assert not [c for c in calls if c[0] == "ungrib"]
    metgrid = [c for c in calls if c[0] == "metgrid"]
    assert len(metgrid) == 1 and "ungrib/2025/FILE" in metgrid[0][-1]
    linked = sorted(p.name for p in (export / "wps" / "ungrib" / "2025").iterdir())
    assert linked == [disk_name(f"FILE:{t:%Y-%m-%d_%H}") for t in times]
    # The ZIP holds the same converted files
    _, data = export_zip(case, options(wrf, wps))
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as archive:
        inside = [n for n in archive.namelist() if f"/{names()['intermediate']}/FILE/" in n]
    assert sorted(n.rsplit("/", 1)[1] for n in inside) == expected


def test_linux_computer_loads_the_engine_environment_and_gives_both_commands(
    reference_case: Case,
) -> None:
    chosen = ExportOptions(target="local", environment=["source /app/ows/moteur/env.sh"])
    files = export_files(reference_case, chosen)
    for script in ("wps/run_wps.sh", "wrf/run_wrf.sh"):
        assert "source /app/ows/moteur/env.sh" in files[script][0]
    readme = files[names()["readme"]][0]
    assert "setsid nohup bash -c 'cd " in readme
    # And how to follow it: steps, programs running, instant reached, errors
    assert "grep 'Timing for main' wrf/rsl.error.0000" in readme and "ps -ef" in readme
    assert "bash run_wps.sh && cd ../wrf && bash run_wrf.sh' >" in readme
    assert f"| tee {names()['run_log']}" in readme


@needs_bash
def test_home_paths_of_the_compute_page_work_in_the_scripts(
    reference_case: Case, tmp_path: Path
) -> None:
    """The Compute page accepts ~/... and $HOME/... for WRF and the input data: bash expands
    them in the scripts instead of looking for a folder literally named ~ or $HOME."""
    home = tmp_path / "home"
    fake_engine(home / "engine")
    chosen = ExportOptions(
        target="local",
        cores=2,
        wps_cores=1,
        wrf_dir="~/engine/WRF",
        wps_dir="$HOME/engine/WPS",
        geog_dir="${HOME}/engine/geog",
        data_dir="~/donnees",
    )
    export = tmp_path / "export"
    write_folder(study_case(reference_case), chosen, export)
    (home / "donnees" / "gfs" / "2024").mkdir(parents=True)
    (home / "donnees" / "gfs" / "2024" / "gfs.2024022612.f000.grib2").write_text("grib")
    done = run("run_wps.sh", export / "wps", home / "engine" / "outils", HOME=posix(home))
    assert done.returncode == 0, done.stdout + done.stderr
