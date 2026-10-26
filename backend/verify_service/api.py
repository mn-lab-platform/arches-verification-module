"""Same-origin API and static Astro build for /verify/."""

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from .auth import require_editor
from .cache import cached_resource_snapshot
from .custom_rules import (
    CustomRule,
    RuleDefinitionError,
    RuleNotFoundError,
    RuleStoreError,
    build_custom_rule,
    extend_profile,
    new_rule_id,
    rule_kinds,
    rule_store,
)
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


def _store_call(action: Callable[..., Any], *args: Any) -> Any:
    """Map rule storage errors to HTTP responses."""
    try:
        return action(*args)
    except RuleDefinitionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    except RuleNotFoundError:
        raise HTTPException(status_code=404, detail="Nie znaleziono zasady") from None
    except RuleStoreError:
        logger.exception("Custom rules file is unavailable")
        raise HTTPException(status_code=503, detail="Nie udało się odczytać lub zapisać zasad użytkownika") from None


def _rule_set(profile: ResourceProfile) -> tuple[ResourceProfile, tuple[RuleSpec, ...], set[str]]:
    """Builtin plus custom rules, and the profile extended with the fields the custom ones read."""
    custom = _store_call(rule_store().rules, profile.id)
    specs = RULE_SPECS_BY_RESOURCE_TYPE[profile.id] + tuple(rule.spec for rule in custom)
    return extend_profile(profile, custom), specs, {rule.spec.id for rule in custom}


def _builder_options(profile: ResourceProfile) -> dict:
    try:
        return load_rule_builder_options(profile)
    except Exception:
        logger.exception("Could not read rule builder metadata for %s", profile.id)
        raise HTTPException(status_code=503, detail="Definicja grafu Arches jest chwilowo niedostępna") from None


def _definition_profile(data: Any) -> ResourceProfile:
    resource_type = data.get("resource_type") if isinstance(data, dict) else None
    if not isinstance(resource_type, str) or not resource_type:
        raise HTTPException(status_code=400, detail="Podaj resource_type zasady")
    return _profile(resource_type, None)


def _built_rule(data: Any, profile: ResourceProfile, rule_id: str, created_at: str | None = None) -> CustomRule:
    options = _builder_options(profile)
    return _store_call(build_custom_rule, data, options, rule_id, created_at)


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
    profile, specs, custom_ids = _rule_set(_profile(resource_type, graph_id))
    snapshot = _snapshot(profile)
    trenches = snapshot.related_resources.get("trench", {})
    response.headers["Cache-Control"] = "no-store"
    return {
        "model": _model(profile),
        "rules": [
            {"id": spec.id, "label": spec.label, "description": spec.description, "custom": spec.id in custom_ids}
            for spec in specs
        ],
        "trenches": [
            {"id": resource_id, "name": name}
            for resource_id, name in sorted(trenches.items(), key=lambda item: item[1].casefold())
        ],
        "defaults": _defaults(specs),
        "generated_at": snapshot.generated_at,
    }


@app.get("/api/rule-builder-options")
def rule_builder_options(response: Response, resource_type: str):
    """Expose compatible Arches graph nodes and the form schema of each custom rule kind."""
    result = _builder_options(_profile(resource_type, None))
    response.headers["Cache-Control"] = "no-store"
    return {**result, "kinds": rule_kinds()}


@app.get("/api/rules")
def list_rules(response: Response, resource_type: str):
    """Builtin rules are read-only; custom rules come with their full definitions."""
    profile = _profile(resource_type, None)
    custom = _store_call(rule_store().rules, profile.id)
    response.headers["Cache-Control"] = "no-store"
    return {
        "model": _model(profile),
        "builtin": [
            {"id": spec.id, "label": spec.label, "description": spec.description, "kind": spec.kind}
            for spec in RULE_SPECS_BY_RESOURCE_TYPE[profile.id]
        ],
        "custom": [rule.to_record() for rule in custom],
    }


@app.post("/api/rules", status_code=201)
def create_rule(request: Request, response: Response, data: Any = Body(...)):
    profile = _definition_profile(data)
    require_editor(request, profile)
    rule = _built_rule(data, profile, new_rule_id())
    _store_call(rule_store().add, rule)
    response.headers["Cache-Control"] = "no-store"
    return rule.to_record()


@app.put("/api/rules/{rule_id}")
def update_rule(rule_id: str, request: Request, response: Response, data: Any = Body(...)):
    existing = _store_call(rule_store().get, rule_id)
    profile = _profile(existing.spec.resource_type, None)
    require_editor(request, profile)
    if _definition_profile(data).id != profile.id:
        raise HTTPException(status_code=400, detail="Nie można zmienić typu zasobu istniejącej zasady")
    rule = _built_rule(data, profile, rule_id, existing.created_at)
    _store_call(rule_store().replace, rule)
    response.headers["Cache-Control"] = "no-store"
    return rule.to_record()


@app.delete("/api/rules/{rule_id}", status_code=204)
def delete_rule(rule_id: str, request: Request):
    existing = _store_call(rule_store().get, rule_id)
    require_editor(request, _profile(existing.spec.resource_type, None))
    _store_call(rule_store().delete, rule_id)
    return Response(status_code=204)


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
    profile, specs, _ = _rule_set(_profile(resource_type, graph_id))
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
