"""Automatic engine installation, tested without network, compilation or real target: the kit
and its consistency with the recipe, the target-side helper, the orchestration through a fake
target (launch, follow-up, stopped worker, cancellation, resumption) and the API.
These tests check the contracts and scripts; a real build is validated on a real target."""

import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import types
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from helpers import make_client

from owstudio.core.engine import install
from owstudio.core.engine.profiles import ComputeProfile
from owstudio.core.engine.shells import Completed, Shell

SPEC = install.spec()
ENGINE = SPEC["id"]
ROOT = f"/home/me/OffshoreWindStudioEngine/{ENGINE}"


def target_profile(**changes: Any) -> ComputeProfile:
    profile = ComputeProfile(id="server", name="Server", kind="wsl", wsl_distro="Ubuntu")
    return profile.model_copy(update=changes)


def manifest(root: str = ROOT, mode: str = "managed") -> dict[str, Any]:
    return {
        "schema": 2, "id": ENGINE, "state": "ready", "prefix": root, "wrf_version": "4.8.0", "wps_version": "4.7.0",
        "wrf_commit": SPEC["wrf"]["commit"], "wps_commit": SPEC["wps"]["commit"], "dependency_mode": mode,
        "versions": {"compiler": "GNU Fortran 13.3.0", "mpi": "mpirun (Open MPI) 4.1.6"},
        "packages": [{"name": "openmpi", "version": "4.1.6"}, {"name": "libnetcdf", "version": "4.9.2"}, {"name": "zstd", "version": "1"}],
        "executables": {"WRF/main/wrf.exe": "a" * 64, "WPS/geogrid.exe": "b" * 64},
        "geography": {"id": "mandatory-low", "path": f"{root}/geography/mandatory-low", "datasets": ["albedo_modis"], "complements": []},
    }  # fmt: skip


class FakeTarget(Shell):
    """Answers the installer's scripts like a Linux target; statuses are served in order."""

    def __init__(self, statuses: list[dict[str, Any]], alive: str = "yes", probe: str = "") -> None:
        self.statuses = [json.dumps(s) for s in statuses]
        self.alive = alive
        self.probe = probe
        self.scripts: list[str] = []
        self.uploads: list[tuple[Path, str, list[str]]] = []

    def command(self, script: str) -> list[str]:
        return ["fake", script]

    def run(self, script: str, timeout: float | None = 600) -> Completed:
        self.scripts.append(script)
        if "OWS_HOME=" in script:
            return Completed(0, "\nOWS_HOME=/home/me\n", "")
        if "OWS_SYSTEM" in script:
            return Completed(0, self.probe, "")
        if "status.json 2>/dev/null || true" in script:
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return Completed(
                0,
                f"{status}\nOWS_ALIVE={self.alive}\nOWS_INSTALL_LOG\n[12:00] {json.loads(status)['stage']}\n",
                "",
            )
        if "manifest.py" in script and " verify " in script:
            return Completed(0, json.dumps(manifest()) + "\n", "")
        return Completed(0, "", "")

    def upload(self, local: Path, remote: str) -> Completed:
        names = sorted(p.name for p in local.iterdir()) if local.is_dir() else [local.name]
        self.uploads.append((local, remote, names))
        return Completed(0, "", "")

    def download(self, remote: str, local: Path) -> Completed:
        return Completed(0, "", "")


class FakeJob:
    def __init__(self) -> None:
        self.id = "job000000001"
        self.progress = 0.0
        self.lines: list[str] = []
        self.cancelled = threading.Event()

    def write(self, line: str) -> None:
        self.lines.append(line)


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install, "POLL_SECONDS", 0.0)
    monkeypatch.setattr(install, "keep_wsl_alive", lambda *args: None)


def status(state: str, progress: float = 0.5, stage: str = "compile-wrf") -> dict[str, Any]:
    return {"state": state, "progress": progress, "stage": stage, "detail": "", "phase": "all"}


# -------------------------------------------------------------------- the kit


