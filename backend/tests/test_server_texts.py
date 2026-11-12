"""Every text the server shows to the user exists in English and in French (core/i18n.py: tr), and
the exported files follow the language of the interface.

The code is read, not run: an error raised, an HTTP error, a check (Issue), a problem added to a
list shown in the interface, written as a plain sentence instead of tr("...", "..."), fails. The
log stays in English and is not read here. An error that never reaches the user may carry the
comment "# internal" on its line.
"""

import ast
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import TypeGuard

import pytest

from owstudio.core import i18n

SOURCE = Path(__file__).resolve().parents[1] / "src" / "owstudio"

# Lists whose items are shown to the user
SHOWN_LISTS = {"problems", "warnings", "notes", "issues", "errors", "messages", "missing", "flags"}
# Lists named like these (column_flags, speed_flags...) are shown too
SHOWN_SUFFIXES = ("_flags", "_notes")
# Calls whose argument (at this position) is shown to the user
SHOWN_CALLS = {
    "HTTPException": 1,
    "Issue": 1,
    "Finding": 1,
    "Turbines": 1,
    "check_same_timing": 1,
    "check_heights": 1,
    "in_unit": 3,
    # How a series was obtained, written under the charts and in the exported files
    "Computed": 2,
    "Extracted": 2,
}
# Arguments and variables holding a text shown to the user (how a result was made, why...)
SHOWN_KEYWORDS = {"detail", "message", "method", "description"}
SHOWN_NAMES = {
    "method",
    "flags",
    "reason",
    "problem",
    "hint",
    "label",
    "what",
    "where",
    "how_to_add",
}


