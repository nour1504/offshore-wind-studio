# PyInstaller build of Offshore Wind Studio: one folder with the executable and everything it
# needs (Python, libraries, the built interface, catalogues, Vtables, help topics, examples).
# Built by packaging/build.ps1; never includes user data or simulation results.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "backend" / "src" / "owstudio"

datas = []
# The application's own resources: built interface, catalogues, schemas, Vtables, docs, examples
datas += [(str(p), str(Path("owstudio") / p.relative_to(PACKAGE).parent)) for p in PACKAGE.rglob("*")
          if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".py", ".pyc")]
for package in ("pyproj", "matplotlib", "reportlab", "imageio_ffmpeg", "webview", "certifi", "netCDF4", "cftime", "shapely"):
    datas += collect_data_files(package)

binaries = []
for package in ("netCDF4", "shapely", "pyproj", "imageio_ffmpeg"):
    binaries += collect_dynamic_libs(package)

hiddenimports = []
for package in ("owstudio", "uvicorn", "netCDF4", "cftime", "pyproj"):
    hiddenimports += collect_submodules(package)
# Windows only: the other platforms of pywebview need toolkits that are not installed
hiddenimports += collect_submodules(
    "webview", filter=lambda name: not any(p in name for p in ("android", "gtk", "qt", "cocoa", "cef"))
)
hiddenimports += ["clr", "clr_loader", "pythonnet", "matplotlib.backends.backend_agg"]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "backend" / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # Development tools and libraries the application never imports (the exported scripts download
    # ERA5 with cdsapi on the compute machine; uvicorn reloading is not used)
    excludes=["tkinter", "pytest", "IPython", "notebook", "PyQt5", "PySide6", "PyQt6",
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
    icon=str(ROOT / "packaging" / "owstudio.ico"),
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="OffshoreWindStudio", upx=False)
