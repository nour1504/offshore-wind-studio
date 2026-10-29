#!/usr/bin/env bash
# Prepares, once, as root, a WSL distribution used to build or test the Linux packages of
# Offshore Wind Studio. Never run it in the engine distribution.
#
#   setup-env.sh build   in OffshoreWindStudio-Build (AlmaLinux 8, glibc 2.28: what is built there
#                        runs on Debian 10 / Scibian 10 and every more recent Linux). Python 3.12
#                        comes from conda-forge through micromamba (the version pinned by the
#                        engine kit), never from the system; the project's libraries come from
#                        PyPI wheels built for glibc <= 2.28.
#   setup-env.sh test    in OffshoreWindStudio-Test (Debian):
#                        - a user without administrator rights, "tester", for the no-sudo installer;
#                        - the desktop pieces a Debian desktop has (GTK, WebKitGTK through the
#                          system python3, desktop menu tools), to test the window through
#                          WSLg;
#                        - a minimal Debian 10 (buster, glibc 2.28, the base of Scibian 10) in
#                          /srv/buster, without any desktop library, to check that the
#                          application starts there.
set -euo pipefail

build() {
    ENV_ROOT=/opt/owsbuild
    MAMBA_URL="https://api.anaconda.org/download/conda-forge/micromamba/2.3.2/linux-64/micromamba-2.3.2-0.tar.bz2"
    MAMBA_SHA256="5512233cdd8564a671626081026dc861537a963baa06706baab08fac6f3bb9d2"

    dnf -y -q install bzip2 tar gzip findutils binutils file which >/dev/null

    mkdir -p "$ENV_ROOT/bin"
    if [ ! -x "$ENV_ROOT/bin/micromamba" ]; then
        curl -fsSL "$MAMBA_URL" -o /tmp/micromamba.tar.bz2
        echo "$MAMBA_SHA256  /tmp/micromamba.tar.bz2" | sha256sum -c -
        tar -xjf /tmp/micromamba.tar.bz2 -C "$ENV_ROOT" bin/micromamba
        rm /tmp/micromamba.tar.bz2
    fi

    export MAMBA_ROOT_PREFIX="$ENV_ROOT/mamba"
    if [ ! -x "$ENV_ROOT/env/bin/python" ]; then
        "$ENV_ROOT/bin/micromamba" create -y -q -p "$ENV_ROOT/env" -c conda-forge python=3.12 pip
    fi

    PIP="$ENV_ROOT/env/bin/python -m pip"
    $PIP install -q --upgrade pip
    # Same libraries as the Windows build (backend/pyproject.toml), plus the build and test tools;
    # --only-binary keeps to prebuilt wheels, whose tags guarantee glibc compatibility
    $PIP install -q --only-binary=:all: \
        "pydantic>=2" "pyyaml>=6" "f90nml>=1.4" "numpy>=2" "pandas>=2" "xarray>=2024.1" "netCDF4>=1.7" \
        "fastapi>=0.115" "uvicorn[standard]>=0.30" "pyproj>=3.6" "matplotlib>=3.9" \
        "reportlab>=4" "imageio-ffmpeg>=0.5" "pyshp>=2.3" "shapely>=2" "psutil>=5.9" \
        "pyinstaller>=6" "pytest>=8" "httpx>=0.27" "ruff>=0.6" "mypy>=1.11" pandas-stubs types-PyYAML types-psutil
    "$ENV_ROOT/env/bin/python" --version
    $PIP list 2>/dev/null | grep -Ei "^(numpy|netcdf4|pyproj|shapely|matplotlib|pyinstaller|fastapi|pydantic) "
    echo "build environment ready in $ENV_ROOT/env"
}

test_env() {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -q
    apt-get install -y -q --no-install-recommends \
        ca-certificates curl python3 python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
        desktop-file-utils xdg-utils zenity dbus-x11 fonts-dejavu-core debootstrap file binutils >/dev/null

    id -u tester >/dev/null 2>&1 || useradd --create-home --shell /bin/bash tester

    if [ ! -x /srv/buster/bin/bash ]; then
        # Debian 10 is archived: its packages come from archive.debian.org
        debootstrap --variant=minbase buster /srv/buster http://archive.debian.org/debian >/dev/null
    fi
    chroot /srv/buster ldd --version | head -1
    echo "test environment ready"
}

case "${1:-}" in
    build) build ;;
    test) test_env ;;
    *) echo "usage: setup-env.sh build|test" >&2; exit 2 ;;
esac