def sentence(node: ast.AST) -> bool:
    """A text written for a reader: a string (or f-string) with at least two words."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return sentence(node.left) or sentence(node.right)
    elif isinstance(node, ast.IfExp):
        return sentence(node.body) or sentence(node.orelse)
    else:
        return False
    words = [w for w in text.replace(":", " ").split() if any(c.isalpha() for c in w)]
    return len(words) >= 2


def called(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def untranslated() -> list[str]:
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for item in shown_texts(path):
            found.append(
                f"{path.relative_to(SOURCE).as_posix()}:{item.lineno}: {lines[item.lineno - 1].strip()}"
            )
    return found


def shown_texts(path: Path) -> list[ast.AST]:
    """The sentences of a module shown to the user without tr()."""
    source = path.read_text(encoding="utf-8")
    return [item for item in shown_nodes(ast.parse(source), source.splitlines()) if sentence(item)]


def shown_nodes(tree: ast.AST, lines: list[str]) -> list[ast.AST]:
    """The texts of a module shown to the user (each item of a list, each branch of a choice),
    tr() or not."""
    result: list[ast.AST] = []
    shown: list[ast.AST] = []
    # Functions of the module that pass on a message (def error(code, message): ...): their
    # calls carry a text shown to the user at that position
    forwarding = {
        node.name: index
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        for index, argument in enumerate(node.args.args)
        if argument.arg in ("message", "detail")
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            name = called(node.exc)
            if name != "HTTPException" and node.exc.args:
                shown.append(node.exc.args[0])
        if isinstance(node, ast.Call):
            name = called(node)
            if name in SHOWN_CALLS:
                position = SHOWN_CALLS[name]
                if len(node.args) > position:
                    shown.append(node.args[position])
            if isinstance(node.func, ast.Name) and len(node.args) > forwarding.get(
                name, len(node.args)
            ):
                shown.append(node.args[forwarding[name]])
            if name not in ("Field", "FastAPI"):
                shown += [k.value for k in node.keywords if k.arg in SHOWN_KEYWORDS]
            # A list of that name, or an attribute of that name (result.problems.append(...))
            owner = node.func.value if isinstance(node.func, ast.Attribute) else None
            listed = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
            if (
                name in ("append", "extend")
                and (listed in SHOWN_LISTS or listed.endswith(SHOWN_SUFFIXES))
                and node.args
            ):
                shown.append(node.args[0])
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                # A name, an attribute, or a key of a dictionary (fiche["how_to_add"] = ...)
                if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant):
                    named = str(target.slice.value)
                else:
                    named = (
                        target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
                    )
                if named in SHOWN_NAMES | SHOWN_LISTS and node.value is not None:
                    shown.append(node.value)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in (
                    "message",
                    "detail",
                    "method",
                    "flags",
                    "notes",
                ):
                    shown.append(value)
    for node in shown:
        candidates = [node]
        while any(
            isinstance(c, ast.List | ast.Tuple | ast.IfExp | ast.ListComp | ast.GeneratorExp)
            for c in candidates
        ):
            expanded: list[ast.AST] = []
            for c in candidates:
                if isinstance(c, ast.List | ast.Tuple):
                    expanded += c.elts
                elif isinstance(c, ast.IfExp):
                    expanded += [c.body, c.orelse]
                elif isinstance(c, ast.ListComp | ast.GeneratorExp):
                    expanded.append(c.elt)
                else:
                    expanded.append(c)
            candidates = expanded
        result += [item for item in candidates if "# internal" not in lines[item.lineno - 1]]
    return result


def test_every_text_shown_by_the_server_exists_in_both_languages() -> None:
    missing = untranslated()
    assert not missing, f"{len(missing)} texts in one language only:\n" + "\n".join(missing)


def test_translations_are_complete() -> None:
    """Both texts of every tr() are written, and differ (a French text copied from the English
    one is a forgotten translation), except for technical words identical in both."""
    same_allowed = {"WPS", "WRF", "OK", "", "tslist", "Slurm"}
    problems = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and called(node) == "tr":
                if len(node.args) != 2:
                    problems.append(f"{path.name}:{node.lineno}: tr() needs English and French")
                    continue
                en, fr = node.args
                literal = en.value if isinstance(en, ast.Constant) else None
                if ast.dump(en) == ast.dump(fr) and literal not in same_allowed:
                    problems.append(f"{path.name}:{node.lineno}: same text in both languages")
    assert not problems, "\n".join(problems)


# A format giving decimals (.2f, .3g, g, e, .1%...), not .0f, an integer or a date (%d/%m/%Y)
DECIMAL_FORMAT = re.compile(
    r"^(?:.?[<>=^])?[+\- ]?z?#?0?\d*[,_]?(?:\.(?P<precision>\d+))?(?P<type>[eEfFgGn%])$"
)


def gives_decimals(spec: str) -> bool:
    match = DECIMAL_FORMAT.match(spec)
    if not match:
        return False
    return match["type"] in "eEgGn" or match["precision"] != "0"


def is_tr(node: ast.AST) -> TypeGuard[ast.Call]:
    return isinstance(node, ast.Call) and called(node) == "tr" and len(node.args) == 2


def in_french(node: ast.AST) -> Iterator[ast.AST]:
    """The parts of a text read in French: all of it but the English text of the tr() it holds."""
    yield node
    children = [node.args[1]] if is_tr(node) else list(ast.iter_child_nodes(node))
    for child in children:
        yield from in_french(child)


def english_parts(tree: ast.AST) -> set[int]:
    """The nodes of the English texts of the tr() calls of a module."""
    return {id(n) for node in ast.walk(tree) if is_tr(node) for n in ast.walk(node.args[0])}


def french_texts(tree: ast.AST) -> Iterator[ast.AST]:
    """The texts of a module read in French: the French text of each tr(), whatever its shape (an
    f-string, texts added together, a choice), and each f-string put together around a tr() piece,
    whose own values are read in French too (f"{method} {tr('to', 'à')} {height_m:g} m")."""
    english = english_parts(tree)
    for node in ast.walk(tree):
        if is_tr(node):
            yield node.args[1]
        elif (
            isinstance(node, ast.JoinedStr)
            and id(node) not in english
            and any(isinstance(v, ast.FormattedValue) and is_tr(v.value) for v in node.values)
        ):
            yield node


def is_height(value: ast.AST) -> bool:
    """A height in metres (height_m, meta.height_m): 92.5 m is written with its decimal."""
    name = value.id if isinstance(value, ast.Name) else getattr(value, "attr", "")
    return name.endswith("height_m")


def test_french_texts_write_decimals_with_a_comma() -> None:
    """A number with decimals in a French text is written by i18n.num (or i18n.pair), with
    the decimal comma of the interface (0,5 m/s); a format of its own would write a point, even
    in a text built inside the French one, in texts added together, or around a tr() piece. A
    height is such a number (« à 92,5 m »), with or without a format. Two such numbers are not
    separated by a comma: "55,5, 7,8" reads as four numbers (i18n.pair writes "55,5 ; 7,8")."""
    found = set()
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        where = path.relative_to(SOURCE).as_posix()
        for text in french_texts(tree):
            for part in in_french(text):
                if isinstance(part, ast.JoinedStr):
                    values = part.values
                    for left, between, right in zip(values, values[1:], values[2:], strict=False):
                        if (
                            isinstance(left, ast.FormattedValue)
                            and isinstance(right, ast.FormattedValue)
                            and all(
                                isinstance(v.value, ast.Call) and called(v.value) == "num"
                                for v in (left, right)
                            )
                            and isinstance(between, ast.Constant)
                            and str(between.value).strip() == ","
                        ):
                            found.add(
                                f"{where}:{part.lineno}: "
                                f"{ast.unparse(left.value)}, {ast.unparse(right.value)} (pair)"
                            )
                if not isinstance(part, ast.FormattedValue):
                    continue
                spec = "".join(
                    v.value
                    for v in getattr(part.format_spec, "values", [])
                    if isinstance(v, ast.Constant)
                )
                if gives_decimals(spec) or is_height(part.value):
                    found.add(f"{where}:{part.lineno}: {{{ast.unparse(part.value)}:{spec}}}")
    listed = "\n".join(sorted(found))
    assert not found, f"{len(found)} French texts write a decimal point:\n{listed}"


# A ; : ? or ! written right after a value, that French writes after a space
UNSPACED = re.compile(r"^[;:?!](?:\s|$)")


def test_french_texts_space_their_punctuation() -> None:
    """French writes a space before ; : ? and ! (« fenêtres indépendantes : chaque spin-up
    écarté ; moyennes… »). A text put together from other texts and shown in both languages
    (f"{method}; {note}", f"{what}: {problem}") is written with tr(), the French one spaced; so
    is a list joined inside a French text (" ; ".join(...))."""
    found = set()
    for path in sorted(SOURCE.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        where = path.relative_to(SOURCE).as_posix()
        english = english_parts(tree)
        shown = [n for n in shown_nodes(tree, source.splitlines()) if id(n) not in english]
        for text in [*shown, *french_texts(tree)]:
            for part in in_french(text):
                # A text is one line: an f-string of several is a script or a file, whose syntax
                # (the shell's "; do") is not French; its tr() pieces are read on their own
                if isinstance(part, ast.JoinedStr) and not any(
                    "\n" in str(v.value) for v in part.values if isinstance(v, ast.Constant)
                ):
                    for left, right in zip(part.values, part.values[1:], strict=False):
                        if (
                            isinstance(left, ast.FormattedValue)
                            and isinstance(right, ast.Constant)
                            and UNSPACED.match(str(right.value))
                        ):
                            found.add(f"{where}:{part.lineno}: {ast.unparse(part)}")
                if (
                    isinstance(part, ast.Call)
                    and called(part) == "join"
                    and isinstance(part.func, ast.Attribute)
                    and isinstance(part.func.value, ast.Constant)
                    and UNSPACED.match(str(part.func.value.value))
                ):
                    found.add(f"{where}:{part.lineno}: {ast.unparse(part)}")
    listed = "\n".join(sorted(found))
    assert not found, f"{len(found)} French texts glue their punctuation:\n{listed}"


# « vous », « votre », « vos », and the verbs of the second person plural ("lancez", "suivez-la"),
# outside the few words that only look like them
ORDER = re.compile(r"\b(?:vous|votre|vos)\b|\b(?!(?:assez|chez|nez|rez)\b)[A-Za-zÀ-ÿ]+ez\b")
# French written without tr(): the scripts and the LISEZ-MOI of the exported files
FRENCH_MODULES = ("core/method/scripts_text.py", "core/method/scripts.py", "core/method/export.py")


def french_text(node: ast.AST) -> str:
    """The literal parts of a text (a string, an f-string, or strings added together)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(french_text(v) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return french_text(node.left) + " " + french_text(node.right)
    return " "


def test_french_texts_say_neither_vous_nor_orders() -> None:
    """The French texts read like an engineer's note (his rule of 28/10): the problem, then the
    action in the infinitive or as a noun phrase ("lancer d'abord le calcul"), never « vous »,
    « votre », or the imperative of the second person ("lancez d'abord le calcul")."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        name = path.relative_to(SOURCE).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        texts: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and called(node) == "tr" and len(node.args) == 2:
                texts.append((node.lineno, french_text(node.args[1])))
            elif (
                name in FRENCH_MODULES
                and isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            ):
                texts.append((node.lineno, node.value))
        for line, text in texts:
            for line_text in text.splitlines() or [text]:
                words = ORDER.findall(line_text)
                if words:
                    found.append(f"{name}:{line}: {', '.join(words)} | {line_text.strip()[:120]}")
    assert not found, f"{len(found)} French texts with vous or an order:\n" + "\n".join(found)


def test_numbers_take_the_decimal_mark_of_the_language() -> None:
    with i18n.using("fr"):
        assert i18n.num(0.5) == "0,5"
        assert i18n.num(-1.234, ".2f") == "-1,23"
        assert i18n.num(600.0) == "600"
        assert i18n.num(1e-06) == "1e-06"
        assert i18n.num(2.5, "+g") == "+2,5"
        assert i18n.num(0.123, ".1%") == "12,3%"
        # The comma separates decimals: two numbers side by side take a semicolon
        assert i18n.pair(55.5, 7.8, ".4f") == "55,5000 ; 7,8000"
    with i18n.using("en"):
        assert i18n.num(0.5) == "0.5"
        assert i18n.num(-1.234, ".2f") == "-1.23"
        assert i18n.pair(55.5, 7.8, ".4f") == "55.5000, 7.8000"


def test_counts_take_their_singular_and_plural() -> None:
    """No "N thing(s)": 1 is singular in both languages, 0 in French only."""
    with i18n.using("en"):
        assert [i18n.counted(n, "file", "files") for n in (0, 1, 2)] == ["files", "file", "files"]
    with i18n.using("fr"):
        assert [i18n.counted(n, "fichier", "fichiers") for n in (0, 1, 2)] == [
            "fichier",
            "fichier",
            "fichiers",
        ]
    written = re.compile(r"[a-zéè]\((s|es|x|ies)\)")
    found = [
        f"{path.name}:{node.lineno}"
        for path in sorted(Path(i18n.__file__).parents[1].rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and written.search(node.value)
    ]
    assert found == []


def test_language_of_each_request(tmp_path: Path) -> None:
    from helpers import make_client

    client = make_client(tmp_path)
    english = client.get("/api/cases/nothing", headers={"X-OWS-Lang": "en"})
    french = client.get("/api/cases/nothing", headers={"X-OWS-Lang": "fr"})
    query = client.get("/api/cases/nothing?lang=fr")
    assert english.status_code == french.status_code == 404
    assert english.json()["detail"] == "Project nothing not found"
    assert french.json()["detail"] == query.json()["detail"] == "Projet nothing introuvable"


def test_background_work_and_unasked_requests_follow_the_settings(tmp_path: Path) -> None:
    from helpers import make_client

    client = make_client(tmp_path)
    for lang, text in (("en", "Project x not found"), ("fr", "Projet x introuvable")):
        assert client.patch("/api/settings", json={"language": lang}).status_code == 200
        assert client.get("/api/cases/x").json()["detail"] == text
        assert i18n.current() == lang


def test_the_page_opens_in_the_language_of_the_settings(tmp_path: Path) -> None:
    """The page carries the saved language from the first image: the window keeps nothing
    from one start to the next and would otherwise start in the language of Windows until the
    settings arrive."""
    from helpers import make_client

    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text('<!doctype html><html lang="en"><body></body></html>')
    client = make_client(tmp_path, static_dir=web)
    for lang in ("fr", "en"):
        client.patch("/api/settings", json={"language": lang})
        page = client.get("/").text
        assert f'<html lang="{lang}" data-saved-lang="{lang}">' in page
        assert client.get("/index.html").text == page


# Words that only one of the two languages uses, to tell an exported text's language
FRENCH = {
    "fenetre",
    "fenetres",
    "dossier",
    "fichier",
    "fichiers",
    "annee",
    "chemin",
    "depuis",
    "avant",
    "apres",
    "sortie",
    "sorties",
    "lancer",
    "termine",
    "erreur",
    "echec",
    "journal",
    "bloc",
    "donnees",
    "eoliennes",
    "maille",
    "debut",
    "periode",
    "parametres",
}
ENGLISH = {
    "window",
    "windows",
    "folder",
    "file",
    "files",
    "year",
    "path",
    "since",
    "before",
    "after",
    "output",
    "outputs",
    "run",
    "done",
    "error",
    "fail",
    "block",
    "data",
    "turbines",
    "cell",
    "start",
    "period",
    "settings",
    "the",
    "and",
    "of",
}


def words(text: str) -> set[str]:
    """The words of a text, without the technical names (options, files, variables: written
    with _ . / $ = or in capitals), which belong to no language."""
    kept = [
        token
        for token in text.split()
        if not any(c in token for c in "_./$={}[]") and not token.isupper()
    ]
    cleaned = "".join(c.lower() if c.isalpha() else " " for c in " ".join(kept))
    return set(cleaned.split())


@pytest.mark.parametrize("target", ["cluster", "local"])
@pytest.mark.parametrize("source", ["gfs", "era5"])
def test_exported_files_follow_the_language(
    reference_case: object, target: str, source: str
) -> None:
    from owstudio.core.method.export import ExportOptions, export_files
    from owstudio.core.method.scripts import FILE_NAMES

    case = reference_case.model_copy(deep=True)  # type: ignore[attr-defined]
    case.input_source = source
    exported = {}
    for lang in ("fr", "en"):
        with i18n.using(lang):  # type: ignore[arg-type]
            exported[lang] = export_files(
                case,
                ExportOptions(target=target),
                datetime(2026, 1, 1),  # type: ignore[arg-type]
            )
    for lang, other, foreign in (("fr", "en", ENGLISH), ("en", "fr", FRENCH)):
        files = exported[lang]
        names = FILE_NAMES[lang]
        assert names["readme"] in files and names["plan"] in files
        assert not any(
            FILE_NAMES[other]["readme"] == p or FILE_NAMES[other]["plan"] == p for p in files
        )
        for path, (text, _) in files.items():
            if (
                path.startswith("wps/Vtable")
                or path.endswith(
                    (
                        "namelist.wps",
                        "namelist.input",
                        "namelist.wps.sst",
                        "tslist",
                        ".txt",
                        ".tbl",
                        ".json",
                    )
                )
                and not path.endswith(names["readme"])
            ):
                continue
            # Comments and messages of the scripts, the read-me file and the CSV headers
            readable = "\n".join(
                line
                for line in text.splitlines()
                if line.lstrip().startswith("#") or '"' in line or path.endswith((".txt", ".csv"))
            )
            if path.endswith(".csv"):
                readable = text.splitlines()[0]
            if path.endswith(".py"):
                # The docstring and the messages, not the requests sent to the CDS
                readable = text.split('"""')[1] + "\n".join(
                    line for line in text.splitlines() if "print(" in line
                )
            mixed = words(readable) & foreign
            if lang == "fr":
                # French texts quote WRF's English messages (SUCCESS COMPLETE, Successful completion)
                # and the words the commands of the read-me look for in its logs (error, fatal)
                mixed -= {
                    "run",
                    "the",
                    "of",
                    "data",
                    "start",
                    "done",
                    "settings",
                    "file",
                    "files",
                    "error",
                }
            assert not mixed, f"{lang} {path}: {sorted(mixed)}"
