"""Statistics of directions (degrees, clockwise from north), which plain arithmetic gets wrong:
the mean of 350 and 10 degrees is 0, not 180."""

import numpy as np


def wrap(degrees: np.ndarray | float) -> np.ndarray:
    """Directions brought into [0, 360). (np.mod alone returns 360.0 for tiny negative values.)"""
    result: np.ndarray = np.mod(np.asarray(degrees, dtype=float), 360.0)
    return np.where(result >= 360.0, result - 360.0, result)


def difference(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    """Signed smallest difference a - b, in (-180, 180]."""
    d = np.mod(np.asarray(a, dtype=float) - np.asarray(b, dtype=float) + 180.0, 360.0) - 180.0
    return np.where(d == -180.0, 180.0, d)


def mean(directions: np.ndarray, weights: np.ndarray | None = None) -> float:
    """Mean direction of unit vectors (optionally weighted, e.g. by wind speed); NaN if empty
    or if the vectors cancel out."""
    d = np.asarray(directions, dtype=float)
    w = np.ones_like(d) if weights is None else np.asarray(weights, dtype=float)
    ok = np.isfinite(d) & np.isfinite(w)
    if not ok.any():
        return float("nan")
    rad = np.deg2rad(d[ok])
    s, c = np.sum(w[ok] * np.sin(rad)), np.sum(w[ok] * np.cos(rad))
    if np.hypot(s, c) < 1e-12 * max(np.sum(np.abs(w[ok])), 1e-300):
        return float("nan")
    return float(wrap(np.rad2deg(np.arctan2(s, c))))


def resultant_length(directions: np.ndarray) -> float:
    """Mean resultant length R in [0, 1]: 1 when all directions agree, 0 when spread evenly."""
    d = np.asarray(directions, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return float("nan")
    rad = np.deg2rad(d)
    return float(np.hypot(np.mean(np.sin(rad)), np.mean(np.cos(rad))))


def std_yamartino(directions: np.ndarray) -> float:
    """Standard deviation of directions, degrees (Yamartino 1984), the usual estimator for
    wind direction."""
    d = np.asarray(directions, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return float("nan")
    rad = np.deg2rad(d)
    s, c = np.mean(np.sin(rad)), np.mean(np.cos(rad))
    epsilon = np.sqrt(max(0.0, 1.0 - (s * s + c * c)))
    return float(np.rad2deg(np.arcsin(epsilon) * (1.0 + (2.0 / np.sqrt(3.0) - 1.0) * epsilon**3)))


def from_components(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Meteorological direction (where the wind blows from) of earth-relative u (eastward) and
    v (northward) components; NaN for calm (both components exactly 0)."""
    u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
    direction = wrap(270.0 - np.rad2deg(np.arctan2(v, u)))
    return np.where((u == 0) & (v == 0), np.nan, direction)


def sector(directions: np.ndarray, sectors: int = 12) -> np.ndarray:
    """Sector index 0..sectors-1, sector 0 centred on north; -1 for missing directions."""
    d = np.asarray(directions, dtype=float)
    width = 360.0 / sectors
    index = np.floor(np.mod(d + width / 2.0, 360.0) / width)
    return np.where(np.isfinite(d), index, -1).astype(int)
