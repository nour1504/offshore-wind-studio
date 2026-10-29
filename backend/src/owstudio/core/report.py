"""The PDF report of a project and of its run, laid out like the application.

    page 1  the project, its period, four key figures and the map of the mean wind at hub height
    page 2  production: the farm power over time and the energy of each farm
    page 3  wind at the centre of the farms: speed over time, wind rose, a few figures
    page 4  configuration: domains, farms, physics and method

Without imported outputs, only the cover and the configuration are written. Figures are drawn
with matplotlib in the colours of the interface; the namelists themselves are not printed (they
are in the exported files).
"""

import io
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

from owstudio import __version__
from owstudio.core.case.model import Case
from owstudio.core.energy.production import EnergyError
from owstudio.core.energy.summary import run_energy
from owstudio.core.extract.grid import OutsideGrid, locate
from owstudio.core.extract.points import point_series
from owstudio.core.method.plan import plan
from owstudio.core.postproc.results import Results

# Fewer values than this make a wind rose say nothing (every value in one or two sectors)
ROSE_MINIMUM = 100
INK, MUTED, LINE, SOFT = "#17201b", "#66736b", "#dfe6e1", "#f2f6f3"
ACCENT, ACCENT_LIGHT, REFERENCE = "#176743", "#3aad66", "#8a958e"
MONTHS = {
    "fr": [
        "janv.",
        "févr.",
        "mars",
        "avr.",
        "mai",
        "juin",
        "juil.",
        "août",
        "sept.",
        "oct.",
        "nov.",
        "déc.",
    ],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}


class Words:
    """The few words of the report, in its language."""

    def __init__(self, lang: str) -> None:
        self.fr = lang == "fr"
        self.lang = "fr" if self.fr else "en"

    def __call__(self, en: str, fr: str) -> str:
        return fr if self.fr else en

    def number(self, value: float | None, digits: int = 1) -> str:
        if value is None or not math.isfinite(value):
            return "–"
        text = f"{value:,.{digits}f}".replace(",", " ")
        return text.replace(".", ",") if self.fr else text

    def date(self, moment: datetime | pd.Timestamp, hour: bool = True) -> str:
        moment = pd.Timestamp(moment)
        day = f"{moment.day} {MONTHS[self.lang][moment.month - 1]} {moment.year}"
        return f"{day}, {moment:%H:%M}" if hour else day


# ------------------------------------------------------------------ figures


def _style() -> Any:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.edgecolor": LINE,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": LINE,
            "grid.linewidth": 0.6,
            "axes.titleweight": "bold",
            "axes.titlesize": 9.5,
            "axes.titlecolor": INK,
            "axes.titlelocation": "left",
            "legend.frameon": False,
        }
    )
    return plt


def _png(figure: Any) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=200, bbox_inches="tight", facecolor="white")
    _style().close(figure)
    return buffer.getvalue()


def _farm_centre(case: Case) -> tuple[float, float] | None:
    turbines = [t for _, t in case.active_turbines()]
    if not turbines:
        return None
    return float(np.mean([t.lat for t in turbines])), float(np.mean([t.lon for t in turbines]))


def map_figure(results: Results, number: int, words: Words) -> bytes:
    """Mean wind at hub height over the useful period on one domain, its coastline and turbines."""
    plt = _style()
    files = results._history("main", number)
    lat, lon = files.coordinates
    field = results.field("hub_wind", number, None)
    figure, axes = plt.subplots(figsize=(7.0, 5.2))
    mesh = axes.pcolormesh(lon, lat, field, cmap="viridis", shading="auto")
    if files.has("LANDMASK"):
        axes.contour(
            lon, lat, files.at_time("LANDMASK", 0), levels=[0.5], colors="white", linewidths=0.9
        )
    turbines = [t for _, t in results.case.active_turbines()]
    if turbines:
        axes.scatter(
            [t.lon for t in turbines],
            [t.lat for t in turbines],
            s=3,
            c="white",
            edgecolors=INK,
            linewidths=0.3,
            zorder=3,
        )
    axes.set_aspect(1 / math.cos(math.radians(float(np.nanmean(lat)))))
    axes.grid(False)
    axes.tick_params(labelsize=7)
    bar = figure.colorbar(
        mesh, ax=axes, orientation="horizontal", fraction=0.045, pad=0.07, aspect=40
    )
    bar.outline.set_visible(False)
    bar.set_label(
        words(
            f"Mean wind at {results.hub_height_m:.0f} m (m/s)",
            f"Vent moyen à {results.hub_height_m:.0f} m (m/s)",
        ),
        color=MUTED,
    )
    return _png(figure)


