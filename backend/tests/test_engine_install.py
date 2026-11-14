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

from owstudio.core import i18n
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
        self.verified: dict[str, Any] | None = manifest()
        # Programs of the engine that are running, and what its wrf.exe writes
        self.running: list[str] = []
        self.tslist = "yes"
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
        if "OWS_RUNNING=" in script:
            return Completed(0, "".join(f"OWS_RUNNING={name}\n" for name in self.running), "")
        if "OWS_TSLIST=" in script:
            return Completed(0, f"OWS_TSLIST={self.tslist}\n", "")
        if "status.json 2>/dev/null || true" in script:
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return Completed(
                0,
                f"{status}\nOWS_ALIVE={self.alive}\nOWS_INSTALL_LOG\n[12:00] {json.loads(status)['stage']}\n",
                "",
            )
        if "manifest.py" in script and " verify " in script:
            if self.verified is None:  # the folder holds no engine: the script's own first test
                return Completed(0, "OWS_ENGINE=absent\n", "")
            return Completed(0, json.dumps(self.verified) + "\n", "")
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
    assert sorted(linux) == [
        "environment.yml",
        "install.sh",
        "manifest.py",
        "spec.json",
        "wrf-tslist.patch",
    ]
    assert sorted(install.kit_files("windows")) == ["enable-wsl.ps1"]
    script = linux["install.sh"].decode()
    constant = lambda name: re.search(rf"^{name}=(\S+)$", script, re.MULTILINE).group(1)
    assert constant("ENGINE_ID") == ENGINE
    # The recipe's patch is in the kit, touches the files the recipe names and nothing else, and
    # is applied before WRF is compiled
    (patch,) = SPEC["wrf"]["patches"]
    text = linux[patch["file"]].decode("ascii")
    assert re.findall(r"^\+\+\+ b/(\S+)$", text, re.MULTILINE) == patch["changes"]
    assert b"\r" not in linux[patch["file"]] and not re.search(r"^\+.*[ \t]$", text, re.MULTILINE)
    run = script[script.rindex("\n  compatibility\n") :]
    assert run.index("  patch_wrf\n") < run.index("  build_wrf\n")
    assert f'patch="$kit/{patch["file"]}"' in script
    # What the application looks for in a compiled wrf.exe is what the patch writes into it
    added = "\n".join(line[1:] for line in text.splitlines() if line.startswith("+"))
    assert all(trace in added for trace in install.TSLIST_TRACES)
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
    # In French, its read-me is French, with the same command
    with i18n.using("fr"):
        french = install.export_kit(tmp_path / "kit-fr.zip")
    with zipfile.ZipFile(french) as archive:
        text = archive.read("OffshoreWindStudio-engine/LISEZ-MOI.txt").decode("utf-8")
        assert "--geography mandatory-high" in text and "paramétrisation des parcs" in text
        assert "OffshoreWindStudio-engine/README.txt" not in archive.namelist()


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


