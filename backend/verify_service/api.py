"""Same-origin API and static Astro build for /verify/."""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles

from .cache import cached_resource_snapshot
from .profiles import CONTEXT_PROFILE, PROFILES, ResourceProfile
from .report import SORTS, ReportQuery, build_report
from .repository import load_resource_snapshot
from .rule_builder_options import load_rule_builder_options
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


@app.get("/api/rule-builder-options")
def rule_builder_options(response: Response, resource_type: str):
    """Expose compatible Arches graph nodes for future custom rule forms."""
    profile = _profile(resource_type, None)
    try:
        result = load_rule_builder_options(profile)
    except Exception:
        logger.exception("Could not read rule builder metadata for %s", profile.id)
        raise HTTPException(status_code=503, detail="Definicja grafu Arches jest chwilowo niedostępna") from None
    response.headers["Cache-Control"] = "no-store"
    return result


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
    profile = _profile(resource_type, graph_id)
    specs = _specs(profile)
    available_ids = {spec.id for spec in specs}
    start, end = _date(created_from, "od"), _date(created_to, "do")
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="Data początkowa jest późniejsza niż końcowa")
    rule_ids = tuple(dict.fromkeys(rules.split(",") if rules is not None else (spec.id for spec in specs)))
    if not rule_ids or any(rule_id not in available_ids for rule_id in rule_ids):
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
