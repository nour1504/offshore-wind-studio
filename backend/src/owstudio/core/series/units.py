"""Unit conversions used when importing series into the common format.

Only conversions that are exact or conventional are offered; anything else is refused with an
error rather than guessed.
"""

from collections.abc import Callable

import numpy as np

from owstudio.core.i18n import tr

# Spellings seen in data files, mapped to one canonical spelling
ALIASES: dict[str, str] = {
    "m/s": "m s-1", "ms-1": "m s-1", "m.s-1": "m s-1", "m s^-1": "m s-1", "mps": "m s-1",
    "km/h": "km h-1", "kmh": "km h-1", "kph": "km h-1",
    "kn": "kt", "knot": "kt", "knots": "kt", "kts": "kt",
    "mph": "mi h-1",
    "k": "K", "kelvin": "K",
    "c": "degC", "°c": "degC", "degc": "degC", "celsius": "degC", "deg c": "degC",
    "f": "degF", "°f": "degF", "degf": "degF",
    "pa": "Pa", "hpa": "hPa", "mbar": "hPa", "mb": "hPa", "kpa": "kPa", "bar": "bar",
    "deg": "deg", "°": "deg", "degree": "deg", "degrees": "deg", "rad": "rad", "radian": "rad",
    "w": "W", "kw": "kW", "mw": "MW", "gw": "GW",
    "wh": "Wh", "kwh": "kWh", "mwh": "MWh", "gwh": "GWh",
    "%": "%", "percent": "%", "1": "1", "-": "1", "fraction": "1",
    "m": "m", "km": "km", "ft": "ft", "feet": "ft",
    "kg/m3": "kg m-3", "kg m-3": "kg m-3", "kg.m-3": "kg m-3",
    "w/m2": "W m-2", "w m-2": "W m-2", "w.m-2": "W m-2",
    "m2/s2": "m2 s-2", "m2 s-2": "m2 s-2", "m^2/s^2": "m2 s-2",
    "kg/kg": "kg kg-1", "g/kg": "g kg-1",
    "mm": "mm",
}  # fmt: skip


def canonical(unit: str) -> str:
    text = unit.strip()
    return ALIASES.get(text.lower(), text)


Converter = Callable[[np.ndarray], np.ndarray]

# (from, to) -> function; each family has one base unit and factors or offsets to it
_LINEAR: dict[str, tuple[str, float]] = {
    "m s-1": ("m s-1", 1.0), "km h-1": ("m s-1", 1 / 3.6), "kt": ("m s-1", 1852 / 3600), "mi h-1": ("m s-1", 0.44704),
    "Pa": ("Pa", 1.0), "hPa": ("Pa", 100.0), "kPa": ("Pa", 1000.0), "bar": ("Pa", 1e5),
    "W": ("W", 1.0), "kW": ("W", 1e3), "MW": ("W", 1e6), "GW": ("W", 1e9),
    "Wh": ("Wh", 1.0), "kWh": ("Wh", 1e3), "MWh": ("Wh", 1e6), "GWh": ("Wh", 1e9),
    "m": ("m", 1.0), "km": ("m", 1e3), "ft": ("m", 0.3048),
    "%": ("1", 0.01), "1": ("1", 1.0),
    "deg": ("deg", 1.0), "rad": ("deg", 180 / np.pi),
    "kg kg-1": ("kg kg-1", 1.0), "g kg-1": ("kg kg-1", 1e-3),
}  # fmt: skip


def _to_kelvin(unit: str) -> Converter | None:
    return {
        "K": lambda x: x,
        "degC": lambda x: x + 273.15,
        "degF": lambda x: (x - 32.0) * 5.0 / 9.0 + 273.15,
    }.get(unit)


def _from_kelvin(unit: str) -> Converter | None:
    return {
        "K": lambda x: x,
        "degC": lambda x: x - 273.15,
        "degF": lambda x: (x - 273.15) * 9.0 / 5.0 + 32.0,
    }.get(unit)


class UnitError(ValueError):
    pass


def converter(source: str, target: str) -> Converter:
    """A function converting values from ``source`` to ``target`` units; raises UnitError."""
    a, b = canonical(source), canonical(target)
    if a == b:
        return lambda x: x
    to_k, from_k = _to_kelvin(a), _from_kelvin(b)
    if to_k is not None and from_k is not None:
        return lambda x: from_k(to_k(x))
    if a in _LINEAR and b in _LINEAR and _LINEAR[a][0] == _LINEAR[b][0]:
        factor = _LINEAR[a][1] / _LINEAR[b][1]
        return lambda x: x * factor
    raise UnitError(
        tr(
            f"Cannot convert {source!r} to {target!r}",
            f"Impossible de convertir {source!r} en {target!r}",
        )
    )


def convert(values: np.ndarray, source: str, target: str) -> np.ndarray:
    return converter(source, target)(np.asarray(values, dtype=float))


def known(unit: str) -> bool:
    u = canonical(unit)
    return u in _LINEAR or _to_kelvin(u) is not None
