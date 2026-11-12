"""The Help tab: topics in English and French, links between topics, search."""

import re
from pathlib import Path

from helpers import make_client

from owstudio.core import docs


def test_every_topic_exists_in_both_languages_with_a_header() -> None:
    english, french = docs.topics("en"), docs.topics("fr")
    assert english and set(english) == {
        t for t, topic in french.items() if topic.lang in ("fr", "en")
    }
    for topic_id, topic in english.items():
        assert topic.title != topic_id and topic.section and topic.summary, topic_id
        assert french[topic_id].lang == "fr", f"{topic_id} has no French version"


def test_links_point_to_existing_topics_or_are_listed_as_planned() -> None:
    known = set(docs.topics("en"))
    for lang in docs.LANGS:
        for topic in docs.topics(lang).values():
            for target in re.findall(r"\(doc:([\w-]+)\)", topic.markdown) + topic.related:
                # Topics written later by other modules may be linked already; they must at
                # least be valid identifiers
                assert docs.TOPIC_ID.match(target), (topic.id, target)
    assert {"input-data", "input-sources", "sst", "vtables", "period"} <= known


def test_french_topics_say_neither_vous_nor_orders() -> None:
    """The French guide reads like an engineer's note (his rule of 28/10): the infinitive or a
    noun phrase ("lancer `run_wps.sh`"), never « vous », « votre », or the imperative of the
    second person ("lancez `run_wps.sh`"); one apostrophe, the straight one."""
    order = re.compile(
        r"\b(?:[Vv]ous|[Vv]otre|[Vv]os)\b|\b(?!(?:assez|chez|nez|rez)\b)[A-Za-zÀ-ÿ]+ez\b|’"
    )
    found = [
        f"{topic.id}: {line.strip()[:100]}"
        for topic in docs.topics("fr").values()
        if topic.lang == "fr"
        for line in f"{topic.title}\n{topic.summary}\n{topic.markdown}".splitlines()
        if order.search(line)
    ]
    assert found == []


def test_search_ignores_accents_and_case(tmp_path: Path) -> None:
    hits = docs.search("temperature surface mer", "fr")
    assert hits and hits[0].id == "sst"
    assert docs.search("TEMPÉRATURE", "fr")
    assert docs.search("x", "en") == []


def test_docs_api(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    index = client.get("/api/docs", params={"lang": "fr"}).json()["topics"]
    assert index[0]["section"] == "Prise en main" and index[0]["id"] == "getting-started"
    assert next(t for t in index if t["id"] == "input-data")["section"] == "Données d'entrée"
    page = client.get("/api/docs/sst", params={"lang": "en"}).json()
    assert page["title"] == "Sea surface temperature" and "fg_name" in page["markdown"]
    assert {r["id"] for r in page["related"]} <= set(docs.topics("en"))
    assert client.get("/api/docs/nope").status_code == 404
    assert client.get("/api/docs/../secrets").status_code == 404
    found = client.get("/api/docs/search", params={"q": "Vtable ECMWF", "lang": "en"}).json()[
        "results"
    ]
    assert found and found[0]["id"] in ("vtables", "input-sources")


def test_every_help_link_of_the_interface_opens_a_topic() -> None:
    # A help bubble (help="...", topic="...") whose topic is missing opens "not available yet"
    src = Path(__file__).resolve().parents[2] / "frontend" / "src"
    if not src.is_dir():
        return
    known = set(docs.topics("en"))
    named = {
        (path.relative_to(src).as_posix(), topic)
        for path in src.rglob("*.tsx")
        for attribute in re.findall(
            r"\b(?:help|topic)=(\"[\w-]+\"|\{[^}]*\})", path.read_text(encoding="utf-8")
        )
        for topic in re.findall(r"\"([\w-]+)\"", attribute)
    }
    assert named
    assert sorted((where, topic) for where, topic in named if topic not in known) == []


def test_no_topic_names_itself_as_related() -> None:
    """Regression: "Getting started" and "Results" offered a link to themselves."""
    for lang in ("en", "fr"):
        for topic in docs.topics(lang).values():
            assert topic.id not in topic.related, f"{lang}/{topic.id} is related to itself"


def test_the_help_names_the_engine_recipe_that_is_installed() -> None:
    """Regression: the help still gave the default folder of the recipe before (…-v2)."""
    from owstudio.core.engine import install

    for lang in ("en", "fr"):
        text = docs.get("engine-install", lang).markdown
        assert f"~/OffshoreWindStudioEngine/{install.spec()['id']}" in text, lang


def test_english_topics_do_not_space_their_colons() -> None:
    """French puts a space before a colon, English does not ("Official reference :")."""
    for topic in docs.topics("en").values():
        assert not re.search(r"[A-Za-z] :(?:\s|$)", topic.markdown), topic.id
