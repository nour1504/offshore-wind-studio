"""Builds the folder and ZIP to send to a user: only the installers (Windows setup, Linux .deb
and .run) and LISEZ-MOI.txt, with their SHA256 written in the LISEZ-MOI and checked in both
copies.

Run after packaging/build.ps1 and packaging/build-linux.ps1:

    backend/.venv/Scripts/python.exe packaging/make_distribution.py

It writes, next to the repository: "Offshore Wind Studio - A envoyer" and its ZIP.
"""

import hashlib
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
VERSION = next(
    line.split('"')[1]
    for line in (REPO / "backend" / "src" / "owstudio" / "__init__.py")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.startswith("__version__")
)
SETUP = REPO / "dist" / "installer" / f"OffshoreWindStudio-{VERSION}-setup.exe"
# Linux installers, built by packaging/build-linux.ps1
DEB = REPO / "dist" / "linux" / f"offshore-wind-studio_{VERSION}_amd64.deb"
RUN = REPO / "dist" / "linux" / f"OffshoreWindStudio-{VERSION}-linux-setup.run"
INSTALLERS = [SETUP, DEB, RUN]
# Example projects to send with them (exported by the application into dist/projects)
PROJECTS = sorted((REPO / "dist" / "projects").glob("*.owstudio.zip"))
FOLDER = ROOT / "Offshore Wind Studio - A envoyer"
ARCHIVE = ROOT / "Offshore Wind Studio - A envoyer.zip"
TEMPLATE = Path(__file__).with_name("LISEZ-MOI-envoi.txt")

# Validation status of this version, inserted in the LISEZ-MOI
STATE = """Cette version prépare les fichiers et scripts WPS/WRF et analyse les résultats
importés. Le logiciel ne lance pas les simulations lui-même.
Scripts vérifiés avec de faux programmes WPS/WRF, et import vérifié avec de petits
fichiers synthétiques. Cela ne valide pas une étude météo réelle.
L'installation du logiciel a été vérifiée sous Windows 11, Debian 13 et Debian 10
minimal, ainsi que la compilation du moteur sous Windows/WSL et Linux. Ces essais ne garantissent pas tous les postes Scibian ou les clusters.
À valider : étude réelle ERA5/SST, environnement du cluster, PC Scibian et proxy
d'entreprise. Chaque cluster exige ses propres chemins, modules et ressources."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def recycle_previous(path: Path) -> None:
    """Replace only the two known distribution artifacts, preserving them in the Recycle Bin."""
    if path.resolve() not in (FOLDER.resolve(), ARCHIVE.resolve()) or path.parent.resolve() != ROOT.resolve():
        raise ValueError(f"Unexpected distribution target: {path}")
    if not path.exists():
        return
    if os.name != "nt":
        raise RuntimeError(f"Move the previous distribution aside before replacing it: {path}")
    script = """$ErrorActionPreference='Stop'
Add-Type -AssemblyName Microsoft.VisualBasic
$previous = [Environment]::GetEnvironmentVariable('OWS_PREVIOUS_DISTRIBUTION')
if ([IO.Directory]::Exists($previous)) {
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory($previous, 'OnlyErrorDialogs', 'SendToRecycleBin')
} else {
  [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($previous, 'OnlyErrorDialogs', 'SendToRecycleBin')
}
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, "OWS_PREVIOUS_DISTRIBUTION": str(path.resolve())},
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True,
    )


def main() -> None:
    missing = [path.name for path in INSTALLERS if not path.is_file()]
    assert not missing, f"Build them first (build.ps1, build-linux.ps1): {missing}"
    hashes = {path.name: sha256(path) for path in [*INSTALLERS, *PROJECTS]}
    projects = "\n".join(f"  {path.name}" for path in PROJECTS) or "  (aucun)"
    text = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("{VERSION}", VERSION)
        .replace("{ETAT}", STATE)
        .replace("{PROJETS}", projects)
        .replace("{SHA256}", "\n".join(f"{name}\n  {digest}" for name, digest in hashes.items()))
    )
    assert "{" not in text, "a placeholder of the LISEZ-MOI was not filled"
    readme = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8-sig")

    # The folder holds only the installers, example projects and LISEZ-MOI: refuse anything else
    if FOLDER.exists():
        unexpected = [
            p.name
            for p in FOLDER.iterdir()
            if p.name != "LISEZ-MOI.txt"
            and not p.name.startswith(("OffshoreWindStudio-", "offshore-wind-studio_"))
            and not p.name.endswith(".owstudio.zip")
        ]
        assert not unexpected, f"Unexpected files in the folder to send: {unexpected}"
    # Finish and verify the replacement before touching the previous delivery.
    with tempfile.TemporaryDirectory(prefix="ows-delivery-", dir=ROOT) as staging:
        staged_folder = Path(staging) / "delivery"
        staged_archive = Path(staging) / "delivery.zip"
        assert staged_folder.resolve().is_relative_to(ROOT.resolve())
        staged_folder.mkdir()
        for path in [*INSTALLERS, *PROJECTS]:
            shutil.copy2(path, staged_folder / path.name)
        (staged_folder / "LISEZ-MOI.txt").write_bytes(readme)
        with zipfile.ZipFile(staged_archive, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(staged_folder / "LISEZ-MOI.txt", "LISEZ-MOI.txt")
            for path in [*INSTALLERS, *PROJECTS]:
                info = zipfile.ZipInfo.from_file(staged_folder / path.name, path.name)
                info.compress_type = zipfile.ZIP_DEFLATED
                if path.suffix == ".run":
                    info.create_system = 3
                    info.external_attr = 0o100755 << 16
                with (staged_folder / path.name).open("rb") as source, archive.open(info, "w") as target:
                    shutil.copyfileobj(source, target, 1 << 20)
        with zipfile.ZipFile(staged_archive) as archive:
            assert sorted(archive.namelist()) == sorted(["LISEZ-MOI.txt", *hashes])
            assert archive.testzip() is None
            assert archive.read("LISEZ-MOI.txt") == readme
            for name, digest in hashes.items():
                assert sha256(staged_folder / name) == digest
                assert hashlib.sha256(archive.read(name)).hexdigest().upper() == digest
        recycle_previous(FOLDER)
        recycle_previous(ARCHIVE)
        staged_folder.replace(FOLDER)
        staged_archive.replace(ARCHIVE)
    for name, digest in hashes.items():
        print(name, (FOLDER / name).stat().st_size, "bytes, SHA256", digest)
    print("zip", ARCHIVE.stat().st_size, "bytes, SHA256", sha256(ARCHIVE))


if __name__ == "__main__":
    main()
