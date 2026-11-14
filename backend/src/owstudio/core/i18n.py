"""Texts shown to the user in English or French, written side by side where they are used:

    tr("The period ends before it starts.", "La période finit avant de commencer.")

The language is the requesting window's (X-OWS-Lang header or ``lang`` query), else the settings';
background work, the engine install and files written for a request follow it. The log stays in
English; tests/test_server_texts.py fails on a text in one language only.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

Lang = Literal["en", "fr"]
LANGS: tuple[Lang, ...] = ("en", "fr")

_default: Lang = "fr"
_current: ContextVar[Lang | None] = ContextVar("owstudio_lang", default=None)


def language(value: object) -> Lang | None:
    """``value`` when it names a language of the application ("fr", "fr-FR", "EN"…), else None."""
    code = str(value or "").strip().lower()[:2]
    return code if code in LANGS else None


def set_default(lang: Lang) -> None:
    """The language of the settings, used when no window asked."""
    global _default
    _default = lang


def current() -> Lang:
    return _current.get() or _default


@contextmanager
def using(lang: Lang | None) -> Iterator[None]:
    """Everything inside speaks ``lang`` (unchanged when None)."""
    token = _current.set(lang or current())
    try:
        yield
    finally:
        _current.reset(token)


def tr(en: str, fr: str) -> str:
    """The text in the current language."""
    return fr if current() == "fr" else en


def num(value: float, spec: str = "g") -> str:
    """``value`` written with ``spec`` (Python's format: "g", ".2f"...) and the decimal mark of
    the current language: a comma in French (0,5), as the interface writes it."""
    text = format(value, spec)
    return text.replace(".", ",") if current() == "fr" else text


def counted(count: int, one: str, many: str) -> str:
    """``one`` or ``many`` for a count, in the current language: the singular for 1, and for 0
    in French ("0 intervalle écarté", "0 intervals left out")."""
    return one if count == 1 or (count == 0 and current() == "fr") else many


def pair(first: float, second: float, spec: str = "g") -> str:
    """Two numbers side by side (latitude and longitude...): "55.5000, 7.8000"; in French, where
    the comma is the decimal mark, "55,5000 ; 7,8000"."""
    return (" ; " if current() == "fr" else ", ").join(num(v, spec) for v in (first, second))