def test_kit_holds_only_the_recipe_and_matches_the_spec(tmp_path: Path) -> None:
    linux = install.kit_files()
    assert sorted(linux) == ["environment.yml", "install.sh", "manifest.py", "spec.json"]
    assert sorted(install.kit_files("windows")) == ["enable-wsl.ps1"]
    script = linux["install.sh"].decode()
    constant = lambda name: re.search(rf"^{name}=(\S+)$", script, re.MULTILINE).group(1)
    assert constant("ENGINE_ID") == ENGINE
    assert (
        constant("WRF_COMMIT") == SPEC["wrf"]["commit"]
        and constant("WPS_COMMIT") == SPEC["wps"]["commit"]
    )
    assert constant("WRF_TAG") == SPEC["wrf"]["tag"] and constant("WPS_TAG") == SPEC["wps"]["tag"]
    assert (
        constant("MAMBA_URL") == SPEC["micromamba"]["url"]
        and constant("MAMBA_SHA256") == SPEC["micromamba"]["sha256"]
    )
    base = constant("GEOG_BASE")
    # Every geography choice and complement of the catalogue has its official archive in the script
    for item in [*SPEC["geography"], *SPEC["complements"]]:
        if item["url"]:
            name = item["url"].removeprefix(base + "/")
            assert re.search(
                rf"^\s+{re.escape(item['id'])}\) echo {re.escape(name)};;$", script, re.MULTILINE
            ), item["id"]
    environment = yaml.safe_load(linux["environment.yml"])
    assert environment["channels"] == ["conda-forge"]
    pins = {d.split("=")[0]: d for d in environment["dependencies"]}
    assert (
        pins["openmpi"] == "openmpi=4.1.6"
        and pins["gfortran_linux-64"] == "gfortran_linux-64=13.3.0"
    )
    assert (
        pins["libnetcdf"] == "libnetcdf=4.9.2=nompi_*"
        and pins["netcdf-fortran"] == "netcdf-fortran=4.6.1=nompi_*"
    )
    # The kit is small: no binary, no geography
    assert install.catalog()["kit_bytes"] < 100_000
    # Found on a real build: conda's compiler variables, passed on by make with the values of
    # configure.wps, break the configure scripts of WPS's zlib, libpng and JasPer
    wps = script[script.index("build_wps() {") :]
    assert 'unset "${COMPILER_VARIABLES[@]}"' in wps[: wps.index("./compile")]
    # ...and libpng needs zlib.h, which a system without zlib's development files lacks
    assert 'C_INCLUDE_PATH="$root/WPS/grib2/include' in wps[: wps.index("./compile")]
    # ...and JasPer must not enable JPEG from a libjpeg ungrib does not link
    assert "export ac_cv_lib_jpeg_jpeg_destroy=no" in wps[: wps.index("./compile")]
    listed = set(re.search(r"COMPILER_VARIABLES=\(([^)]*)\)", script).group(1).split())
    assert {"AR", "CPP", "LD", "CC", "CFLAGS", "LDFLAGS"} <= listed


def real_bash() -> str | None:
    """A bash interpreter, not the WSL launcher of Windows (System32 bash.exe)."""
    for candidate in (r"C:\Program Files\Git\bin\bash.exe", shutil.which("bash")):
        if candidate and Path(candidate).is_file() and "system32" not in candidate.lower():
            return candidate
    return None


