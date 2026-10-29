"""Incremental animation rendering and configuration/result reports from existing outputs."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from owstudio.core.case.model import Case
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.points import field_at
from owstudio.core.extract.quantities import Unavailable
from owstudio.core.i18n import tr

RENDER_LOCK = threading.Lock()


class MediaCancelled(RuntimeError):
    pass


def video(
    path: Path,
    outputs: Path,
    case: Case,
    domain: int,
    variable: str,
    height_m: float | None,
    frames: list[int],
    fps: int,
    width: int,
    vectors: bool,
    cancelled: threading.Event,
    progress: Callable[[float], None],
    vmin: float | None = None,
    vmax: float | None = None,
) -> dict[str, Any]:
    """Read and encode one time at a time. Frame rate only changes playback, never model time."""
    import imageio_ffmpeg
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    files = HistoryFiles(outputs, domain)
    lat, lon = files.coordinates
    if not frames or min(frames) < 0 or max(frames) >= len(files.times):
        raise ValueError(
            tr(
                "Choose a non-empty frame range within this run's available output times",
                "Choisissez une plage d'images non vide parmi les instants de sortie de ce calcul",
            )
        )
    if vmin is None or vmax is None:
        # Fixed colour scale, sampled across the interval without keeping a year in memory.
        lows, highs = [], []
        for index in sorted(
            {frames[k] for k in np.linspace(0, len(frames) - 1, min(10, len(frames)), dtype=int)}
        ):
            if cancelled.is_set():
                raise MediaCancelled(tr("Rendering cancelled", "Rendu annulé"))
            values, _, _ = field_at(files, index, variable, height_m)
            valid = values[np.isfinite(values)]
            if valid.size:
                lows.append(float(np.nanpercentile(valid, 2)))
                highs.append(float(np.nanpercentile(valid, 98)))
        if not lows:
            raise ValueError(
                tr(
                    "No finite values for this variable and height in the selected period",
                    "Aucune valeur finie pour cette variable et cette hauteur sur la période choisie",
                )
            )
        vmin = min(lows) if vmin is None else vmin
        vmax = max(highs) if vmax is None else vmax
    if vmax <= vmin:
        vmax = vmin + 1.0
    height = int(round(width * 0.625 / 16) * 16)
    temporary = path.with_name(f".{path.stem}.partial.mp4")
    writer = imageio_ffmpeg.write_frames(
        str(temporary),
        (width, height),
        fps=fps,
        codec="libx264",
        pix_fmt_in="rgb24",
        pix_fmt_out="yuv420p",
        macro_block_size=1,
        output_params=["-movflags", "+faststart"],
    )
    methods: set[str] = set()
    warnings: set[str] = set()
    try:
        writer.send(None)
        for count, index in enumerate(frames, 1):
            if cancelled.is_set():
                raise MediaCancelled(tr("Rendering cancelled", "Rendu annulé"))
            values, unit, method = field_at(files, index, variable, height_m)
            methods.add(method)
            with RENDER_LOCK:
                figure = Figure(figsize=(width / 100, height / 100), dpi=100, facecolor="white")
                canvas = FigureCanvasAgg(figure)
                ax = figure.add_subplot(111)
                mesh = ax.pcolormesh(
                    lon, lat, values, cmap="viridis", vmin=vmin, vmax=vmax, shading="auto"
                )
                figure.colorbar(mesh, ax=ax, label=f"{variable} [{unit}]", pad=0.025)
                if vectors:
                    try:
                        u, _, _ = field_at(files, index, "u", height_m)
                        v, _, _ = field_at(files, index, "v", height_m)
                        stride = max(1, max(lat.shape) // 24)
                        sampled = (slice(None, None, stride), slice(None, None, stride))
                        ax.quiver(
                            lon[sampled],
                            lat[sampled],
                            u[sampled],
                            v[sampled],
                            color="#172b3a",
                            alpha=0.65,
                            width=0.002,
                        )
                    except Unavailable as error:
                        warnings.add(str(error))
                for farm in case.farms:
                    if not farm.turbines:
                        continue
                    ax.scatter(
                        [t.lon for t in farm.turbines],
                        [t.lat for t in farm.turbines],
                        s=12,
                        marker="^",
                        edgecolors="white",
                        linewidths=0.4,
                        label=farm.name,
                    )
                if any(f.turbines for f in case.farms):
                    ax.legend(loc="upper right", fontsize=8)
                ax.set_xlim(float(np.nanmin(lon)), float(np.nanmax(lon)))
                ax.set_ylim(float(np.nanmin(lat)), float(np.nanmax(lat)))
                ax.set_aspect(1 / max(0.1, np.cos(np.deg2rad(float(np.nanmean(lat))))))
                ax.set_xlabel("Longitude [deg]")
                ax.set_ylabel("Latitude [deg]")
                level = "surface" if height_m is None else f"{height_m:g} m AGL"
                ax.set_title(
                    f"{case.name} | d{domain:02d} | {level}\n{files.times[index].isoformat()}",
                    fontsize=10,
                )
                figure.tight_layout()
                canvas.draw()  # type: ignore[no-untyped-call]
                rgb = np.ascontiguousarray(np.asarray(canvas.buffer_rgba())[:, :, :3])  # type: ignore[no-untyped-call]
                writer.send(rgb.tobytes())
                figure.clear()
            progress(count / len(frames))
        writer.close()
        temporary.replace(path)
    except BaseException:
        try:
            writer.close()
        finally:
            temporary.unlink(missing_ok=True)
        raise
    return {
        "frames": len(frames),
        "fps": fps,
        "duration_s": len(frames) / fps,
        "first": files.times[frames[0]].isoformat(),
        "last": files.times[frames[-1]].isoformat(),
        "methods": sorted(methods),
        "warnings": sorted(warnings),
        "vmin": vmin,
        "vmax": vmax,
        "colour_scale": "2nd/98th percentile bounds sampled from up to 10 frames, clipped",
    }


def report(path: Path, case: Case, root: Path | None, lang: str = "fr") -> dict[str, Any]:
    """The PDF report of the project and of its run (see report.py)."""
    from owstudio.core.report import report as write_report

    return write_report(path, case, root, lang)
