#!/usr/bin/env bash
# Offshore Wind Studio engine installer: WRF 4.8.0 + WPS 4.7.0 (GNU, dmpar) on a Linux x86_64
# target (WSL, server, cluster). Never started automatically. No meteorological
# data, no simulation. Every stage is resumable: a later run skips what is complete.
#
#   install.sh --root DIR [--jobs N] [--mode managed|system] [--stage all|fetch|build]
#              [--geography mandatory-high|mandatory-low|existing] [--geog-path DIR]
#              [--extra ID]... [--task-id ID]
#
# managed: compilers, OpenMPI and NetCDF from conda-forge in DIR/runtime (no administrator).
# system:  the machine's own compilers, MPI and NetCDF (cluster modules loaded beforehand).
# fetch:   downloads only (login node of a cluster); build: compile and verify (compute node).
set -euo pipefail
umask 022

ENGINE_ID=wrf4.8.0-wps4.7.0-gnu13-v1
WRF_TAG=v4.8.0
WRF_COMMIT=06d4240ae989cc3e50af412bb472df3d9048783c
WPS_TAG=v4.7.0
WPS_COMMIT=5feccecd63384381b6942371c7a837f66e4ccb84
MAMBA_URL=https://api.anaconda.org/download/conda-forge/micromamba/2.3.2/linux-64/micromamba-2.3.2-0.tar.bz2
MAMBA_SHA256=5512233cdd8564a671626081026dc861537a963baa06706baab08fac6f3bb9d2
GEOG_BASE=https://www2.mmm.ucar.edu/wrf/src/wps_files

kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
root="" jobs=4 mode=managed geography=mandatory-high geog_path="" task_id=manual stage=all
extras=()
while (($#)); do
  case "$1" in
    --root) root="$2"; shift 2;;
    --jobs) jobs="$2"; shift 2;;
    --mode) mode="$2"; shift 2;;
    --stage) stage="$2"; shift 2;;
    --geography) geography="$2"; shift 2;;
    --geog-path) geog_path="$2"; shift 2;;
    --extra) extras+=("$2"); shift 2;;
    --task-id) task_id="$2"; shift 2;;
    --plan) cat "$kit/spec.json"; exit 0;;
    *) echo "Unknown option: $1" >&2; exit 2;;
  esac
done

archive_of() { # dataset id -> official archive name
  case "$1" in
    mandatory-high) echo geog_high_res_mandatory.tar.gz;;
    mandatory-low) echo geog_low_res_mandatory.tar.gz;;
    thompson28) echo geog_thompson28_chem.tar.gz;;
    noahmp) echo geog_noahmp.tar.gz;;
    lake_depth) echo lake_depth.tar.bz2;;
    gsl_gwd) echo gsl_gwd.tar.bz2;;
    topobath) echo topobath_30s.tar.bz2;;
    ssib) echo geog_ssib.tar.gz;;
    px) echo geog_px.tar.gz;;
    *) return 1;;
  esac
}

fail_usage() { echo "$1" >&2; exit 2; }
case "$root" in
  /|/usr|/usr/local|/opt|/home|/tmp|/var|/root|"") fail_usage 'Choose a dedicated absolute Linux installation folder.';;
