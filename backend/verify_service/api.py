"""Same-origin API and static Astro build for /verify/."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles

from .cache import cached_snapshot
from .constants import CONTEXT_GRAPH_ID
from .report import SORTS, ReportQuery, build_report
from .repository import load_snapshot
from .rules import ALL_RULE_IDS, RULES

logger = logging.getLogger(__name__)
app = FastAPI(title="Context verification", docs_url=None, redoc_url=None, openapi_url=None)


def _snapshot():
    try:
        return cached_snapshot(load_snapshot)
    except Exception:
        logger.exception("Could not read Arches data")
        raise HTTPException(status_code=503, detail="Dane Arches są chwilowo niedostępne") from None


def _date(value: str | None, label: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Niepoprawna data {label}") from None


def _positive_int(value: str, label: str, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {label}") from None
    if number < 1 or (maximum is not None and number > maximum):
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {label}")
    return number


def _boolean(value: str, label: str) -> bool:
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {label}")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/options")
def options(response: Response):
    snapshot = _snapshot()
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    response.headers["Cache-Control"] = "no-store"
    return {
        "model": {"graph_id": CONTEXT_GRAPH_ID, "name": "(O) Context"},
        "rules": [{"id": rule.id, "label": rule.label, "description": rule.description} for rule in RULES],
        "trenches": [
            {"id": resource_id, "name": name}
            for resource_id, name in sorted(snapshot.trenches.items(), key=lambda item: item[1].casefold())
        ],
        "defaults": {"from": (today - timedelta(days=29)).isoformat(), "to": today.isoformat(), "rules": list(ALL_RULE_IDS)},
        "generated_at": snapshot.generated_at,
    }


@app.get("/api/results")
def results(
    response: Response,
    graph_id: str = CONTEXT_GRAPH_ID,
    created_from: str | None = Query(default=None, alias="from"),
    created_to: str | None = Query(default=None, alias="to"),
    trench_id: str | None = None,
    include_harris: str = "false",
    rules: str | None = None,
    only_failed: str = "false",
    sort: str = "created_desc",
    page: str = "1",
    page_size: str = "100",
):
    if graph_id != CONTEXT_GRAPH_ID:
        raise HTTPException(status_code=400, detail="Na razie dostępne są tylko zasady Context")
    start, end = _date(created_from, "od"), _date(created_to, "do")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="Data początkowa jest późniejsza niż końcowa")
    rule_ids = tuple(dict.fromkeys(rules.split(",") if rules is not None else ALL_RULE_IDS))
    if not rule_ids or any(rule_id not in ALL_RULE_IDS for rule_id in rule_ids):
        raise HTTPException(status_code=400, detail="Wybierz co najmniej jedną dostępną zasadę")
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail="Nieznane sortowanie")
    query = ReportQuery(
        created_from=start,
        created_to=end,
        trench_id=trench_id or None,
        include_harris=_boolean(include_harris, "include_harris"),
        rule_ids=rule_ids,
        only_failed=_boolean(only_failed, "only_failed"),
        sort=sort,
        page=_positive_int(page, "page"),
        page_size=_positive_int(page_size, "page_size", maximum=100),
    )
    snapshot = _snapshot()
    if query.trench_id and query.trench_id not in snapshot.trenches:
        raise HTTPException(status_code=400, detail="Nieznany Trench")
    response.headers["Cache-Control"] = "no-store"
    return build_report(snapshot, query)


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
else:
    @app.get("/")
    def frontend_not_built():
        raise HTTPException(status_code=503, detail="Frontend Astro nie został zbudowany")
