"""The interface speaks one language at a time: every text of a page has an English and a French
version with the same keys, the French one actually translated, and no visible sentence is
written straight into the code instead of going through the translations.

Reads the interface's sources (frontend/src); WRF's own names (namelist.input, e_vert...),
units and symbols stay as they are in both languages."""

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
pytestmark = pytest.mark.skipif(not SRC.is_dir(), reason="interface sources not present")

# A French text may equal the English one when it is a name, a symbol or WRF's own vocabulary
SAME_IN_BOTH = re.compile(
    r"^(?:[\s\d.,:;/×·+\-–—%()#{}|<>=*'\"]|km|m|s|h|min|hPa|Pa|MW|GW|kW|Go|GB|Mo|MB|UTC|WRF|WPS|GFS|ERA5|OSTIA|"
    r"Slurm|WSL|Linux|Windows|GRIB|NetCDF|CSV|JSON|YAML|ZIP|PDF|PNG|GeoJSON|tslist|wrfout|namelist|real|exe|"
    r"geogrid|ungrib|metgrid|Fitch|MAV|MYNN|Vtable|eta|dx|dy|dt|d0\d|[A-Za-z_]+_[A-Za-z0-9_]+|[A-Za-z]+\.[a-z]+)*$"
)


# Words written the same in both languages (names, and words French shares with English)
SHARED_WORDS = {
    "latitude",
    "longitude",
    "interpolation",
    "option",
    "options",
    "point",
    "points",
    "cluster",
    "offshore",
    "wind",
    "studio",
    "noaa",
    "copernicus",
    "ncep",
    "nam",
    "enable",
    "turbo",
    "français",
    "editions",
    "europe",
    "paris",
    "detail",
    "first",
    "last",
    "start",
    "end",
    "label",
    "farm",
    "lat",
    "lon",
    "ns",
    "ew",
    "we",
    "sn",
    "width",
    "height",
    "turbine",
    "tbl",
    "metgrid",
    "slurm",
    "km",
    "centre",
    "betz",
}


def same_in_both(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", re.sub(r"{[^}]*}", "", text))
    return bool(SAME_IN_BOTH.match(text)) or all(
        w.lower() in SHARED_WORDS or w.isupper() or "_" in w for w in words
    )


def _blocks(text: str) -> list[tuple[str, str]]:
    """The en and fr object literals of every defineMessages call."""
    found = []
    for start in [m.end() for m in re.finditer(r"defineMessages\(\{", text)]:
        parts: dict[str, str] = {}
        for lang in ("en", "fr"):
            m = re.compile(rf"\b{lang}:\s*\{{").search(text, start)
            if not m:
                break
            parts[lang] = _balanced(text, m.end() - 1)
            start = m.end() + len(parts[lang]) - 1
        if len(parts) == 2:
            found.append((parts["en"], parts["fr"]))
    return found


def _balanced(text: str, opening: int) -> str:
    """The object literal starting at text[opening] == "{", strings and comments skipped."""
    depth, i, quote = 0, opening, ""
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = ""
        elif c in "\"'`":
            quote = c
        elif text.startswith("//", i):
            i = text.index("\n", i)
            continue
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[opening : i + 1]
        i += 1
    raise ValueError("unbalanced object")


ENTRY = re.compile(
    r"""(?P<key>[A-Za-z_][\w]*|"[^"]+")\s*:\s*(?:(?P<open>\{)|(?P<value>"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`|'(?:[^'\\]|\\.)*'))"""
)


def _leaves(literal: str, prefix: str = "") -> dict[str, str]:
    """Every key path of a messages object, with its text."""
    out: dict[str, str] = {}
    body = literal[1:-1]
    i = 0
    while True:
        m = ENTRY.search(body, i)
        if not m:
            return out
        key = prefix + m.group("key").strip('"')
        if m.group("open"):
            inner = _balanced(body, m.start("open"))
            out.update(_leaves(inner, key + "."))
            i = m.start("open") + len(inner)
        else:
            out[key] = m.group("value")[1:-1]
            i = m.end()


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.ts*") if not p.name.endswith(".d.ts"))


def test_every_text_has_both_languages_with_the_same_keys() -> None:
    problems = []
    for path in _sources():
        for en, fr in _blocks(path.read_text(encoding="utf-8")):
            english, french = _leaves(en), _leaves(fr)
            for key in sorted(set(english) ^ set(french)):
                problems.append(
                    f"{path.relative_to(SRC)}: {key} only in {'en' if key in english else 'fr'}"
                )
    assert not problems, "\n".join(problems)


def test_french_texts_are_translated() -> None:
    problems = []
    for path in _sources():
        for en, fr in _blocks(path.read_text(encoding="utf-8")):
            english, french = _leaves(en), _leaves(fr)
            for key, text in english.items():
                if (
                    text
                    and french.get(key) == text
                    and len(re.findall(r"[A-Za-z]{3,}", text)) >= 2
                    and not same_in_both(text)
                ):
                    problems.append(f"{path.relative_to(SRC)}: {key} = {text!r} in both languages")
    assert not problems, "\n".join(problems)


# Visible text written in the code: words between JSX tags, or in a visible attribute
JSX_TEXT = re.compile(r">([^<>{}\n;=()?&]*[A-Za-zÀ-ÿ][^<>{}\n;=()?&]*)<")
VISIBLE_ATTRIBUTE = re.compile(
    r"""\b(?:label|title|placeholder|aria-label|description|alt)=["']([^"'{}]*[A-Za-zÀ-ÿ]{3,}[^"'{}]*)["']"""
)


def test_no_visible_sentence_written_in_the_code() -> None:
    problems = []
    for path in sorted(SRC.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        # Comments are not shown
        code = re.sub(
            r"/\*.*?\*/|\{/\*.*?\*/\}|^\s*//.*$", "", text, flags=re.DOTALL | re.MULTILINE
        )
        for pattern in (JSX_TEXT, VISIBLE_ATTRIBUTE):
            for m in pattern.finditer(code):
                words = m.group(1).strip()
                if len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", words)) >= 2 and not same_in_both(words):
                    problems.append(f"{path.relative_to(SRC)}: {words!r}")
    assert not problems, "\n".join(problems)
