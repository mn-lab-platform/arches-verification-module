"""Same-origin API and static Astro build for /verify/."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from .cache import cached_resource_snapshot
from .profiles import CONTEXT_PROFILE, PROFILES, ResourceProfile
from .report import SORTS, ReportQuery, build_report
from .repository import load_resource_snapshot
from .rules import RULE_SPECS_BY_RESOURCE_TYPE, RuleSpec
from .types import ResourceSnapshot

logger = logging.getLogger(__name__)
app = FastAPI(title="Arches verification", docs_url=None, redoc_url=None, openapi_url=None)


def _profile(resource_type: str | None, graph_id: str | None) -> ResourceProfile:
    if resource_type:
        profile = PROFILES.get(resource_type)
    elif graph_id:
        profile = next((item for item in PROFILES.values() if item.graph_id == graph_id), None)
    else:
        profile = CONTEXT_PROFILE
    if profile is None or (graph_id and graph_id != profile.graph_id):
        raise HTTPException(status_code=400, detail="Nieznany typ zasobu")
    if profile.id not in RULE_SPECS_BY_RESOURCE_TYPE:
        raise HTTPException(status_code=400, detail="Brak zasad dla wybranego typu zasobu")
    return profile


def _specs(profile: ResourceProfile) -> tuple[RuleSpec, ...]:
    return RULE_SPECS_BY_RESOURCE_TYPE[profile.id]


def _model(profile: ResourceProfile) -> dict[str, str]:
    return {"resource_type": profile.id, "graph_id": profile.graph_id, "name": profile.label}


def _snapshot(profile: ResourceProfile) -> ResourceSnapshot:
    try:
        return cached_resource_snapshot(profile, load_resource_snapshot)
    except Exception:
        logger.exception("Could not read Arches data for %s", profile.id)
        raise HTTPException(status_code=503, detail="Dane Arches są chwilowo niedostępne") from None


def _date(value: str | None, label: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Niepoprawna data {label}") from None


def _positive_int(value: str | int, label: str, maximum: int | None = None) -> int:
    if isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {label}")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {label}") from None
    if number < 1 or (maximum is not None and number > maximum):
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {label}")
    return number


def _boolean(value: str | bool, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if value.lower() in {"true", "1", "yes"}:
        return True
    if value.lower() in {"false", "0", "no"}:
        return False
    raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {label}")


def _body_string(body: dict, key: str, default: str | None = None) -> str | None:
    value = body.get(key, default)
    if value is not None and not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {key}")
    return value


def _body_int(body: dict, key: str, default: int) -> str | int:
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {key}")
    return value


def _body_bool(body: dict, key: str) -> str | bool:
    value = body.get(key, False)
    if not isinstance(value, (str, bool)):
        raise HTTPException(status_code=400, detail=f"Niepoprawna wartość {key}")
    return value


def _resource_ids(body: dict) -> frozenset[str]:
    values = body.get("resource_ids")
    if not isinstance(values, list):
        raise HTTPException(status_code=400, detail="resource_ids musi być listą identyfikatorów UUID")
    try:
        if any(not isinstance(value, str) for value in values):
            raise ValueError
        return frozenset(str(UUID(value)) for value in values)
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Niepoprawny identyfikator w resource_ids") from None


def _rule_ids(value: str | list[str] | None, specs: tuple[RuleSpec, ...]) -> tuple[str, ...]:
    if value is None:
        requested = (spec.id for spec in specs)
    elif isinstance(value, str):
        requested = value.split(",")
    elif isinstance(value, list) and all(isinstance(rule_id, str) for rule_id in value):
        requested = value
    else:
        raise HTTPException(status_code=400, detail="Niepoprawna lista zasad")
    rule_ids = tuple(dict.fromkeys(requested))
    available_ids = {spec.id for spec in specs}
    if not rule_ids or any(rule_id not in available_ids for rule_id in rule_ids):
        raise HTTPException(status_code=400, detail="Wybierz co najmniej jedną dostępną zasadę")
    return rule_ids


def _defaults(specs: tuple[RuleSpec, ...]) -> dict:
    today = datetime.now(ZoneInfo("Europe/Warsaw")).date()
    return {
        "from": (today - timedelta(days=29)).isoformat(),
        "to": today.isoformat(),
        "rules": [spec.id for spec in specs],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/catalog")
def catalog(response: Response):
    """List available resource types without accessing PostgreSQL or Redis."""
    response.headers["Cache-Control"] = "no-store"
    return {
        "models": [_model(profile) for profile in PROFILES.values() if profile.id in RULE_SPECS_BY_RESOURCE_TYPE],
    }


@app.get("/api/options")
def options(response: Response, resource_type: str | None = None, graph_id: str | None = None):
    """Load choices for a selected profile; default Context supports the current UI."""
    profile = _profile(resource_type, graph_id)
    specs = _specs(profile)
    snapshot = _snapshot(profile)
    trenches = snapshot.related_resources.get("trench", {})
    response.headers["Cache-Control"] = "no-store"
    return {
        "model": _model(profile),
        "rules": [{"id": spec.id, "label": spec.label, "description": spec.description} for spec in specs],
        "trenches": [
            {"id": resource_id, "name": name}
            for resource_id, name in sorted(trenches.items(), key=lambda item: item[1].casefold())
        ],
        "defaults": _defaults(specs),
        "generated_at": snapshot.generated_at,
    }


@app.get("/api/results")
def results(
    response: Response,
    resource_type: str | None = None,
    graph_id: str | None = None,
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
    return _results(
        response, resource_type, graph_id, created_from, created_to, trench_id,
        include_harris, rules, only_failed, sort, page, page_size,
    )


@app.post("/api/results")
async def search_results(request: Request, response: Response):
    """Verify a complete Arches search result set, not just its visible page."""
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Niepoprawny JSON") from None
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Oczekiwano obiektu JSON")
    resource_ids = _resource_ids(body)
    return _results(
        response,
        _body_string(body, "resource_type"),
        _body_string(body, "graph_id"),
        _body_string(body, "from"),
        _body_string(body, "to"),
        _body_string(body, "trench_id"),
        _body_bool(body, "include_harris"),
        body.get("rules"),
        _body_bool(body, "only_failed"),
        _body_string(body, "sort", "created_desc"),
        _body_int(body, "page", 1),
        _body_int(body, "page_size", 100),
        resource_ids,
    )


def _results(
    response: Response,
    resource_type: str | None,
    graph_id: str | None,
    created_from: str | None,
    created_to: str | None,
    trench_id: str | None,
    include_harris: str | bool,
    rules: str | list[str] | None,
    only_failed: str | bool,
    sort: str,
    page: str | int,
    page_size: str | int,
    resource_ids: frozenset[str] | None = None,
):
    profile = _profile(resource_type, graph_id)
    specs = _specs(profile)
    start, end = _date(created_from, "od"), _date(created_to, "do")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="Data początkowa jest późniejsza niż końcowa")
    rule_ids = _rule_ids(rules, specs)
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
        resource_ids=resource_ids,
    )
    snapshot = _snapshot(profile)
    if query.trench_id and query.trench_id not in snapshot.related_resources.get("trench", {}):
        raise HTTPException(status_code=400, detail="Nieznany Trench")
    response.headers["Cache-Control"] = "no-store"
    return build_report(snapshot, profile, specs, query)


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
else:
    @app.get("/")
    def frontend_not_built():
        raise HTTPException(status_code=503, detail="Frontend Astro nie został zbudowany")
