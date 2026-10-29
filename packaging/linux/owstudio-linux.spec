# PyInstaller build of Offshore Wind Studio for Linux: one folder with the program and everything
# it needs (Python, libraries, built interface, catalogues, Vtables, help, examples). Built by
# packaging/linux/build-linux.sh on a glibc 2.28 base, so that it runs on Debian 10 / Scibian 10
# and every more recent Linux. The window comes from the system (GTK) or a browser: no web view
# toolkit is bundled. Never includes user data or simulation results.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parents[1]
PACKAGE = ROOT / "backend" / "src" / "owstudio"

datas = []
# The application's own resources: built interface, catalogues, schemas, Vtables, docs, examples
datas += [(str(p), str(Path("owstudio") / p.relative_to(PACKAGE).parent)) for p in PACKAGE.rglob("*")
          if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".py", ".pyc")]
# The Linux window is a script run by the system's own Python: shipped as a file, not compiled
datas += [(str(PACKAGE / "data" / "linux" / "window.py"), "owstudio/data/linux")]
for package in ("pyproj", "matplotlib", "reportlab", "imageio_ffmpeg", "certifi", "netCDF4", "cftime", "shapely"):
    datas += collect_data_files(package)

binaries = []
for package in ("netCDF4", "shapely", "pyproj", "imageio_ffmpeg"):
    binaries += collect_dynamic_libs(package)

hiddenimports = []
for package in ("owstudio", "uvicorn", "netCDF4", "cftime", "pyproj"):
    hiddenimports += collect_submodules(package)
hiddenimports += ["matplotlib.backends.backend_agg"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "backend" / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "IPython", "notebook", "PyQt5", "PySide6", "PyQt6", "webview", "clr", "pythonnet",
              "mypy", "mypyc", "ast_serialize", "watchfiles", "cdsapi"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OffshoreWindStudio",
    console=True,
    strip=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="OffshoreWindStudio", strip=False, upx=False)
