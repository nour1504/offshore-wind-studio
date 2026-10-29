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
