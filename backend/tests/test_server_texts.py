"""Every text the server shows to the user exists in English and in French (core/i18n.py: tr), and
the exported files follow the language of the interface.

The code is read, not run: an error raised, an HTTP error, a check (Issue), a problem added to a
list shown in the interface, written as a plain sentence instead of tr("...", "..."), fails. The
log stays in English and is not read here. An error that never reaches the user may carry the
comment "# internal" on its line.
"""

import ast
from datetime import datetime
from pathlib import Path

import pytest

from owstudio.core import i18n

SOURCE = Path(__file__).resolve().parents[1] / "src" / "owstudio"

# Lists whose items are shown to the user
SHOWN_LISTS = {"problems", "warnings", "notes", "issues", "errors", "messages", "missing", "flags"}
# Calls whose argument (at this position) is shown to the user
SHOWN_CALLS = {"HTTPException": 1, "Issue": 1, "Finding": 1, "Turbines": 1}
# Arguments and variables holding a text shown to the user (how a result was made, why...)
SHOWN_KEYWORDS = {"detail", "message", "method", "description"}
SHOWN_NAMES = {"method", "flags", "reason", "problem", "hint", "label", "what", "where"}


def sentence(node: ast.AST) -> bool:
    """A text written for a reader: a string (or f-string) with at least two words."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return sentence(node.left) or sentence(node.right)
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
    lines = source.splitlines()
    tree = ast.parse(source)
    result: list[ast.AST] = []
    shown: list[ast.AST] = []
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
            if name not in ("Field", "FastAPI"):
                shown += [k.value for k in node.keywords if k.arg in SHOWN_KEYWORDS]
            if (
                name in ("append", "extend")
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in SHOWN_LISTS
                and node.args
            ):
                shown.append(node.args[0])
        if isinstance(node, ast.Assign | ast.AnnAssign | ast.AugAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                named = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
                if named in SHOWN_NAMES and node.value is not None:
                    shown.append(node.value)
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in ("message", "detail"):
                    shown.append(value)
    for node in shown:
        candidates = [node]
        while any(isinstance(c, ast.List | ast.Tuple | ast.IfExp) for c in candidates):
            expanded: list[ast.AST] = []
            for c in candidates:
                if isinstance(c, ast.List | ast.Tuple):
                    expanded += c.elts
                elif isinstance(c, ast.IfExp):
                    expanded += [c.body, c.orelse]
                else:
                    expanded.append(c)
            candidates = expanded
        for item in candidates:
            if not sentence(item):
                continue
            if "# internal" in lines[item.lineno - 1]:
                continue
            result.append(item)
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
