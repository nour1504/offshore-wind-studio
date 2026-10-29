"""The Help tab: documentation topics in English and French, shipped with the application.

Each topic is a Markdown file owstudio/data/docs/<lang>/<id>.md starting with a small header:

    ---
    title: Sea surface temperature
    section: Input data
    order: 30
    summary: Where the SST comes from, separate SST products and updates during long runs.
    related: input-sources, vtables
    ---

Links between topics are written [text](doc:topic-id). A topic missing in French falls back to
English, so that the help never shows an empty page.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from importlib.resources.abc import Traversable

LANGS = ("en", "fr")
TOPIC_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ALIASES = {
    "wind-analysis": "analyses",
    "energy": "wake-efficiency",
    "variables": "results",
    "checks": "project-overview",
    "projects": "project-overview",
    "observations-comparison": "observations",
}
# Order of the sections in the help index; unknown sections come last
SECTION_ORDER = {
    "en": [
        "Getting started", "Projects", "Input data", "Domains", "Wind farms", "Physics and namelists",
        "Outputs", "Compute", "Runs", "Results", "Analyses", "Observations", "Storage", "Troubleshooting",
        "Reference",
    ],
    "fr": [
        "Prise en main", "Projets", "Données d'entrée", "Domaines", "Parcs éoliens", "Physique et namelists",
        "Sorties", "Calcul", "Calculs", "Résultats", "Analyses", "Observations", "Stockage", "Dépannage",
        "Référence",
    ],
}  # fmt: skip


@dataclass(frozen=True)
class Topic:
    id: str
    lang: str
    title: str
    section: str
    order: int
    summary: str
    markdown: str
    related: list[str] = field(default_factory=list)
    hidden: bool = False


def _root() -> Traversable:
    return resources.files("owstudio.data") / "docs"


def parse(topic_id: str, lang: str, text: str) -> Topic:
    """Reads the header and body of a topic file."""
    header: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        for line in head.strip().splitlines():
            key, _, value = line.partition(":")
            header[key.strip()] = value.strip()
    return Topic(
        id=topic_id,
        lang=lang,
        title=header.get("title", topic_id),
        section=header.get("section", ""),
        order=int(header.get("order", "100") or 100),
        summary=header.get("summary", ""),
        markdown=body.strip() + "\n",
        related=[r.strip() for r in header.get("related", "").split(",") if r.strip()],
        hidden=header.get("hidden", "").lower() == "true",
    )


@cache
def topics(lang: str) -> dict[str, Topic]:
    """Every topic in ``lang``, completed with the English topics it lacks."""
    found: dict[str, Topic] = {}
    for code in ("en", lang) if lang != "en" else ("en",):
        folder = _root() / code
        if not folder.is_dir():
            continue
        for entry in folder.iterdir():
            if entry.name.endswith(".md"):
                topic_id = entry.name[:-3]
                topic = parse(topic_id, code, entry.read_bytes().decode("utf-8"))
                if topic.hidden:
                    found.pop(topic_id, None)
                else:
                    found[topic_id] = topic
    return found


def index(lang: str) -> list[Topic]:
    order = SECTION_ORDER.get(lang, SECTION_ORDER["en"])

    def key(topic: Topic) -> tuple[int, int, str]:
        section = order.index(topic.section) if topic.section in order else len(order)
        return (section, topic.order, topic.title)

    return sorted(topics(lang).values(), key=key)


def get(topic_id: str, lang: str) -> Topic:
    """Raises KeyError for an unknown topic."""
    if not TOPIC_ID.match(topic_id):
        raise KeyError(topic_id)
    return topics(lang)[ALIASES.get(topic_id, topic_id)]


def _plain(text: str) -> str:
    """Lower case without accents, for matching "systeme" with "système"."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass(frozen=True)
class Hit:
    id: str
    title: str
    section: str
    excerpt: str
    score: float


def search(query: str, lang: str, limit: int = 20) -> list[Hit]:
    """Topics matching every word of the query, best first: title, then summary, then text."""
    words = [w for w in re.split(r"\W+", _plain(query)) if len(w) > 1]
    if not words:
        return []
    hits = []
    for topic in topics(lang).values():
        title, summary, body = _plain(topic.title), _plain(topic.summary), _plain(topic.markdown)
        if not all(w in title or w in summary or w in body for w in words):
            continue
        score = sum(
            5 * title.count(w) + 3 * summary.count(w) + min(body.count(w), 10) for w in words
        )
        position = body.find(words[0])
        start = max(0, position - 80)
        excerpt = re.sub(r"\s+", " ", topic.markdown[start : start + 220]).strip()
        hits.append(
            Hit(topic.id, topic.title, topic.section, ("…" if start else "") + excerpt + "…", score)
        )
    return sorted(hits, key=lambda h: -h.score)[:limit]
