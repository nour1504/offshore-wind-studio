"""Where a calculation stands, read from the files its scripts write (nothing is run), and the
order of magnitude of its computing time."""

import os
import time
from pathlib import Path

from owstudio.core.case.model import Case
from owstudio.core.method.estimate import estimate
from owstudio.core.method.progress import progress

PLAN = (
    "fenetre,ordre_calcul,bloc,debut_simulation,fin_simulation,debut_utile,fin_utile,"
    "heures_utiles,heures_simulees,duree_simulee_s,decalage_depuis_D_s,reprise\n"
    "001,2,f001,2025-09-30_12:00:00,2025-10-01_12:00:00,x,x,12,24,86400,0,0\n"
    "002,1,f001,2025-10-01_00:00:00,2025-10-02_00:00:00,x,x,12,24,86400,0,0\n"
)


def _folder(root: Path) -> Path:
    (root / "wps").mkdir(parents=True)
    (root / "wrf" / "journaux").mkdir(parents=True)
    (root / "manifest.json").write_text("{}")
    (root / "plan_fenetres.csv").write_text(PLAN)
    return root


def test_nothing_run_yet(tmp_path: Path) -> None:
    found = progress(_folder(tmp_path))
    assert found["state"] == "none" and found["windows"] == 2 and found["window"] == 1


def test_the_download_is_counted(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    data = folder / "donnees"
    (data / "gfs" / "2025").mkdir(parents=True)
    (data / "telecharger_gfs.sh").write_text(
        'FICHIERS=(\n"2025 https://a f1.grib2"\n"2025 https://b f2.grib2"\n)\n'
    )
    (data / "gfs" / "2025" / "f1.grib2").write_text("x")
    (data / "gfs" / "2025" / "f2.grib2.part").write_text("x")
    found = progress(folder)
    assert found["state"] == "running" and found["step"] == "download"
    assert found["download"] == {"done": 1, "expected": 2}


def test_the_download_is_counted_in_the_shared_data_folder(tmp_path: Path) -> None:
    folder = _folder(tmp_path / "calcul")
    shared = tmp_path / "donnees-communes"
    (shared / "gfs" / "2025").mkdir(parents=True)
    (folder / "donnees").mkdir()
    (folder / "donnees" / "telecharger_gfs.sh").write_text(
        f"DOSSIER_DONNEES={shared.as_posix()}\t# dossier commun\n"
        'FICHIERS=(\n"2025 https://a f1.grib2"\n"2025 https://b f2.grib2"\n)\n'
    )
    (shared / "gfs" / "2025" / "f1.grib2").write_text("x")
    (shared / "gfs" / "2025" / "autre.grib2").write_text("x")
    found = progress(folder)
    assert found["step"] == "download" and found["download"] == {"done": 1, "expected": 2}


def test_a_window_being_computed_gives_the_instant_reached_and_the_time_left(
    tmp_path: Path,
) -> None:
    folder = _folder(tmp_path)
    # Window 002 (computed first) done in 2 h for 24 h simulated; window 001 at 06:00 of 24 h
    (folder / "wrf" / "journaux" / "fenetres_faites.txt").write_text("fenetre 002 7200 86400\n")
    (folder / "calcul.log").write_text(
        "[2026-10-26 18:00:00 UTC] Fenetre 001 (bloc f001)\n"
        "[2026-10-26 18:00:01 UTC]   > real.exe...\n"
        "[2026-10-26 18:01:00 UTC]   > wrf.exe...\n"
    )
    (folder / "wrf" / "rsl.error.0000").write_text(
        "Timing for main: time 2025-09-30_17:59:00 on domain   1:    0.50 elapsed seconds\n"
        "Timing for main: time 2025-09-30_18:00:00 on domain   1:    0.50 elapsed seconds\n"
        "Timing for main: time 2025-09-30_18:00:00 on domain   2:    0.20 elapsed seconds\n"
    )
    found = progress(folder)
    assert found["state"] == "running" and found["step"] == "wrf"
    assert (found["window"], found["windows"], found["done"]) == (2, 2, 1)
    assert found["reached"] == "2025-09-30T18:00:00+00:00"
    # 18 h simulated left at 2 h per 24 h
    assert found["left_s"] == 18 * 3600 * 7200 // 86400


def test_a_stop_and_an_error_are_told(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    log = folder / "calcul.log"
    log.write_text(
        "[2026-10-26 18:00:01 UTC]   > geogrid.exe...\n"
        "[2026-10-26 18:00:09 UTC] ERREUR : geogrid.exe : pas de 'Successful completion'\n"
    )
    # Told as soon as the script stopped, not once the journal is old
    found = progress(folder)
    assert found["state"] == "error" and found["step"] == "geogrid"
    assert found["error"].startswith("geogrid.exe") and found["left_s"] is None
    old = time.time() - 3600
    log.write_text("[2026-10-26 18:00:01 UTC]   > metgrid.exe...\n")
    os.utime(log, (old, old))
    assert progress(folder)["state"] == "stopped"


def test_all_windows_done(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / "wrf" / "journaux" / "fenetres_faites.txt").write_text(
        "fenetre 002 7200 86400\nfenetre 001 7000 86400\n"
    )
    found = progress(folder)
    assert found["state"] == "done" and found["left_s"] is None


def test_computing_time_follows_the_calibration(reference_case: Case) -> None:
    """Horns Rev, 2 domains 100 × 100, 51 levels: 21 min per 12 h simulated on 6 cores."""
    found = estimate(reference_case)
    per_12h = found["core_seconds"] / 6 / (found["simulated_seconds"] / 43200)
    assert abs(per_12h - 21 * 60) < 1
    assert 0.5e9 < found["memory_bytes"] < 2e9