esac
[[ "$root" == /* && ! "$root" =~ [[:space:]] && "$root" != *..* ]] || fail_usage 'Choose a dedicated absolute Linux installation folder without spaces.'
[[ "$jobs" =~ ^[0-9]+$ ]] && ((jobs >= 1 && jobs <= 128)) || fail_usage 'Invalid number of build jobs.'
[[ "$task_id" =~ ^[A-Za-z0-9-]{1,64}$ ]] || fail_usage 'Invalid task identifier.'
[[ "$mode" == managed || "$mode" == system ]] || fail_usage 'Mode must be managed or system.'
[[ "$stage" == all || "$stage" == fetch || "$stage" == build ]] || fail_usage 'Stage must be all, fetch or build.'
[[ "$geography" == existing ]] || archive_of "$geography" >/dev/null || fail_usage 'Unknown geography choice.'
for extra in "${extras[@]+"${extras[@]}"}"; do
  [[ "$extra" != mandatory-* ]] && archive_of "$extra" >/dev/null || fail_usage "Unknown geography complement: $extra"
done
if [[ "$geography" == existing ]]; then
  [[ "$geog_path" == /* && -d "$geog_path" ]] || fail_usage 'Choose an existing absolute WPS_GEOG folder.'
  ((${#extras[@]} == 0)) || fail_usage 'Complements are installed only into a geography folder managed by this installer.'
fi
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || fail_usage 'This recipe supports Linux x86_64 only.'
for tool in curl tar gzip sha256sum flock df stat python3; do
  command -v "$tool" >/dev/null || fail_usage "Missing basic tool on the target: $tool"
done

# Never take over someone else's folder, nor follow a symbolic link as the installation root
[[ ! -L "$root" ]] || fail_usage 'The installation folder must not be a symbolic link.'
if [[ -d "$root" && -n $(ls -A "$root" 2>/dev/null) ]]; then
  [[ $(cat "$root/.ows-engine-owner" 2>/dev/null) == "$ENGINE_ID" ]] || fail_usage 'This folder is not empty and does not belong to this engine installer: choose another folder.'
fi
mkdir -p "$root"
root=$(cd -- "$root" && pwd -P)
printf '%s\n' "$ENGINE_ID" > "$root/.ows-engine-owner"
exec 9>"$root/.install.lock"
flock -n 9 || { echo 'Another installation is working in this folder.' >&2; exit 3; }

task="$root/.install-runs/$task_id"
mkdir -p "$task" "$root/downloads"
status="$task/status.json"
printf '%s\n' "$$" > "$task/worker.pid"
progress=0.01 step=start detail=""

write_status() { # state
  local clean=${detail//[^A-Za-z0-9 .,:\/%_()+-]/}
  printf '{"state":"%s","progress":%s,"stage":"%s","detail":"%s","phase":"%s","pid":%s}\n' \
    "$1" "$progress" "$step" "$clean" "$stage" "$$" > "$status.tmp"
  mv -f "$status.tmp" "$status"
}
update() { progress="$1"; step="$2"; detail="${3:-}"; write_status running; echo "[$(date -u +%H:%M:%S)] $step ${detail}"; }
cancelled() { [[ -f "$task/cancel" ]]; }
check_cancel() { if cancelled; then echo 'Cancelled.' >&2; exit 130; fi; }
finish() {
  local code=$? state=failed
  trap - EXIT
  if ((code == 0)); then state=succeeded; [[ "$stage" == fetch ]] && state=fetched; fi
  cancelled && ((code != 0)) && state=cancelled
  write_status "$state"
  exit "$code"
}
trap finish EXIT
trap 'exit 130' INT TERM HUP

gb() { awk -v b="$1" 'BEGIN { printf "%.1f GB", b / 1e9 }'; }
free_bytes() { df -Pk "$root" | awk 'NR == 2 { printf "%.0f", $4 * 1024 }'; }

## The geography sits next to the engine, in geog/ under NCAR's folder names (WPS_GEOG,
## WPS_GEOG_LOW_RES), where any engine of the machine finds it; one installed before inside the
## engine (geography/<choice>) stays where it is
geog_name() { if [[ "$1" == mandatory-low ]]; then echo WPS_GEOG_LOW_RES; else echo WPS_GEOG; fi; }
geography_folder() {
  if [[ "$geography" == existing ]]; then echo "$geog_path"
  elif [[ -f "$root/geography/$geography/.ows-geog-ready" ]]; then echo "$root/geography/$geography"
  else echo "$(dirname -- "$root")/geog/$(geog_name "$geography")"; fi
}

# ------------------------------------------------------------------- disk space
update 0.02 space-check
need=0
if [[ ! -f "$root/WRF/.ows-built" || ! -f "$root/WPS/.ows-built" ]]; then need=$((need + 6000000000)); fi
if [[ "$mode" == managed && ! -f "$root/runtime/.ows-ready" ]]; then need=$((need + 3000000000)); fi
if [[ "$geography" == mandatory-high && ! -f "$(geography_folder)/.ows-geog-ready" ]]; then need=$((need + 33000000000)); fi
if [[ "$geography" == mandatory-low && ! -f "$(geography_folder)/.ows-geog-ready" ]]; then need=$((need + 1000000000)); fi
for extra in "${extras[@]+"${extras[@]}"}"; do
  [[ -f "$root/geography/.extra-$extra" ]] || need=$((need + 6000000000))
done
free=$(free_bytes)
if ((free < need)); then
  echo "Not enough free space in $root: $(gb "$need") needed, $(gb "$free") free." >&2
  exit 4
fi

# --------------------------------------------------------------------- downloads
content_length() { curl -sIL --max-time 60 --proto '=https' "$1" | tr -d '\r' | awk 'tolower($1) == "content-length:" { n = $2 } END { print n + 0 }'; }

download() { # url target p0 p1 label
  local url=$1 target=$2 p0=$3 p1=$4 label=$5 expected size pid
  [[ -f "$target" ]] && return 0
  expected=$(content_length "$url")
  size=$(stat -c %s "$target.part" 2>/dev/null || echo 0)
  if ((expected == 0 || size < expected)); then
    curl --fail --location --retry 5 --retry-delay 15 --continue-at - --proto '=https' --tlsv1.2 \
      --speed-limit 1024 --speed-time 300 --silent --show-error --output "$target.part" "$url" &
    pid=$!
    while kill -0 "$pid" 2>/dev/null; do
      if cancelled; then kill "$pid" 2>/dev/null || true; check_cancel; fi
      size=$(stat -c %s "$target.part" 2>/dev/null || echo 0)
      if ((expected > 0)); then
        update "$(awk -v a="$p0" -v b="$p1" -v s="$size" -v e="$expected" 'BEGIN { printf "%.3f", a + (b - a) * s / e }')" "$label" "$(gb "$size") of $(gb "$expected")"
      else
        update "$p0" "$label" "$(gb "$size")"
      fi
      sleep 5
    done
    wait "$pid"
  fi
  size=$(stat -c %s "$target.part")
  if ((expected > 0 && size != expected)); then
    echo "Incomplete download of $url: $size bytes instead of $expected; it will resume on the next attempt." >&2
    exit 5
  fi
  mv -f "$target.part" "$target"
}

# ---------------------------------------------------------- managed libraries
activate_build() {
  if [[ "$mode" == managed ]]; then
    export MAMBA_ROOT_PREFIX="$root/mamba"
    set +u  # activation scripts read unset variables
    eval "$("$root/bootstrap/bin/micromamba" shell hook --shell bash --root-prefix "$MAMBA_ROOT_PREFIX")"
    micromamba activate "$root/runtime"
    set -u
    # Downloads trust the machine's own certificates (and a company proxy's, added there by IT)
    # rather than the environment's bundle, which may lack what a server or a proxy needs
    local bundle
    for bundle in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/ca-bundle.pem; do
      if [[ -s "$bundle" ]]; then export SSL_CERT_FILE="$bundle" CURL_CA_BUNDLE="$bundle" GIT_SSL_CAINFO="$bundle"; break; fi
    done
    export PATH="$root/toolchain/bin:$PATH"
    export NETCDF="$root/runtime"
    export OPAL_PREFIX="$root/runtime"
    # OpenMPI looks for ssh/rsh even on one machine; without them, it starts processes itself
    command -v ssh >/dev/null || command -v rsh >/dev/null || export OMPI_MCA_plm_rsh_agent=false
  else
    export NETCDF="${NETCDF:-$(nc-config --prefix)}"
  fi
  export WRF_DIR="$root/WRF" WRFIO_NCD_LARGE_FILE_SUPPORT=1
  export LD_LIBRARY_PATH="$NETCDF/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
}

managed_libraries() {
  [[ -f "$root/runtime/.ows-ready" ]] && return 0
  update 0.04 package-manager
  download "$MAMBA_URL" "$root/downloads/micromamba-2.3.2-0.tar.bz2" 0.04 0.05 package-manager
  printf '%s  %s\n' "$MAMBA_SHA256" "$root/downloads/micromamba-2.3.2-0.tar.bz2" | sha256sum --check --status \
    || { echo 'Micromamba checksum mismatch: the download is corrupted.' >&2; rm -f "$root/downloads/micromamba-2.3.2-0.tar.bz2"; exit 5; }
  mkdir -p "$root/bootstrap"
  # Python reads bzip2 itself: the bzip2 program, often absent without administrator rights, is not needed
  python3 -c 'import sys, tarfile; tarfile.open(sys.argv[1], "r:bz2").extract("bin/micromamba", sys.argv[2])' \
    "$root/downloads/micromamba-2.3.2-0.tar.bz2" "$root/bootstrap"
  chmod 0755 "$root/bootstrap/bin/micromamba"
  update 0.06 libraries "compilers, OpenMPI, NetCDF"
  # An environment left incomplete by an interrupted attempt is rebuilt (this folder is ours)
  rm -rf "$root/runtime"
  MAMBA_ROOT_PREFIX="$root/mamba" "$root/bootstrap/bin/micromamba" create --yes --no-rc \
    --override-channels --channel conda-forge --strict-channel-priority \
    --prefix "$root/runtime" --file "$kit/environment.yml"
  "$root/bootstrap/bin/micromamba" list --explicit --md5 --prefix "$root/runtime" > "$root/environment.lock"
  mkdir -p "$root/toolchain/bin"
  local tool source
  for tool in gcc g++ gfortran cpp ar ranlib nm ld as strip; do
    source="$root/runtime/bin/x86_64-conda-linux-gnu-$tool"
    [[ -x "$source" ]] || { echo "Managed tool missing: $source" >&2; exit 6; }
    ln -sfn "$source" "$root/toolchain/bin/$tool"
  done
  ln -sfn "$root/toolchain/bin/gcc" "$root/toolchain/bin/cc"
  ln -sfn "$root/runtime/bin/tcsh" "$root/toolchain/bin/csh"
  touch "$root/runtime/.ows-ready"
}

write_environment() {
  # Sourced by every later WPS/WRF step and Slurm job: plain variables, no activation needed
  {
    echo '#!/usr/bin/env bash'
    echo "# Offshore Wind Studio engine $ENGINE_ID ($mode libraries), generated by install.sh"
    printf 'export OWS_ENGINE_ROOT=%q\n' "$root"
    if [[ "$mode" == managed ]]; then
      printf 'export PATH=%q:"$PATH"\n' "$root/runtime/bin"
      printf 'export OPAL_PREFIX=%q\n' "$root/runtime"
      # OpenMPI looks for ssh/rsh even on one machine; without them, it starts processes itself
      echo 'command -v ssh >/dev/null || command -v rsh >/dev/null || export OMPI_MCA_plm_rsh_agent=false'
    fi
    printf 'export NETCDF=%q\n' "$NETCDF"
    printf 'export WRF_DIR=%q\n' "$root/WRF"
    echo 'export WRFIO_NCD_LARGE_FILE_SUPPORT=1'
    echo 'export LD_LIBRARY_PATH="$NETCDF/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"'
  } > "$root/env.sh.tmp"
  mv -f "$root/env.sh.tmp" "$root/env.sh"
}

# -------------------------------------------------------------------- sources
clone() { # name tag commit
  local name=$1 tag=$2 commit=$3 dir="$root/$1"
  if [[ -d "$dir" && ! -f "$dir/.ows-cloned" ]]; then rm -rf "$dir"; fi  # interrupted clone
  if [[ ! -d "$dir" ]]; then
    git clone --quiet --depth 1 --branch "$tag" --recurse-submodules --shallow-submodules \
      "https://github.com/wrf-model/$name.git" "$dir"
    [[ $(git -C "$dir" rev-parse HEAD) == "$commit" ]] || { echo "$name $tag is not the expected official commit." >&2; exit 7; }
    touch "$dir/.ows-cloned"
  fi
}

# --------------------------------------------------------------------- build
cpp_path() {
  if [[ "$mode" == managed ]]; then echo "$root/toolchain/bin/cpp"; return; fi
  if [[ -x /lib/cpp ]]; then echo /lib/cpp; return; fi
  command -v cpp || { echo 'No C preprocessor (cpp) found on the target.' >&2; exit 6; }
}

use_cpp() { # configure file: the official templates name /lib/cpp or /usr/bin/cpp
  local file=$1 cpp
  cpp=$(cpp_path)
  sed -i -E "s#^(CPP[[:space:]]*=[[:space:]]*)(/lib/cpp|/usr/bin/cpp|cpp)([[:space:]]|\$)#\1$cpp\3#" "$file"
  grep -Eq "^CPP[[:space:]]*=[[:space:]]*$cpp([[:space:]]|\$)" "$file" || { echo "Could not set the C preprocessor in $file" >&2; exit 8; }
}

adapt_csh() { # the official build scripts start with #!/bin/csh, absent from minimal Linux images
  [[ -x /bin/csh ]] && return 0
  python3 "$kit/manifest.py" adapt "$1" "$(command -v csh)"
}

compatibility() {
  update 0.22 compiler-check
  printf 'program check\n  use netcdf\n  print *, trim(nf90_inq_libvers())\nend program check\n' > "$task/check.f90"
  # shellcheck disable=SC2046
  mpif90 $(nf-config --fflags) "$task/check.f90" -o "$task/check-netcdf" $(nf-config --flibs)
  "$task/check-netcdf"
  printf 'program hello\n  use mpi\n  integer :: rank, ierr\n  call MPI_Init(ierr)\n  call MPI_Comm_rank(MPI_COMM_WORLD, rank, ierr)\n  if (rank == 0) print *, "mpi ok"\n  call MPI_Finalize(ierr)\nend program hello\n' > "$task/hello.f90"
  mpif90 "$task/hello.f90" -o "$task/mpi-hello"
  if [[ "$mode" == managed ]]; then
    mpirun --oversubscribe -np 2 "$task/mpi-hello"
  else
    mpirun -np 1 "$task/mpi-hello"
  fi
}

build_wrf() {
  [[ -f "$root/WRF/.ows-built" ]] && return 0
  update 0.30 compile-wrf "about 10 to 60 minutes"
  cd "$root/WRF"
  adapt_csh "$root/WRF"
  [[ -f configure.wrf ]] && { ./clean -a > "$task/wrf-clean.log" 2>&1 || true; }
  local menu option
  menu=$(printf -- '-1\n' | ./configure 2>&1 || true)
  option=$(printf '%s\n' "$menu" | sed -n -E 's/.*[^0-9]([0-9]+)\. \(dmpar\).*GNU \(gfortran\/gcc\).*/\1/p' | head -n 1)
  [[ -n "$option" ]] || { printf '%s\n' "$menu" | tail -n 30 >&2; echo 'GNU dmpar option not found in the WRF menu.' >&2; exit 8; }
  printf '%s\n1\n' "$option" | ./configure > "$task/wrf-configure.log" 2>&1
  grep -Eq '^DMPARALLEL[[:space:]]*=[[:space:]]*1' configure.wrf || { echo 'WRF was not configured for dmpar.' >&2; exit 8; }
  use_cpp configure.wrf
  J="-j $jobs" ./compile em_real > "$task/wrf-compile.log" 2>&1 || true
  local exe
  for exe in wrf.exe real.exe ndown.exe tc.exe; do
    [[ -x "main/$exe" ]] || { tail -n 80 "$task/wrf-compile.log" >&2; echo "WRF build failed: main/$exe missing (log: $task/wrf-compile.log)." >&2; exit 8; }
  done
  touch .ows-built
}

# Compiler variables the conda activation exports (AR, CPP, LD, CFLAGS...). make passes them on,
# with the values configure.wps gives them (AR = "ar ru", CPP = "cpp -P -traditional", LD =
# mpif90), to the configure scripts of zlib, libpng and JasPer, which then fail. Without them
# WPS builds as on a plain system: the tools come from the toolchain folder in PATH.
COMPILER_VARIABLES=(AR AS CC CPP CXX FC F77 F90 F95 GFORTRAN LD NM RANLIB STRIP OBJCOPY OBJDUMP
  READELF SIZE STRINGS ADDR2LINE ELFEDIT GCC GCC_AR GCC_NM GCC_RANLIB CXXFILT CC_FOR_BUILD
  CXX_FOR_BUILD CPP_FOR_BUILD CFLAGS CPPFLAGS CXXFLAGS FFLAGS FCFLAGS FORTRANFLAGS LDFLAGS
  LDFLAGS_LD ARFLAGS DEBUG_CFLAGS DEBUG_CPPFLAGS DEBUG_CXXFLAGS DEBUG_FFLAGS DEBUG_FCFLAGS
  DEBUG_FORTRANFLAGS)

build_wps() {
  [[ -f "$root/WPS/.ows-built" ]] && return 0
  update 0.65 compile-wps "about 5 to 15 minutes"
  cd "$root/WPS"
  adapt_csh "$root/WPS"
  [[ -f configure.wps ]] && { ./clean -a > "$task/wps-clean.log" 2>&1 || true; }
  # zlib, libpng and JasPer are rebuilt from their official state after an earlier attempt
  rm -rf grib2
  { git checkout --quiet -- external && git clean -fdxq external; } || true
  local menu option
  (
    unset "${COMPILER_VARIABLES[@]}"
    # libpng includes <zlib.h> and links -lz: the zlib WPS has just built in grib2, as the
    # system's zlib development files may be absent (no administrator account needed)
    export C_INCLUDE_PATH="$root/WPS/grib2/include${C_INCLUDE_PATH:+:$C_INCLUDE_PATH}"
    export LIBRARY_PATH="$root/WPS/grib2/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
    # GRIB2 needs JasPer's JPEG 2000 only. Its configure would enable JPEG when a libjpeg is
    # linkable (the compiler's library folder may hold one without its header), and ungrib's
    # link line has no -ljpeg: JasPer is built without JPEG, as on a system without libjpeg
    export ac_cv_lib_jpeg_jpeg_destroy=no
    menu=$(printf -- '-1\n' | ./configure --build-grib2-libs 2>&1 || true)
    option=$(printf '%s\n' "$menu" | sed -n -E 's/^ *([0-9]+)\. +Linux x86_64, gfortran +\(dmpar\) *$/\1/p' | head -n 1)
    [[ -n "$option" ]] || { printf '%s\n' "$menu" | tail -n 30 >&2; echo 'GNU dmpar option not found in the WPS menu.' >&2; exit 8; }
    printf '%s\n' "$option" | ./configure --build-grib2-libs > "$task/wps-configure.log" 2>&1
    grep -Eq '^DM_FC[[:space:]]*=[[:space:]]*mpif90' configure.wps || { echo 'WPS was not configured for dmpar.' >&2; exit 8; }
    use_cpp configure.wps
    ./compile > "$task/wps-compile.log" 2>&1 || true
  )
  local exe
  for exe in geogrid.exe ungrib.exe metgrid.exe; do
    [[ -x "$exe" ]] || { tail -n 80 "$task/wps-compile.log" >&2; echo "WPS build failed: $exe missing (log: $task/wps-compile.log)." >&2; exit 8; }
  done
  # The libraries are installed in grib2: their sources go back to the official state, so the
  # manifest lists only this installer's own adaptations
  { git checkout --quiet -- external && git clean -fdxq external; } || true
  touch .ows-built
}

# ----------------------------------------------------------------- geography
unpack() { # archive destination expected-bytes p0 p1 label
  local archive=$1 destination=$2 expected=$3 p0=$4 p1=$5 label=$6 pid size
  rm -rf "$destination"
  mkdir -p "$destination"
  python3 "$kit/manifest.py" extract "$archive" "$destination" &
  pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    if cancelled; then kill "$pid" 2>/dev/null || true; check_cancel; fi
    size=$(du -sb "$destination" 2>/dev/null | awk '{ print $1 }')
    update "$(awk -v a="$p0" -v b="$p1" -v s="${size:-0}" -v e="$expected" 'BEGIN { f = s / e; if (f > 1) f = 1; printf "%.3f", a + (b - a) * f }')" "$label" "$(gb "${size:-0}") unpacked"
    sleep 20
  done
  wait "$pid"
}


## The geography as the profile names it: geogrid joins its path and each dataset folder in 128
## characters (run_wps.sh accepts 90 at most), so a longer path gets a short link in the home folder
short_geography() {
  local folder link
  folder=$(geography_folder)
  folder=${folder%/}
  if (( ${#folder} <= 60 )); then echo "$folder"; return; fi
  link="$HOME/ows-geog-$geography"
  if [[ -L "$link" || ! -e "$link" ]] && ln -sfn "$folder" "$link" && (( ${#link} <= 60 )); then
    echo "$link"
  else
    echo "$folder"
  fi
}

mandatory_geography() {
  [[ "$geography" == existing ]] && return 0
  local target archive name staging unpacked=29000000000
  target=$(geography_folder)
  [[ -f "$target/.ows-geog-ready" ]] && return 0
  [[ "$geography" == mandatory-low ]] && unpacked=500000000
  # A folder of that name that this installer did not finish is never replaced
  if [[ -e "$target" ]]; then
    echo "$target already exists and is not a geography finished by this installer: choose it as an existing geography, or move it." >&2
    exit 2
  fi
  name=$(archive_of "$geography")
  archive="$root/downloads/$name"
  # Unpacked next to its place: moved there in one step, on the same disk
  staging="$(dirname -- "$target")/.unpack-$geography"
  mkdir -p "$(dirname -- "$target")"
  download "$GEOG_BASE/$name" "$archive" 0.40 0.55 geography-download
  unpack "$archive" "$staging" "$unpacked" 0.55 0.62 geography-unpack
  python3 "$kit/manifest.py" adopt-geography "$staging" "$target"
  sha256sum "$archive" | awk '{ print $1 }' > "$target/.ows-geog-ready"
  rm -rf "$staging"
  rm -f "$archive"  # the unpacked data are kept; the archive would only use space
}

complements() {
  local extra name archive target staging
  target=$(geography_folder)
  for extra in "${extras[@]+"${extras[@]}"}"; do
    [[ -f "$root/geography/.extra-$extra" ]] && continue
    name=$(archive_of "$extra")
    archive="$root/downloads/$name"
    download "$GEOG_BASE/$name" "$archive" 0.62 0.64 "complement-$extra"
    staging="$(dirname -- "$target")/.unpack-$extra"
    mkdir -p "$root/geography"
    unpack "$archive" "$staging" 1000000000 0.64 0.66 "complement-$extra"
    python3 "$kit/manifest.py" merge-geography "$staging" "$target" > "$root/geography/.extra-$extra"
    rm -rf "$staging"
    rm -f "$archive"
  done
}

# ---------------------------------------------------------------------- run
if [[ "$mode" == managed ]]; then
  managed_libraries
else
  update 0.04 site-libraries
  for tool in gcc gfortran cpp mpicc mpif90 mpirun nc-config nf-config python3 git make perl m4 csh; do
    command -v "$tool" >/dev/null || { echo "Not available on the target: $tool. Load the site modules (compilers, MPI, NetCDF) or choose managed libraries." >&2; exit 6; }
  done
fi
check_cancel
if [[ "$stage" != build ]]; then
  update 0.15 sources "official WRF $WRF_TAG and WPS $WPS_TAG"
  if [[ "$mode" == managed ]]; then activate_build; fi
  clone WRF "$WRF_TAG" "$WRF_COMMIT"
  clone WPS "$WPS_TAG" "$WPS_COMMIT"
  check_cancel
  mandatory_geography
  complements
  check_cancel
fi
if [[ "$stage" != fetch ]]; then
  [[ -f "$root/WRF/.ows-cloned" && -f "$root/WPS/.ows-cloned" ]] || { echo 'The sources are not downloaded yet: run the fetch stage first.' >&2; exit 7; }
  activate_build
  [[ -f "$NETCDF/include/netcdf.inc" && -f "$NETCDF/include/netcdf.h" ]] || { echo "NetCDF C and Fortran must share $NETCDF/include (netcdf.h and netcdf.inc)." >&2; exit 6; }
  write_environment
  compatibility
  check_cancel
  build_wrf
  check_cancel
  build_wps
  check_cancel
  update 0.95 verify
  mkdir -p "$(dirname -- "$root")/donnees"
  python3 "$kit/manifest.py" record "$root" "$kit" "$(short_geography)" "$geography" "$mode" "${extras[*]+"${extras[*]}"}" > "$task/manifest.json"
  (source "$root/env.sh"; python3 "$kit/manifest.py" verify "$root" "$kit") > "$task/manifest.json"
  update 1.0 verified
  echo "Engine installed and verified in $root"
else
  update 0.70 fetched "downloads complete; compilation follows"
fi