def power_figure(results: Results, words: Words) -> bytes | None:
    power = results._retained(results.farm_power())
    if power.empty:
        return None
    plt = _style()
    figure, axes = plt.subplots(figsize=(7.4, 2.9))
    axes.fill_between(power.index, power.to_numpy(), color=ACCENT_LIGHT, alpha=0.15, linewidth=0)
    axes.plot(
        power.index,
        power.to_numpy(),
        color=ACCENT,
        linewidth=1.8,
        label=words("With wakes", "Avec sillages"),
    )
    ideal = results.ideal_power()
    if ideal is not None:
        ideal = results._retained(ideal)
        axes.plot(
            ideal.index,
            ideal.to_numpy(),
            color=REFERENCE,
            linewidth=1.3,
            linestyle=(0, (5, 3)),
            label=words("Without wakes", "Sans sillages"),
        )
        axes.legend(loc="lower right")
    axes.axhline(results.installed_mw, color=MUTED, linewidth=0.8, linestyle=":")
    axes.text(
        power.index[0],
        results.installed_mw,
        words(
            f" {results.installed_mw:.0f} MW installed", f" {results.installed_mw:.0f} MW installés"
        ),
        va="bottom",
        color=MUTED,
        fontsize=7,
    )
    axes.set_ylim(0, results.installed_mw * 1.12)
    axes.set_ylabel("MW")
    axes.set_title(words("Farm power (UTC)", "Puissance des parcs (UTC)"))
    _time_axis(axes, power.index)
    return _png(figure)


def _time_axis(axes: Any, index: pd.Index) -> None:
    import matplotlib.dates as mdates

    times = pd.DatetimeIndex(index)
    hours = (times[-1] - times[0]).total_seconds() / 3600 if len(times) > 1 else 0
    axes.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M" if hours <= 48 else "%d/%m"))  # type: ignore[no-untyped-call]
    axes.margins(x=0)


def wind_figures(
    results: Results, number: int, words: Words
) -> tuple[bytes, bytes, dict[str, float]] | None:
    """Speed over time and the wind rose at hub height at the centre of the farms."""
    centre = _farm_centre(results.case)
    if centre is None:
        return None
    files = results._history("main", number)
    try:
        position = locate(*files.coordinates, *centre)
    except OutsideGrid:
        return None
    height = results.hub_height_m
    speed = point_series(files, position, "wind_speed", height, "agl", "nearest").values
    direction = point_series(files, position, "wind_direction", height, "agl", "nearest").values
    plt = _style()
    figure, axes = plt.subplots(figsize=(7.4, 2.6))
    axes.plot(speed.index, speed.to_numpy(), color=ACCENT, linewidth=1.8)
    axes.set_ylabel("m/s")
    axes.set_ylim(0, max(1.0, float(np.nanmax(speed.to_numpy())) * 1.15))
    axes.set_title(
        words(
            f"Wind at {height:.0f} m, centre of the farms (UTC)",
            f"Vent à {height:.0f} m au centre des parcs (UTC)",
        )
    )
    _time_axis(axes, speed.index)
    timeline = _png(figure)

    sectors = 12
    width = 2 * math.pi / sectors
    edges = [0, 4, 8, 12, 16, 20, math.inf]
    colours = ["#46327e", "#365c8d", "#1fa187", "#4ac16d", "#a0da39", "#fde725"]
    valid = speed.notna() & direction.notna()
    s, d = speed[valid].to_numpy(), direction[valid].to_numpy()
    index = np.floor(((d + 180 / sectors) % 360) / (360 / sectors)).astype(int)
    figure = plt.figure(figsize=(3.4, 3.4))
    axes = figure.add_subplot(projection="polar")
    axes.set_theta_zero_location("N")
    axes.set_theta_direction(-1)
    bottom = np.zeros(sectors)
    for k in range(len(edges) - 1):
        inside = (s >= edges[k]) & (s < edges[k + 1])
        share = np.bincount(index[inside], minlength=sectors) / max(1, len(s)) * 100
        label = (
            f"{edges[k]:g}–{edges[k + 1]:g}" if math.isfinite(edges[k + 1]) else f"≥ {edges[k]:g}"
        )
        axes.bar(
            np.arange(sectors) * width,
            share,
            width=width * 0.9,
            bottom=bottom,
            color=colours[k],
            edgecolor="white",
            linewidth=0.4,
            label=f"{label} m/s",
        )
        bottom += share
    axes.set_xticks(
        np.radians([0, 90, 180, 270]),
        [words("N", "N"), words("E", "E"), words("S", "S"), words("W", "O")],
    )
    axes.tick_params(labelsize=7)
    axes.set_yticklabels([])
    axes.grid(color=LINE)
    axes.spines["polar"].set_color(LINE)
    axes.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=3, fontsize=6.5)
    rose = _png(figure)
    main = float(np.argmax(bottom) * 360 / sectors) if len(s) else math.nan
    return (
        timeline,
        rose,
        {
            "mean": float(np.nanmean(s)) if len(s) else math.nan,
            "max": float(np.nanmax(s)) if len(s) else math.nan,
            "direction": main,
            "count": float(len(s)),
        },
    )


