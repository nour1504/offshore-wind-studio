"""Cases stored on disk: one directory per case holding its case.yaml."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from owstudio.core.case.model import Case

CASE_FILE = "case.yaml"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "case"


@dataclass(frozen=True)
class CaseSummary:
    id: str
    name: str
    description: str
    start: datetime
    end: datetime
    domains: int
    turbines: int
    farms: int = 0
    farm_scheme: str | None = None


class CaseNotFound(KeyError):
    pass


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cases_dir = root / "cases"
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    def case_dir(self, case_id: str) -> Path:
        if slugify(case_id) != case_id:
            raise CaseNotFound(case_id)
        return self.cases_dir / case_id

    def list(self) -> list[CaseSummary]:
        summaries = []
        for path in sorted(self.cases_dir.glob(f"*/{CASE_FILE}")):
            case = Case.from_yaml(path)
            summaries.append(
                CaseSummary(
                    id=path.parent.name,
                    name=case.name,
                    description=case.description,
                    start=case.period.start,
                    end=case.period.end,
                    domains=case.max_dom,
                    turbines=sum(len(f.turbines) for f in case.farms),
                    farms=len(case.farms),
                    farm_scheme=case.farm_scheme.scheme if case.farm_scheme else None,
                )
            )
        return summaries

    def load(self, case_id: str) -> Case:
        path = self.case_dir(case_id) / CASE_FILE
        if not path.exists():
            raise CaseNotFound(case_id)
        return Case.from_yaml(path)

    def save(self, case_id: str, case: Case) -> None:
        directory = self.case_dir(case_id)
        if not directory.exists():
            raise CaseNotFound(case_id)
        case.to_yaml(directory / CASE_FILE)

    def create(self, case: Case) -> str:
        """Store a new case under a unique id derived from its name."""
        base = slugify(case.name)
        case_id, n = base, 2
        while (self.cases_dir / case_id).exists():
            case_id, n = f"{base}-{n}", n + 1
        (self.cases_dir / case_id).mkdir()
        case.to_yaml(self.cases_dir / case_id / CASE_FILE)
        return case_id
