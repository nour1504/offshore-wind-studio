"""Texts shown to the user in the language of the interface, English or French, written side by
side where they are used:

    tr("The period ends before it starts.", "La période finit avant de commencer.")

The language is the one of the window that asked (the API sets it for each request, from the
X-OWS-Lang header or a ``lang`` query parameter), else the language of the settings: work done in
the background, the engine installation and the files written for a request follow it too.
The log stays in English. tests/test_server_texts.py fails on a text written in one language only.
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