# ------------------------------------------------------------------ document


def report(path: Path, case: Case, root: Path | None, lang: str = "fr") -> dict[str, Any]:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    words = Words(lang)
    results = Results(root) if root is not None and Results.exist(root) else None
    summary = results.summary() if results else None
    energy: dict[str, Any] | None = None
    if root is not None and results is not None:
        try:
            energy = run_energy(root, case)
        except (EnergyError, FileNotFoundError):
            energy = None
    width = A4[0] - 36 * mm

    def style(
        name: str,
        size: float,
        colour: str = INK,
        bold: bool = False,
        leading: float | None = None,
        space: float = 0,
    ) -> ParagraphStyle:
        return ParagraphStyle(
            name,
            fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size,
            leading=leading or size * 1.25,
            textColor=colors.HexColor(colour),
            alignment=TA_LEFT,
            spaceAfter=space,
        )

    eyebrow = style("eyebrow", 8, MUTED, True, space=4)
    title = style("title", 26, INK, True, leading=30, space=6)
    meta = style("meta", 9.5, MUTED, space=14)
    heading = style("heading", 15, INK, True, space=10)
    label = style("label", 7.5, MUTED, True)
    value = style("value", 19, INK, True, leading=22)
    cell = style("cell", 8.5, INK)
    head = style("head", 7.5, MUTED, True)
    caption = style("caption", 7.5, MUTED, space=8)

    def text(content: str, which: ParagraphStyle) -> Paragraph:
        return Paragraph(escape(content), which)

    def image(data: bytes, fraction: float = 1.0) -> Image:
        from reportlab.lib.utils import ImageReader

        reader = ImageReader(io.BytesIO(data))
        w, h = reader.getSize()
        shown = width * fraction
        return Image(io.BytesIO(data), width=shown, height=shown * h / w)

    def table(header: list[str], rows: list[list[str]], widths: list[float]) -> Table:
        data = [[text(h, head) for h in header], *[[text(c, cell) for c in row] for row in rows]]
        item = Table(data, colWidths=[width * w for w in widths], repeatRows=1, hAlign="LEFT")
        item.setStyle(
            TableStyle(
                [
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.HexColor(INK)),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor(LINE)),
                    ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return item

    def figures_band(items: list[tuple[str, str, str]]) -> Table:
        cells = [
            [
                text(name, label),
                Paragraph(
                    f"{escape(number)} <font size=9 color='{MUTED}'>{escape(unit)}</font>", value
                ),
            ]
            for name, number, unit in items
        ]
        band = Table(
            [[cell_pair for cell_pair in cells]], colWidths=[width / len(cells)] * len(cells)
        )
        band.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(SOFT)),
                    ("LINEAFTER", (0, 0), (-2, -1), 0.6, colors.HexColor(LINE)),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        return band

    story: list[Any] = []
    turbines = len(case.active_turbines())
    installed = results.installed_mw if results else 0.0
    period = f"{words.date(case.period.start)} → {words.date(case.period.end)} UTC"
    source = {"gfs": "GFS", "era5": "ERA5"}.get(
        str(case.input_source), str(case.input_source).upper()
    )
    story.append(
        text(
            words("WRF RUN REPORT", "RAPPORT DE CALCUL WRF")
            if results
            else words("PROJECT REPORT", "RAPPORT DE PROJET"),
            eyebrow,
        )
    )
    story.append(text(case.name, title))
    story.append(
        text(
            " · ".join(
                filter(
                    None,
                    [
                        period,
                        words(f"{turbines} turbines", f"{turbines} éoliennes") if turbines else "",
                        f"{words.number(installed, 0)} MW" if installed else "",
                        source,
                    ],
                )
            ),
            meta,
        )
    )

    farm_domain = results.farm_domain if results else None
    number = farm_domain or (
        max(results.files("main")) if results and results.files("main") else None
    )

    def figure(key: str) -> float | None:
        found = summary.get(key) if summary else None
        return float(found) if isinstance(found, int | float) else None

    if figure("mean_power_mw") is not None:
        loss = figure("wake_efficiency")
        energy_mwh = figure("energy_mwh") or 0.0
        story.append(
            figures_band(
                [
                    (
                        words("Energy", "Énergie"),
                        words.number(energy_mwh / 1000, 2)
                        if energy_mwh >= 10_000
                        else words.number(energy_mwh, 0),
                        "GWh" if energy_mwh >= 10_000 else "MWh",
                    ),
                    (
                        words("Mean power", "Puissance moyenne"),
                        words.number(figure("mean_power_mw"), 1),
                        "MW",
                    ),
                    (
                        words("Capacity factor", "Facteur de charge"),
                        words.number(100 * (figure("capacity_factor") or 0.0), 1),
                        "%",
                    ),
                    (
                        words("Wake losses", "Pertes par sillage"),
                        words.number(100 * (1 - loss), 1),
                        "%",
                    )
                    if loss is not None
                    else (
                        words("Peak power", "Puissance maximale"),
                        words.number(figure("max_power_mw"), 1),
                        "MW",
                    ),
                ]
            )
        )
        story.append(Spacer(1, 14))
    if results is not None and number is not None:
        story.append(image(map_figure(results, number, words)))
        story.append(
            text(
                words(
                    f"Domain d0{number} · white line: coastline · dots: turbines",
                    f"Domaine d0{number} · trait blanc : côte · points : éoliennes",
                ),
                caption,
            )
        )

    if results is not None:
        power = power_figure(results, words)
        if power is not None or energy:
            story.append(PageBreak())
            story.append(text(words("Production", "Production"), heading))
            if power is not None:
                story.append(image(power))
                story.append(Spacer(1, 12))
            if energy:
                has_loss = any(r.get("loss_pct") is not None for r in energy["farms"])
                header = [
                    words("Farm", "Parc"),
                    words("Turbines", "Éoliennes"),
                    words("Energy (MWh)", "Énergie (MWh)"),
                    words("Mean (MW)", "Moyenne (MW)"),
                    words("Capacity factor", "Facteur de charge"),
                ]
                rows = [
                    [
                        str(r.get("name") or r.get("id")),
                        str(r.get("turbines", "")),
                        words.number(r["energy_mwh"], 1),
                        words.number(r["mean_power_mw"], 1),
                        f"{words.number(100 * (r['capacity_factor'] or 0), 1)} %",
                    ]
                    for r in energy["farms"]
                ]
                if has_loss:
                    header.append(words("Wake losses", "Pertes par sillage"))
                    for row, r in zip(rows, energy["farms"], strict=True):
                        row.append(
                            "–"
                            if r.get("loss_pct") is None
                            else f"{words.number(r['loss_pct'], 1)} %"
                        )
                story.append(
                    KeepTogether(
                        [
                            text(
                                words("Energy by farm", "Énergie par parc"),
                                style("sub", 10, INK, True, space=6),
                            ),
                            table(
                                header,
                                rows,
                                [0.3, 0.14, 0.18, 0.16, 0.22]
                                if not has_loss
                                else [0.24, 0.12, 0.16, 0.14, 0.17, 0.17],
                            ),
                        ]
                    )
                )
        wind = wind_figures(results, number, words) if number is not None else None
        if wind is not None:
            timeline, rose, figures = wind
            story.append(PageBreak())
            story.append(text(words("Wind", "Vent"), heading))
            story.append(image(timeline))
            story.append(Spacer(1, 12))
            few = figures["count"] < ROSE_MINIMUM
            shown = (
                text(
                    words(
                        f"Too few values for a wind rose: {figures['count']:.0f} ({ROSE_MINIMUM} at least)",
                        f"Trop peu de valeurs pour une rose des vents : {figures['count']:.0f} ({ROSE_MINIMUM} au moins)",
                    ),
                    caption,
                )
                if few
                else image(rose, 0.48)
            )
            side = Table(
                [[shown, figures_band_vertical(figures, words, text, label, value, width * 0.42)]],
                colWidths=[width * 0.52, width * 0.48],
            )
            side.setStyle(
                TableStyle(
                    [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]
                )
            )
            story.append(side)

    # Configuration: on a page of its own after results, right under the title without them
    story.append(PageBreak() if results else Spacer(1, 18))
    story.append(text(words("Configuration", "Configuration"), heading))
    domains = [
        [f"d{k:02d}", f"{dx / 1000:g} km", f"{d.e_we} × {d.e_sn}", str(case.grid.e_vert)]
        for k, (d, dx) in enumerate(zip(case.grid.domains, case.grid.domain_dx(), strict=True), 1)
    ]
    story.append(
        table(
            [
                words("Domain", "Domaine"),
                words("Grid spacing", "Maille"),
                words("Grid points", "Points"),
                words("Levels", "Niveaux"),
            ],
            domains,
            [0.25, 0.25, 0.25, 0.25],
        )
    )
    story.append(Spacer(1, 12))
    if case.farms:
        types = {n: t for n, t in case.turbine_types.items()}
        farms = []
        for farm in case.farms:
            models = sorted({types[t.type].name for t in farm.turbines if t.type in types}) or [
                "WRF generic 2 MW"
            ]
            farms.append(
                [
                    farm.name,
                    str(len(farm.turbines)),
                    ", ".join(models),
                    words("yes", "oui") if farm.enabled else words("no", "non"),
                ]
            )
        story.append(
            table(
                [
                    words("Farm", "Parc"),
                    words("Turbines", "Éoliennes"),
                    words("Model", "Modèle"),
                    words("Simulated", "Simulé"),
                ],
                farms,
                [0.3, 0.15, 0.4, 0.15],
            )
        )
        story.append(Spacer(1, 12))
    physics = (
        case.physics.model_dump() if hasattr(case.physics, "model_dump") else dict(case.physics)
    )

    def first(key: str) -> str:
        item = physics.get(key)
        return str(
            item[0] if isinstance(item, list) and item else item if item is not None else "–"
        )

    windows = plan(case).windows
    count = len(windows)
    useful = (
        max((w.useful_end - w.useful_start).total_seconds() / 3600 for w in windows)
        if windows
        else case.windows.useful_hours
    )
    settings = [
        [
            words("Input data", "Données d'entrée"),
            f"{source} · {case.period.interval_seconds // 3600} h",
        ],
        [words("Spin-up", "Mise en route"), f"{case.spin_up_hours:g} h"],
        [words("Windows", "Fenêtres"), f"{count} × {useful:g} h"],
        [
            words("Output interval", "Intervalle des sorties"),
            f"{case.history_interval_minutes} min",
        ],
        [
            words("Wind farm scheme", "Schéma de parcs"),
            (case.farm_scheme.scheme.upper() if case.farm_scheme else "–"),
        ],
        [words("Boundary layer", "Couche limite"), f"bl_pbl_physics = {first('bl_pbl_physics')}"],
        [
            words("Surface layer", "Couche de surface"),
            f"sf_sfclay_physics = {first('sf_sfclay_physics')}",
        ],
        [words("Microphysics", "Microphysique"), f"mp_physics = {first('mp_physics')}"],
        [
            words("Radiation", "Rayonnement"),
            f"ra_lw_physics = {first('ra_lw_physics')} · ra_sw_physics = {first('ra_sw_physics')}",
        ],
        [words("Cumulus", "Cumulus"), f"cu_physics = {first('cu_physics')}"],
    ]
    story.append(
        table([words("Setting", "Réglage"), words("Value", "Valeur")], settings, [0.4, 0.6])
    )

    def page(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(ACCENT))
        canvas.rect(0, A4[1] - 6, A4[0], 6, stroke=0, fill=1)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(18 * mm, 10 * mm, f"Offshore Wind Studio {__version__} · {case.name}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, str(document.page))
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=case.name,
        author="Offshore Wind Studio",
    )
    document.build(story, onFirstPage=page, onLaterPages=page)
    return {
        "has_energy": energy is not None,
        "run_id": root.name if root else None,
        "method": energy["method"] if energy else None,
    }


def figures_band_vertical(
    figures: dict[str, float], words: Words, text: Any, label: Any, value: Any, width: float
) -> Any:
    """The figures next to the wind rose, one under the other."""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    rows = [
        (words("Mean speed", "Vitesse moyenne"), f"{words.number(figures['mean'], 1)} m/s"),
        (words("Highest speed", "Vitesse maximale"), f"{words.number(figures['max'], 1)} m/s"),
        (
            words("Main direction", "Direction principale"),
            f"{words.number(figures['direction'], 0)}°",
        ),
        (words("Values", "Valeurs"), words.number(figures["count"], 0)),
    ]
    band = Table(
        [[text(name, label), text(number, value)] for name, number in rows],
        colWidths=[width * 0.55, width * 0.45],
    )
    band.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor(LINE)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return band