@pytest.mark.skipif(real_bash() is None, reason="bash not available")
def test_install_script_is_valid_bash(tmp_path: Path) -> None:
    (tmp_path / "install.sh").write_bytes(install.kit_files()["install.sh"])
    result = subprocess.run(
        [str(real_bash()), "-n", "install.sh"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("bash"), reason="bash of Linux")
def test_the_geography_goes_next_to_the_engine_with_a_short_link_when_long(tmp_path: Path) -> None:
    """The geography goes to geog/<NCAR name> next to the engine (one installed before inside it
    stays there); geogrid takes 128 characters for the geography and a dataset folder: a longer
    folder gets a short link in the home folder, which the profile records."""
    script = install.kit_files()["install.sh"].decode()
    place = re.search(r"geog_name\(\) \{.*?\n\}\n", script, re.DOTALL)
    short_link = re.search(r"short_geography\(\) \{.*?\n\}\n", script, re.DOTALL)
    assert place and short_link
    # Short folders of their own, as a home folder and an installation folder usually are
    import tempfile

    home = Path(tempfile.mkdtemp(prefix="h", dir="/tmp"))
    near = Path(tempfile.mkdtemp(prefix="e", dir="/tmp"))

    def short(root: Path) -> str:
        done = subprocess.run(
            [
                "bash",
                "-c",
                place.group(0)
                + short_link.group(0)
                + f"\ngeography=mandatory-low root={root}\nshort_geography",
            ],
            env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=True,
        )
        return done.stdout.strip()

    try:
        assert short(near / "moteur") == f"{near}/geog/WPS_GEOG_LOW_RES"
        far = tmp_path / ("x" * 70) / "moteur"
        (far.parent / "geog" / "WPS_GEOG_LOW_RES").mkdir(parents=True)
        link = short(far)
        assert link == f"{home}/ows-geog-mandatory-low"
        assert Path(link).resolve() == (far.parent / "geog" / "WPS_GEOG_LOW_RES").resolve()
        # A geography finished inside an engine installed before stays where it is
        old = near / "ancien" / "geography" / "mandatory-low"
        old.mkdir(parents=True)
        (old / ".ows-geog-ready").write_text("x")
        assert short(near / "ancien") == str(old)
    finally:
        shutil.rmtree(home)
        shutil.rmtree(near)


def test_exported_kit(tmp_path: Path) -> None:
    path = install.export_kit(tmp_path / "kit.zip")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        assert "OffshoreWindStudio-engine/README.txt" in names and not any(
            n.endswith(".ps1") for n in names
        )
        mode = archive.getinfo("OffshoreWindStudio-engine/install.sh").external_attr >> 16
        assert mode & 0o111
        assert b"--geography mandatory-high" in archive.read("OffshoreWindStudio-engine/README.txt")


# ------------------------------------------------------- target-side helper


@pytest.fixture
def helper() -> types.ModuleType:
    module = types.ModuleType("ows_manifest")
    code = compile(install.kit_files()["manifest.py"].decode(), "manifest.py", "exec")
    exec(code, module.__dict__)  # noqa: S102 - the helper is shipped as text
    return module


def test_extraction_stays_inside_the_destination(tmp_path: Path, helper: types.ModuleType) -> None:
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = b"x"
        info = tarfile.TarInfo("../outside.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with pytest.raises(Exception):  # noqa: B017 - the filter's or our own error
        helper.extract(archive, tmp_path / "into")
    assert not (tmp_path / "outside.txt").exists()


def make_geog(folder: Path, names: list[str]) -> Path:
    for name in names:
        target = folder / name / ("con/index" if name.startswith("orogwd") else "index")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("type=continuous\n")
    return folder


def test_geography_is_adopted_then_completed_without_replacing(
    tmp_path: Path, helper: types.ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    unpacked = tmp_path / "unpack"
    make_geog(unpacked / "WPS_GEOG_LOW_RES", ["albedo_modis", "orogwd_10m", "topo_gmted2010_30s"])
    helper.adopt_geography(unpacked, tmp_path / "geography" / "mandatory-low")
    assert json.loads(capsys.readouterr().out)["datasets"] == [
        "albedo_modis",
        "orogwd_10m",
        "topo_gmted2010_30s",
    ]
    complement = make_geog(tmp_path / "lake", ["lake_depth", "albedo_modis"])
    (complement / "albedo_modis" / "marker").write_text("new")
    helper.merge_geography(complement, tmp_path / "geography" / "mandatory-low")
    assert json.loads(capsys.readouterr().out) == {
        "added": ["lake_depth"],
        "already_present": ["albedo_modis"],
    }
    assert not (tmp_path / "geography" / "mandatory-low" / "albedo_modis" / "marker").exists()
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "readme.txt").write_text("no dataset here")
    with pytest.raises(RuntimeError, match="no WPS geography"):
        helper.adopt_geography(tmp_path / "notes", tmp_path / "other")


def test_manifest_records_and_verifies_a_build(
    tmp_path: Path,
    helper: types.ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, kit = tmp_path / "engine", tmp_path / "kit"
    kit.mkdir()
    (kit / "spec.json").write_bytes(install.kit_files()["spec.json"])
    for name in helper.EXECUTABLES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        path.chmod(0o755)
    geog = make_geog(root / "geography" / "mandatory-high", ["albedo_modis"])
    answers = {"rev-parse": None, "diff": "WRF/compile\n"}

    def output(command: list[str]) -> str:
        if "rev-parse" in command:
            return SPEC["wrf"]["commit"] if command[2].endswith("WRF") else SPEC["wps"]["commit"]
        if "diff" in command:
            return answers["diff"] if command[2].endswith("WRF") else ""
        return "tool 1.0"

    monkeypatch.setattr(helper, "output", output)
    monkeypatch.setattr(helper, "check_linked", lambda path: None)
    helper.record(root, kit, geog, "mandatory-high", "managed", "lake_depth")
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["build_adaptations"] == ["WRF/WRF/compile"] and recorded["geography"][
        "complements"
    ] == ["lake_depth"]
    helper.verify(root, kit)
    assert json.loads(capsys.readouterr().out)["geography"]["datasets"] == ["albedo_modis"]
    (root / "WRF/main/wrf.exe").write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="changed since it was built"):
        helper.verify(root, kit)


# ------------------------------------------------------------- orchestration


def test_requests_are_validated() -> None:
    with pytest.raises(ValueError, match="Unknown geography complement"):
        install.InstallRequest(profile=target_profile(), extras=["nope"])
    with pytest.raises(ValueError, match="installed by the application"):
        install.InstallRequest(
            profile=target_profile(),
            geography="existing",
            geog_path="/data/WPS_GEOG",
            extras=["lake_depth"],
        )
    with pytest.raises(ValueError, match="dedicated"):
        install.InstallRequest(profile=target_profile(), root="/usr")
    # Distributions other programs create for themselves are never used for the engine
    with pytest.raises(ValueError, match="of your own"):
        install.InstallRequest(
            profile=ComputeProfile(id="w", name="W", kind="wsl", wsl_distro="docker-desktop")
        )
    request = install.InstallRequest(profile=target_profile(), extras=["lake_depth", "lake_depth"])
    assert request.extras == ["lake_depth"]
    assert install.complements_for({"mp_physics": [28, 28], "sf_surface_physics": 2}) == [
        "thompson28"
    ]
    assert install.complements_for({"sf_lake_physics": "1", "sf_surface_physics": [4]}) == [
        "noahmp",
        "lake_depth",
    ]


PROBE = """
OWS_SYSTEM=Linux x86_64
OWS_GLIBC=2.39
OWS_CPUS=16
OWS_MEMORY_KB=65000000
OWS_MISSING=
OWS_SITE_MISSING= nc-config nf-config
OWS_PYTHON=3.12
OWS_ROOT_STATE=ours
OWS_HAS=runtime/.ows-ready
OWS_FREE=50000000000
OWS_NET=https://github.com ok
OWS_NET=https://api.anaconda.org ok
OWS_NET=https://www2.mmm.ucar.edu fail
"""


def test_preflight_reports_what_blocks_an_installation() -> None:
    target = FakeTarget([status("queued")], probe=PROBE)
    checked = install.preflight(install.InstallRequest(profile=target_profile()), target)
    by_key = {c["key"]: c for c in checked["checks"]}
    assert checked["root"] == ROOT and checked["cpus"] == 16 and checked["suggested_jobs"] == 16
    # Libraries already there: build and high-resolution geography remain
    assert checked["needed_bytes"] == install.NEED_BUILD + install.NEED_GEOGRAPHY["mandatory-high"]
    assert (
        by_key["space"]["status"] == "ok"
        and by_key["network"]["status"] == "fail"
        and not checked["ready"]
    )
    # An existing geography needs no access to NCAR; site libraries are checked in system mode
    existing = install.InstallRequest(
        profile=target_profile(),
        geography="existing",
        geog_path="/data/WPS_GEOG",
        dependency_mode="system",
    )
    checked = install.preflight(existing, target)
    by_key = {c["key"]: c for c in checked["checks"]}
    assert (
        by_key["network"]["status"] == "ok"
        and by_key["site_libraries"]["detail"] == "nc-config nf-config"
    )


def test_installation_configures_the_profile(tmp_path: Path) -> None:
    target = FakeTarget(
        [
            status("running", 0.3),
            status("running", 0.9, "verify"),
            status("succeeded", 1.0, "verified"),
        ]
    )
    profile = target_profile(
        install=target_profile().install.model_copy(update={"env_setup": "module load proxy"})
    )
    request = install.InstallRequest(
        profile=profile, geography="mandatory-low", jobs=6, extras=["lake_depth"]
    )
    job, ready = FakeJob(), []
    receipt = install.begin(request, tmp_path / "receipts", tmp_path / "kits", job, target)
    assert receipt["root"] == ROOT and receipt["state"] == "running"
    guard = next(s for s in target.scripts if ".ows-engine-owner" in s)
    assert "belongs to something else" in guard and "test ! -L" in guard
    (_local, remote, names) = target.uploads[0]
    assert remote == f"{ROOT}/installer/{receipt['id']}" and names == [
        "environment.yml",
        "install.sh",
        "manifest.py",
        "spec.json",
    ]
    launch = next(s for s in target.scripts if "launcher.pid" in s)
    assert (
        "--stage all" in launch
        and "--jobs 6" in launch
        and "--extra lake_depth" in launch
        and "--geography mandatory-low" in launch
    )
    result = install.follow(receipt, tmp_path / "receipts", job, ready.append, target)
    configured = ready[0]
    assert (
        configured.install.wrf_dir == f"{ROOT}/WRF"
        and configured.install.geog_dir == f"{ROOT}/geography/mandatory-low"
    )
    assert configured.install.env_setup == f"module load proxy\nsource {ROOT}/env.sh"
    assert configured.resources.mpi_command == "mpirun -np {ranks}"
    summary = configured.engine_manifest
    assert (
        summary["packages"] == {"openmpi": "4.1.6", "libnetcdf": "4.9.2"}
        and summary["package_count"] == 3
    )
    assert summary["kit"] == receipt["kit"] and summary["wrf_version"] == "4.8.0"
    assert result["manifest"]["root"] == ROOT
    saved = install.read_receipt(tmp_path / "receipts", receipt["id"])
    assert saved["state"] == "succeeded" and saved["options"]["extras"] == ["lake_depth"]
    assert job.progress == 1.0 and any("verify" in line for line in job.lines)
    # Installing again keeps the user's lines once and the engine's line once
    again = install.configured_profile(
        {**receipt, "profile": configured.model_dump(mode="json")}, manifest()
    )
    assert again.install.env_setup.count("source") == 1


def test_a_stopped_worker_is_reported_and_can_be_resumed(tmp_path: Path) -> None:
    target = FakeTarget([status("running", 0.3)], alive="no")
    request = install.InstallRequest(profile=target_profile())
    job = FakeJob()
    receipt = install.begin(request, tmp_path, tmp_path / "kits", job, target)
    with pytest.raises(RuntimeError, match="stopped on the target"):
        install.follow(receipt, tmp_path, job, lambda profile: None, target)
    saved = install.read_receipt(tmp_path, receipt["id"])
    assert saved["state"] == "failed"
    again = install.resume_request(saved)
    assert again.root == ROOT and again.geography == "mandatory-high"


def test_cancellation_stops_only_this_installation(tmp_path: Path) -> None:
    target = FakeTarget([status("running", 0.3)])
    receipt = install.begin(
        install.InstallRequest(profile=target_profile()),
        tmp_path,
        tmp_path / "kits",
        FakeJob(),
        target,
    )
    job = FakeJob()
    job.cancelled.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        install.follow(receipt, tmp_path, job, lambda profile: None, target)
    cancel = next(s for s in target.scripts if "/cancel" in s)
    assert f"--task-id {receipt['id']}" in cancel and 'kill -TERM -- "-$pid"' in cancel
    assert install.read_receipt(tmp_path, receipt["id"])["state"] == "cancelled"


def test_a_receipt_of_an_earlier_version_still_loads(tmp_path: Path) -> None:
    """Receipts of older versions hold SSH/Slurm profile fields that no longer exist."""
    old = target_profile().model_dump(mode="json")
    old["max_concurrent_runs"], old["clean_work_files"], old["ssh"], old["slurm"] = (
        1,
        True,
        None,
        None,
    )
    old["resources"] = {**old["resources"], "mpi_ranks": 4, "threads": 1, "walltime": "24:00:00"}
    receipt = {"id": "b" * 12, "root": ROOT, "profile": old, "state": "succeeded", "kit": "",
               "started_at": "2026-10-14T00:00:00", "options": {}}  # fmt: skip
    configured = install.configured_profile(receipt, manifest())
    assert configured.id == "server" and configured.install.wrf_dir == f"{ROOT}/WRF"


# ----------------------------------------------------------------------- API


def test_api_installs_and_registers_the_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = FakeTarget([status("running", 0.5), status("succeeded", 1.0)], probe=PROBE)
    monkeypatch.setattr(install, "shell_for", lambda profile: target)
    client = make_client(tmp_path)
    catalogue = client.get("/api/engine/catalog").json()
    assert catalogue["wrf"]["version"] == "4.8.0" and catalogue["local_folder"].endswith(
        "engine-wsl"
    )
    body = {"profile": target_profile().model_dump(mode="json"), "geography": "mandatory-low"}
    assert client.post("/api/engine/preflight", json=body).json()["cpus"] == 16
    job_id = client.post("/api/engine/install", json=body).json()["job_id"]
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            break
        time.sleep(0.02)
    assert job["state"] == "succeeded", job
    profiles = client.get("/api/profiles").json()["profiles"]
    saved = next(p for p in profiles if p["id"] == "server")
    assert (
        saved["engine_manifest"]["wps_version"] == "4.7.0"
        and saved["install"]["wps_dir"] == f"{ROOT}/WPS"
    )
    receipts = client.get("/api/engine/installations").json()
    assert receipts[0]["state"] == "succeeded" and not receipts[0]["followed"]
    assert client.post(f"/api/engine/installations/{receipts[0]['id']}/resume").status_code == 409
    assert client.post("/api/engine/complements", json={"physics": {"gwd_opt": 3}}).json() == {
        "complements": ["gsl_gwd"]
    }


def test_api_refuses_a_second_installation_of_the_same_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make_client(tmp_path)
    folder = install.receipt_folder(tmp_path / "settings.json")
    install.save_receipt(folder, {"id": "a" * 12, "root": ROOT, "profile": target_profile().model_dump(mode="json"),
                                  "state": "running", "started_at": "2026-10-14T00:00:00"})  # fmt: skip
    body = {"profile": target_profile().model_dump(mode="json")}
    answer = client.post("/api/engine/install", json=body)
    assert answer.status_code == 409 and "aaaaaaaaaaaa" in answer.json()["detail"]
    # Another profile name for the same machine is refused too: one installation per machine
    other = target_profile(id="same-pc", name="Same PC").model_dump(mode="json")
    answer = client.post("/api/engine/install", json={"profile": other})
    assert answer.status_code == 409 and "on this machine" in answer.json()["detail"]


def test_preflight_reports_a_folder_where_an_installation_works() -> None:
    target = FakeTarget(
        [status("queued")], probe=PROBE.replace("OWS_ROOT_STATE=ours", "OWS_ROOT_STATE=busy")
    )
    checked = install.preflight(install.InstallRequest(profile=target_profile()), target)
    folder = next(c for c in checked["checks"] if c["key"] == "folder")
    assert folder == {"status": "fail", "key": "folder", "detail": "busy"} and not checked["ready"]
    probe = next(s for s in target.scripts if "OWS_SYSTEM" in s)
    assert 'flock -n "$r/.install.lock" true' in probe


def test_an_existing_local_distribution_is_reused_where_it_was_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found when the installed application reused the engine: the wizard hides the folder
    once the distribution exists and sends its default folder, which holds no marker."""
    from owstudio.core.engine import local_setup

    chosen = tmp_path / "Moteur"
    (chosen / "distro").mkdir(parents=True)
    (chosen / local_setup.MARKER).write_text(json.dumps({"distro": local_setup.MANAGED_DISTRO}))
    state = {"available": True, "ready": True, "version": "2.7.12", "version_ok": True,
             "managed_exists": True, "managed_folder": str(chosen / "distro")}  # fmt: skip
    monkeypatch.setattr(local_setup.sys, "platform", "win32")
    monkeypatch.setattr(local_setup, "status", lambda: state)
    users: list[str] = []

    class Linux:
        def __init__(self, distro: str, user: str) -> None:
            users.append(user)

        def run(self, script: str, timeout: float | None = 600) -> Completed:
            return Completed(0, "/home/owstudio", "")

    monkeypatch.setattr(local_setup, "WslShell", Linux)
    default = tmp_path / "data" / "engine-wsl"
    result = local_setup.prepare(default, tmp_path / "scratch", FakeJob())
    assert result["state"] == "ready" and result["folder"] == str(chosen.resolve())
    assert users == ["root", "owstudio"] and not default.exists()
    # A distribution of that name the application did not create is never taken over
    (chosen / local_setup.MARKER).unlink()
    with pytest.raises(ValueError, match="not created by Offshore Wind Studio"):
        local_setup.prepare(default, tmp_path / "scratch", FakeJob())


@pytest.mark.skipif(sys.platform == "win32", reason="runs the move with bash on this Linux")
def test_an_engine_from_before_0_6_2_moves_its_data_next_to_it(tmp_path: Path) -> None:
    """Its downloads go from <engine>/input to the shared <parent>/donnees, without losing a
    file already there; the profile points to the new folder."""
    from owstudio.core.engine.shells import LocalShell

    root = tmp_path / "moteur"
    old = root / "input" / "gfs" / "2025"
    old.mkdir(parents=True)
    (old / "gfs.f000.grib2").write_text("old")
    (old / "gfs.f006.grib2").write_text("old")
    calculation = root / "work" / "Test-WRF" / "wrf"
    calculation.mkdir(parents=True)
    (calculation / "wrfout_d01_2025-10-01_00:00:00").write_text("old run")
    (root / "work" / "era5" / "2024").mkdir(parents=True)
    (root / "work" / "era5" / "2024" / "era5-01.grib").write_text("era5")
    shared = tmp_path / "donnees" / "gfs" / "2025"
    shared.mkdir(parents=True)
    (shared / "gfs.f006.grib2").write_text("new")
    profile = target_profile(kind="local", engine_manifest={"root": str(root)})
    profile.install.input_dir = f"{root}/input"
    assert install.old_data_folder(profile) == (f"{root}/input", f"{tmp_path}/donnees")

    moved = install.move_data_folder(profile, LocalShell())
    assert moved.install.input_dir == f"{tmp_path}/donnees"
    assert install.old_data_folder(moved) is None
    assert (shared / "gfs.f000.grib2").read_text() == "old"
    assert (shared / "gfs.f006.grib2").read_text() == "new"
    # The file both had stays in the old folder; the empty folders go
    assert (old / "gfs.f006.grib2").exists() and not (old / "gfs.f000.grib2").exists()
    # From the work folder only the downloaded data move; old calculations stay there
    assert (tmp_path / "donnees" / "era5" / "2024" / "era5-01.grib").read_text() == "era5"
    assert (calculation / "wrfout_d01_2025-10-01_00:00:00").exists()
    assert not (tmp_path / "donnees" / "Test-WRF").exists()


def test_an_engine_of_its_own_data_folder_is_not_moved() -> None:
    profile = target_profile(engine_manifest={"root": ROOT})
    profile.install.input_dir = "/data/donnees"
    assert install.old_data_folder(profile) is None
    assert install.old_data_folder(target_profile()) is None


def test_a_linux_computer_engine_is_never_reached_from_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On Windows "bash" is WSL's launcher: a command would land in the default distribution."""
    from owstudio.core.engine import shells

    monkeypatch.setattr(shells.sys, "platform", "win32")
    with pytest.raises(ValueError):
        shells.shell_for(target_profile(kind="local"))