@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links of Linux")
def test_the_manifest_keeps_the_short_link_of_the_geography(
    tmp_path: Path, helper: types.ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """install.sh gives the manifest the short link of a geography folder too long for geogrid
    (short_geography); the manifest, and the profile after it, name the link, not the folder it
    points to: run_wps.sh refuses a path of more than 90 characters."""
    root, kit = tmp_path / "moteur", tmp_path / "kit"
    for name, content in install.kit_files().items():
        (kit / name).parent.mkdir(parents=True, exist_ok=True)
        (kit / name).write_bytes(content)
    spec = json.loads((kit / "spec.json").read_text())
    root.mkdir()
    folder = make_geog(root / ("x" * 80) / "geography" / "mandatory-high", ["topo_gmted2010_30s"])
    link = tmp_path / "ows-geog-mandatory-high"
    link.symlink_to(folder)

    def output(command: list[str]) -> str:
        """git as the build left it: the pinned commits, the patches applied, nothing else changed."""
        if command[-2:] == ["rev-parse", "HEAD"]:
            return str(spec["wrf" if command[2].endswith("WRF") else "wps"]["commit"])
        return ""

    helper.EXECUTABLES = []
    helper.output = output
    helper.record(root, kit, str(link), "mandatory-high", "managed", "")
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["geography"]["path"] == str(link)
    assert manifest["geography"]["datasets"] == ["topo_gmted2010_30s"]
    profile = ComputeProfile(id="p", name="P", kind="wsl", wsl_distro="Ubuntu")
    receipt = {"id": "0123456789ab", "root": str(root), "profile": profile.model_dump()}
    assert install.configured_profile(receipt, manifest).install.geog_dir == str(link)


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
    for name, content in install.kit_files().items():
        (kit / name).write_bytes(content)
    for name in helper.EXECUTABLES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        path.chmod(0o755)
    geog = make_geog(root / "geography" / "mandatory-high", ["albedo_modis"])
    answers = {"rev-parse": None, "diff": "WRF/compile\n", "patched": True}

    def output(command: list[str]) -> str:
        if "rev-parse" in command:
            return SPEC["wrf"]["commit"] if command[2].endswith("WRF") else SPEC["wps"]["commit"]
        if "diff" in command:
            return answers["diff"] if command[2].endswith("WRF") else ""
        if "apply" in command:
            # The patch comes off cleanly only from sources that hold it
            assert command[-3:] == ["--reverse", "--check", str(kit / "wrf-tslist.patch")]
            if not answers["patched"]:
                raise RuntimeError("patch does not apply")
            return ""
        return "tool 1.0"

    monkeypatch.setattr(helper, "output", output)
    monkeypatch.setattr(helper, "check_linked", lambda path: None)
    helper.record(root, kit, geog, "mandatory-high", "managed", "lake_depth")
    recorded = json.loads(capsys.readouterr().out)
    assert recorded["build_adaptations"] == ["WRF/WRF/compile"] and recorded["geography"][
        "complements"
    ] == ["lake_depth"]
    assert recorded["id"] == ENGINE and recorded["wrf_patches"] == {
        "wrf-tslist.patch": helper.digest(kit / "wrf-tslist.patch")
    }
    # A WRF compiled without the recipe's patch is not recorded as this engine
    answers["patched"] = False
    with pytest.raises(RuntimeError, match=r"built without wrf-tslist\.patch"):
        helper.record(root, kit, geog, "mandatory-high", "managed", "")
    answers["patched"] = True
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
    guard = next(s for s in target.scripts if "mkdir -p" in s)
    assert "belongs to something else" in guard and "test ! -L" in guard
    assert guard.index("belongs to something else") < guard.index("mkdir -p")
    (_local, remote, names) = target.uploads[0]
    assert remote == f"{ROOT}/installer/{receipt['id']}" and names == [
        "environment.yml",
        "install.sh",
        "manifest.py",
        "spec.json",
        "wrf-tslist.patch",
    ]
    launch = next(s for s in target.scripts if "launcher.pid" in s)
    assert (
        "--stage all" in launch
        and "--jobs 6" in launch
        and "--extra lake_depth" in launch
        and "--geography mandatory-low" in launch
        and "--fresh" not in launch
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


# ------------------------------------------- WRF's patch, reinstallation and removal

linux_only = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("bash"), reason="bash of Linux"
)


def shell_function(name: str) -> str:
    """A function of install.sh, as its text."""
    found = re.search(
        rf"^{name}\(\) \{{.*?\n\}}\n",
        install.kit_files()["install.sh"].decode(),
        re.MULTILINE | re.DOTALL,
    )
    assert found, name
    return found.group(0)


@pytest.mark.skipif(real_bash() is None or not shutil.which("git"), reason="bash and git")
def test_the_patch_is_applied_once_and_wrf_is_compiled_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """install.sh applies the kit's patch to the WRF sources before compiling them: once (a
    later run changes nothing), a WRF compiled without it is compiled again, and sources it
    does not fit stop the installation. Runs where git is (not in the build distribution)."""
    # Git as on a target: no setting of this computer (line endings, identity)
    (tmp_path / "gitconfig").write_bytes(b"[user]\n\tname = test\n\temail = test@example.org\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root, kit = tmp_path / "engine", tmp_path / "kit"
    wrf, wps = root / "WRF", root / "WPS"
    (wrf / "share").mkdir(parents=True)
    wps.mkdir()
    kit.mkdir()
    source = wrf / "share" / "wrf_timeseries.F"
    source.write_bytes(b"one\ntwo\nthree\n")
    (wps / "compile").write_bytes(b"#!/bin/csh\n")
    for tree in (wrf, wps):
        for arguments in (["init", "--quiet"], ["add", "."], ["commit", "--quiet", "-m", "tag"]):
            subprocess.run(["git", "-C", str(tree), *arguments], check=True, capture_output=True)
    source.write_bytes(b"one\ntwo\nmore outputs\nthree\n")
    made = subprocess.run(["git", "-C", str(wrf), "diff"], check=True, capture_output=True)
    (kit / "wrf-tslist.patch").write_bytes(made.stdout)
    subprocess.run(["git", "-C", str(wrf), "checkout", "--quiet", "--", "."], check=True)
    assert source.read_bytes() == b"one\ntwo\nthree\n" and b"+more outputs\n" in made.stdout

    def run(function: str) -> subprocess.CompletedProcess[str]:
        body = (
            'set -euo pipefail\nupdate() { echo "stage $2"; }\nstop_if_in_use() { echo asked; }\n'
            + shell_function(function)
            + f"root={root.as_posix()} kit={kit.as_posix()}\n{function}\n"
        )
        return subprocess.run(
            [str(real_bash()), "-c", body], capture_output=True, text=True, check=False
        )

    (wrf / ".ows-built").touch()
    (root / "engine-manifest.json").write_text("{}")
    done = run("patch_wrf")
    assert done.returncode == 0, done.stderr
    # Compiled without the outputs: asked first whether a calculation uses it, then no longer ready
    assert done.stdout.split("\n")[:2] == ["asked", "stage patch-wrf"]
    assert source.read_bytes() == b"one\ntwo\nmore outputs\nthree\n"
    assert not (wrf / ".ows-built").exists() and not (root / "engine-manifest.json").exists()
    (wrf / ".ows-built").touch()
    done = run("patch_wrf")
    assert done.returncode == 0 and done.stdout == "" and (wrf / ".ows-built").exists()
    # Sources changed by hand around those lines: nothing is applied
    source.write_bytes(b"one\nTWO\nthree\n")
    done = run("patch_wrf")
    assert done.returncode == 7 and "does not apply" in done.stderr
    assert source.read_bytes() == b"one\nTWO\nthree\n" and (wrf / ".ows-built").exists()
    # --fresh brings the official files back first: the patch fits again
    (wps / "compile").write_bytes(b"#!/usr/bin/tcsh\n")
    assert run("restore_sources").returncode == 0
    assert source.read_bytes() == b"one\ntwo\nthree\n"
    assert (wps / "compile").read_bytes() == b"#!/bin/csh\n"
    assert run("patch_wrf").returncode == 0 and b"more outputs" in source.read_bytes()


@linux_only
def test_a_folder_of_an_earlier_recipe_is_brought_to_this_one(tmp_path: Path) -> None:
    """The folder of an engine installed by an earlier recipe of the same versions is the
    installer's own (its WRF is brought to this recipe in place); a folder of anything else is
    never taken. Checked by the application before it sends the kit, and by install.sh."""
    target = FakeTarget([status("running")])
    root = tmp_path / "engine"
    request = install.InstallRequest(profile=target_profile(), root=str(root))
    install.begin(request, tmp_path / "receipts", tmp_path / "kits", FakeJob(), target)
    guard = next(s for s in target.scripts if "belongs to something else" in s)
    script = install.kit_files()["install.sh"].decode()
    block = re.search(r'^\[\[ ! -L "\$root" \]\].*?\nfi\n', script, re.MULTILINE | re.DOTALL)
    assert block
    own = (
        'set -euo pipefail\nfail_usage() { echo "$1" >&2; exit 2; }\n'
        f"ENGINE_ID={ENGINE} root={root}\n" + block.group(0)
    )

    def codes() -> tuple[int, int]:
        return tuple(  # type: ignore[return-value]
            subprocess.run(["bash", "-c", text], capture_output=True, check=False).returncode
            for text in (own, guard)
        )

    root.mkdir()
    owner = root / ".ows-engine-owner"
    owner.write_text(f"{install.family()}-v1\n")
    assert codes() == (0, 0) and owner.read_text().strip() == ENGINE
    for other in ("wrf4.7.1-wps4.6.0-gnu13-v1", f"{install.family()}-vx", f"x{ENGINE}", ""):
        owner.write_text(other + "\n")
        assert codes() == (2, 2), other
    assert install.same_family(f"{install.family()}-v1") and not install.same_family(
        "wrf4.7.1-wps4.6.0-gnu13-v1"
    )


@linux_only
def test_a_running_program_of_the_engine_stops_what_would_break_it(tmp_path: Path) -> None:
    """A calculation uses the engine while one of its programs runs: nothing is compiled again
    or removed under it."""
    from owstudio.core.engine.shells import LocalShell

    sleep = Path(shutil.which("sleep") or "/bin/sleep").resolve()
    if sleep.name != "sleep":
        pytest.skip("sleep is not a program of its own here")
    root = (tmp_path / "engine").resolve()
    program = root / "WRF" / "main" / "wrf.exe"
    program.parent.mkdir(parents=True)
    shutil.copy(sleep, program)
    (root / ".ows-engine-owner").write_text(ENGINE + "\n")
    profile = target_profile(kind="local", engine_manifest={"root": str(root)})
    in_use = "set -euo pipefail\n" + shell_function("in_use") + shell_function("stop_if_in_use")
    running = subprocess.Popen([str(program), "60"])
    try:
        seen = subprocess.run(
            ["bash", "-c", in_use + f"root={root}\nin_use\n"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert seen.stdout.split() == ["wrf.exe"]
        stopped = subprocess.run(
            ["bash", "-c", in_use + f"root={root}\nstop_if_in_use\necho went on\n"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert stopped.returncode == 3 and "The engine is running (wrf.exe)" in stopped.stderr
        assert install.running_programs(profile, str(root), LocalShell()) == ["wrf.exe"]
        with pytest.raises(install.EngineBusy, match=r"wrf\.exe"):
            install.remove_engine(profile, LocalShell())
        assert program.exists()
    finally:
        running.kill()
        running.wait()
    assert install.running_programs(profile, str(root), LocalShell()) == []
    idle = subprocess.run(
        ["bash", "-c", in_use + f"root={root}\nstop_if_in_use\necho went on\n"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert idle.stdout == "went on\n"


@linux_only
def test_removing_the_engine_keeps_the_geography_the_data_and_the_calculations(
    tmp_path: Path,
) -> None:
    from owstudio.core.engine.shells import LocalShell

    root = tmp_path / "moteur"
    for folder in ("WRF/main", "WPS", "runtime/bin", "mamba", "bootstrap", "toolchain/bin",
                   "downloads", "installer/abc", ".install-runs/abc"):  # fmt: skip
        (root / folder).mkdir(parents=True)
        (root / folder / "file").write_text("built")
    for name in ("env.sh", "engine-manifest.json", "environment.lock"):
        (root / name).write_text("built")
    assert {p.name for p in root.iterdir()} == set(install.ENGINE_PARTS)
    kept = [
        root / "geography" / "mandatory-low" / "albedo_modis" / "index",
        root / "input" / "gfs" / "2025" / "gfs.f000.grib2",
        root / "work" / "Test-WRF" / "wrf" / "wrfout_d01_2025-10-01_00:00:00",
        tmp_path / "geog" / "WPS_GEOG" / "albedo_modis" / "index",
        tmp_path / "donnees" / "era5" / "2024" / "era5-01.grib",
    ]
    for path in kept:
        path.parent.mkdir(parents=True)
        path.write_text("kept")
    (root / ".ows-engine-owner").write_text(f"{install.family()}-v1\n")
    profile = target_profile(kind="local", engine_manifest={"root": str(root)})
    install.remove_engine(profile, LocalShell())
    assert sorted(p.name for p in root.iterdir()) == [
        ".install.lock",
        ".ows-engine-owner",
        "geography",
        "input",
        "work",
    ]
    assert all(path.read_text() == "kept" for path in kept)
    # Removing again, or an engine folder already gone, is not an error
    install.remove_engine(profile, LocalShell())
    gone = target_profile(kind="local", engine_manifest={"root": str(tmp_path / "nowhere")})
    install.remove_engine(gone, LocalShell())
    # A folder the installer did not create is never emptied
    other = tmp_path / "autre"
    (other / "WRF").mkdir(parents=True)
    (other / ".ows-engine-owner").write_text("something-else\n")
    foreign = target_profile(kind="local", engine_manifest={"root": str(other)})
    with pytest.raises(RuntimeError, match="not created by the engine installer"):
        install.remove_engine(foreign, LocalShell())
    assert (other / "WRF").is_dir()
    with pytest.raises(ValueError, match="not installed by the application"):
        install.remove_engine(target_profile(kind="local"), LocalShell())


@linux_only
def test_the_outputs_of_a_wrf_are_read_in_its_program(tmp_path: Path) -> None:
    """Whether a WRF writes the outputs of the patch is read in wrf.exe itself: an engine built
    by hand with them counts, an engine without them does not, whatever its manifest says."""
    from owstudio.core.engine.shells import LocalShell

    wrf = tmp_path / "WRF"
    (wrf / "main").mkdir(parents=True)
    profile = target_profile(kind="local")
    profile.install.wrf_dir = str(wrf)
    assert install.tslist_outputs(profile, LocalShell()) == "absent"
    program = wrf / "main" / "wrf.exe"
    program.write_bytes(b"\x7fELF\x00(i2,f13.6,i5,i5,i5,1x,14(f13.5,1x))\x00\xff\x00")
    assert install.tslist_outputs(profile, LocalShell()) == "no"
    patched = b"\x7fELF\x00(i2,f13.6,i5,i5,i5,1x,18(f13.5,1x),f13.2)\x00\xfe"
    program.write_bytes(patched)
    assert install.tslist_outputs(profile, LocalShell()) == "no"  # half of the patch only
    # The patch of 0.7.4 (QKE profile): compiled again for the TKE profile
    program.write_bytes(patched + b"Failed to allocate grid%ts_qke_profile(1:\x00")
    assert install.tslist_outputs(profile, LocalShell()) == "no"
    program.write_bytes(patched + b"Failed to allocate grid%ts_tke_profile(1:\x00")
    assert install.tslist_outputs(profile, LocalShell()) == "yes"


def test_preflight_needs_a_server_only_for_what_is_still_to_download() -> None:
    """Compiling again an engine whose downloads are all there needs no network (a proxy that
    blocks GitHub, conda or NCAR does not stop it); a complement still to fetch needs NCAR."""
    probe = (
        PROBE.replace("github.com ok", "github.com 403").replace("anaconda.org ok", "anaconda.org 000")
        + "OWS_HAS=WRF/.ows-cloned\nOWS_HAS=WPS/.ows-cloned\n"
        + "OWS_HAS=geography/mandatory-high/.ows-geog-ready\nOWS_HAS=geography/.extra-lake_depth\n"
    )  # fmt: skip
    target = FakeTarget([status("queued")], probe=probe)
    there = install.InstallRequest(profile=target_profile(), extras=["lake_depth"])
    checked = install.preflight(there, target)
    assert checked["ready"] and checked["needed_bytes"] == install.NEED_BUILD
    more = install.InstallRequest(profile=target_profile(), extras=["gsl_gwd", "lake_depth"])
    checked = install.preflight(more, target)
    network = next(c for c in checked["checks"] if c["key"] == "network")
    assert network == {"status": "fail", "key": "network", "detail": "www2.mmm.ucar.edu fail"}
    assert checked["needed_bytes"] == install.NEED_BUILD + install.NEED_COMPLEMENT
    # Compiled again where they are, WRF and WPS take about the room they hold already
    built = probe + "OWS_HAS=WRF/.ows-built\nOWS_HAS=WPS/.ows-built\n"
    target.probe = built + "OWS_HELD=1090000000\n"
    again = install.InstallRequest(profile=target_profile(), extras=["lake_depth"], fresh=True)
    assert install.preflight(again, target)["needed_bytes"] == install.NEED_REBUILD
    assert install.preflight(there, target)["needed_bytes"] == 0
    # Stopped while compiling (cleaned trees), then removed: what is missing of the compiled trees
    target.probe = probe + "OWS_HELD=400000000\n"
    assert install.preflight(again, target)["needed_bytes"] == install.NEED_TREES - 400_000_000
    target.probe = probe
    assert install.preflight(again, target)["needed_bytes"] == install.NEED_TREES
    assert install.preflight(there, target)["needed_bytes"] == install.NEED_BUILD
    # Sources not downloaded yet: GitHub is needed
    target.probe = probe.replace("OWS_HAS=WPS/.ows-cloned\n", "")
    network = next(c for c in install.preflight(there, target)["checks"] if c["key"] == "network")
    assert network["detail"] == "github.com 403"
    # The folder of an earlier recipe is recognised by the probe's own test
    probed = next(s for s in target.scripts if "OWS_SYSTEM" in s)
    assert f"{install.family()}-v[0-9]*) s=ours" in probed.replace("\n        ", " ")
    assert 'grep -a -q -F -e ts_tke_profile "$r/WRF/main/wrf.exe"' in probed


def test_a_reinstallation_takes_what_the_engine_was_installed_with() -> None:
    first = {"id": "c" * 12, "root": ROOT, "options": {"jobs": 12},
             "profile": target_profile().model_dump(mode="json")}  # fmt: skip
    installed = install.configured_profile(first, manifest(mode="system"))
    installed.install.input_dir = "/data/donnees"
    installed.resources.mpi_command = "srun -n {ranks}"
    installed.install.env_setup = f"module load netcdf\nsource {ROOT}/env.sh"
    assert install.installed_jobs(installed, [{"id": "x" * 12}, first]) == 12
    assert install.installed_jobs(installed, []) is None
    order = install.reinstall_request(installed, 12)
    assert order.fresh and order.root == ROOT and order.jobs == 12
    assert order.dependency_mode == "system" and order.geography == "mandatory-low"
    # The engine's own environment line cannot be read while the engine is not there
    assert order.profile.install.env_setup == "module load netcdf"
    command = install.install_command(ROOT, "d" * 12, order.options(), "all")
    assert command.endswith(" --fresh") and "--mode system" in command
    # Once installed again, the profile has the folder and the MPI command it had
    second = {"id": "d" * 12, "root": ROOT, "options": order.options(),
              "profile": order.profile.model_dump(mode="json")}  # fmt: skip
    again = install.configured_profile(second, manifest())
    assert again.install.input_dir == "/data/donnees"
    assert again.resources.mpi_command == "srun -n {ranks}"
    assert again.install.env_setup == f"module load netcdf\nsource {ROOT}/env.sh"
    assert again.engine_manifest["installation_id"] == "d" * 12
    # Resuming a reinstallation that stopped starts it again from clean sources
    assert install.resume_request(second).fresh
    # An engine on a geography of its own is installed again on that geography
    own = manifest()
    own["geography"] = {"id": "existing", "path": "/data/WPS_GEOG", "datasets": ["albedo_modis"],
                        "complements": []}  # fmt: skip
    order = install.reinstall_request(install.configured_profile(first, own), 4)
    assert order.geography == "existing" and order.geog_path == "/data/WPS_GEOG"
    with pytest.raises(ValueError, match="not installed by the application"):
        install.reinstall_request(target_profile(), 4)


def test_an_engine_of_an_earlier_recipe_is_verified_as_what_it_is() -> None:
    """Its manifest names the recipe that built it: the same versions under another recipe
    number pass (what its WRF writes is read in wrf.exe); other versions do not."""
    target = FakeTarget([status("queued")])
    target.verified = {**manifest(), "id": f"{install.family()}-v1"}
    verified = install.verify_engine(target_profile(), ROOT, f"{ROOT}/installer/abc", target)
    assert verified["id"] == f"{install.family()}-v1"
    target.verified = {**manifest(), "id": "wrf4.7.1-wps4.6.0-gnu13-v1"}
    with pytest.raises(RuntimeError, match="does not match"):
        install.verify_engine(target_profile(), ROOT, f"{ROOT}/installer/abc", target)
    # A folder whose engine was removed, or is being compiled again: said in plain words, tested
    # before anything of the engine is read
    target.verified = None
    with pytest.raises(RuntimeError, match="No complete engine in this folder"):
        install.verify_engine(target_profile(), ROOT, f"{ROOT}/installer/abc", target)
    asked = target.scripts[-1]
    assert asked.startswith(f"[ -f {ROOT}/env.sh ] && [ -f {ROOT}/engine-manifest.json ] || ")


# ----------------------------------------------------------------------- API


def wait_for(client: Any, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        job: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    return job


def test_api_reinstalls_and_removes_the_engine_of_a_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    there = "OWS_HAS=WRF/.ows-cloned\nOWS_HAS=WPS/.ows-cloned\nOWS_HAS=WRF/.ows-built\nOWS_HAS=WPS/.ows-built\n"
    target = FakeTarget([status("running", 0.5), status("succeeded", 1.0)], probe=PROBE + there)
    monkeypatch.setattr(install, "shell_for", lambda profile: target)
    client = make_client(tmp_path)
    body = {"profile": target_profile().model_dump(mode="json"), "geography": "mandatory-low",
            "jobs": 6}  # fmt: skip
    job = wait_for(client, client.post("/api/engine/install", json=body).json()["job_id"])
    assert job["state"] == "succeeded", job

    def saved() -> dict[str, Any]:
        profiles = client.get("/api/profiles").json()["profiles"]
        return next(p for p in profiles if p["id"] == "server")

    assert saved()["engine_manifest"]["state"] == "ready"
    # What its WRF writes, read on its machine
    assert client.get("/api/engine/outputs/server").json() == {"tslist": "yes"}
    target.tslist = "no"
    assert client.get("/api/engine/outputs/server").json() == {"tslist": "no"}
    assert client.get("/api/engine/outputs/nobody").status_code == 404

    reinstall = lambda: client.post("/api/engine/reinstall", json={"profile_id": "server"})
    # Not under a calculation, and not when the machine cannot do it (its geography is to
    # download again and NCAR does not answer)
    target.running = ["real.exe", "wrf.exe"]
    answer = reinstall()
    assert answer.status_code == 409 and "real.exe, wrf.exe" in answer.json()["detail"]
    assert client.post("/api/engine/remove", json={"profile_id": "server"}).status_code == 409
    target.running = []
    answer = reinstall()
    assert answer.status_code == 422 and "www2.mmm.ucar.edu" in answer.json()["detail"]
    assert saved()["engine_manifest"]["state"] == "ready"
    assert not any("--fresh" in s for s in target.scripts)

    # A reinstallation that stops leaves the engine not ready, to resume
    target.probe += "OWS_HAS=geography/mandatory-low/.ows-geog-ready\n"
    target.statuses = [json.dumps(status("running", 0.3)), json.dumps(status("failed", 0.3))]
    job = wait_for(client, reinstall().json()["job_id"])
    assert job["state"] == "failed"
    launches = lambda: [s for s in target.scripts if "nohup setsid" in s]
    launch = launches()[-1]
    assert "--fresh" in launch and "--jobs 6" in launch and "--geography mandatory-low" in launch
    assert saved()["engine_manifest"]["state"] == "removed"
    assert saved()["engine_manifest"]["root"] == ROOT
    latest = client.get("/api/engine/installations").json()[0]
    assert latest["state"] == "failed" and latest["options"]["fresh"] is True
    target.statuses = [json.dumps(status("succeeded", 1.0))]
    resumed = client.post(f"/api/engine/installations/{latest['id']}/resume")
    assert wait_for(client, resumed.json()["job_id"])["state"] == "succeeded"
    assert len(launches()) == 3 and "--fresh" in launches()[-1]
    assert saved()["engine_manifest"]["state"] == "ready"
    assert saved()["install"]["wrf_dir"] == f"{ROOT}/WRF"

    # Removed: WRF, WPS and the libraries only, and the profile keeps what a reinstallation needs
    answer = client.post("/api/engine/remove", json={"profile_id": "server"})
    assert answer.status_code == 200
    removal = next(s for s in target.scripts if "rm -rf -- WRF WPS runtime" in s)
    assert "geography" not in removal and "donnees" not in removal and f"r={ROOT}\n" in removal
    kept = next(p for p in answer.json()["profiles"] if p["id"] == "server")
    assert kept["engine_manifest"]["state"] == "removed"
    assert kept["engine_manifest"]["geography"]["id"] == "mandatory-low"
    target.statuses = [json.dumps(status("succeeded", 1.0))]
    assert wait_for(client, reinstall().json()["job_id"])["state"] == "succeeded"
    assert saved()["engine_manifest"]["state"] == "ready"
    # A profile set by hand has no engine of the application to reinstall or remove
    manual = target_profile(id="manual", name="Manual").model_dump(mode="json")
    assert client.put("/api/profiles/manual", json=manual).status_code == 200
    for action in ("reinstall", "remove"):
        answer = client.post(f"/api/engine/{action}", json={"profile_id": "manual"})
        assert answer.status_code == 422, action
    assert client.post("/api/engine/reinstall", json={"profile_id": "nobody"}).status_code == 404


def test_a_reinstallation_is_listed_when_its_request_is_answered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The answer comes once the receipt of the installation is written: the installations read
    right after list it, so the Engine sheet shows it at once instead of « Ready » until its
    next reading (30 s later)."""
    there = "OWS_HAS=WRF/.ows-cloned\nOWS_HAS=WPS/.ows-cloned\nOWS_HAS=WRF/.ows-built\nOWS_HAS=WPS/.ows-built\n"
    target = FakeTarget([status("running", 0.5), status("succeeded", 1.0)], probe=PROBE + there)
    monkeypatch.setattr(install, "shell_for", lambda profile: target)
    client = make_client(tmp_path)
    body = {"profile": target_profile().model_dump(mode="json"), "geography": "mandatory-low",
            "jobs": 6}  # fmt: skip
    assert wait_for(client, client.post("/api/engine/install", json=body).json()["job_id"])["state"] == "succeeded"  # fmt: skip
    target.probe += "OWS_HAS=geography/mandatory-low/.ows-geog-ready\n"
    target.statuses = [json.dumps(status("succeeded", 1.0))]
    saving = install.save_receipt

    def slow(folder: Path, receipt: dict[str, Any]) -> None:
        time.sleep(0.3)
        saving(folder, receipt)

    monkeypatch.setattr(install, "save_receipt", slow)
    answer = client.post("/api/engine/reinstall", json={"profile_id": "server"})
    assert answer.status_code == 202
    latest = client.get("/api/engine/installations").json()[0]
    assert latest["job_id"] == answer.json()["job_id"] and latest["options"]["fresh"] is True
    assert wait_for(client, answer.json()["job_id"])["state"] == "succeeded"


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
