"""Writes need Arches edit rights on the rule's graph, checked with the browser's Arches session."""

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request as UrlRequest, urlopen

from fastapi import HTTPException, Request

from .profiles import ResourceProfile

logger = logging.getLogger(__name__)
PERMISSIONS_PATH = "/api/verify/permissions"
LOGIN_REQUIRED = "Zaloguj się w Arches, aby zarządzać zasadami"


def _check_same_origin(request: Request) -> None:
    """The session cookie authorizes writes, so refuse requests another site could send."""
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(status_code=403, detail="Żądanie z innej domeny")
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    if request.method in {"POST", "PUT"} and content_type != "application/json":
        raise HTTPException(status_code=415, detail="Wymagany Content-Type: application/json")


def _arches_permissions(request: Request) -> dict:
    cookie = request.headers.get("cookie")
    if not cookie:
        raise HTTPException(status_code=401, detail=LOGIN_REQUIRED)
    # The original Host passes Django's ALLOWED_HOSTS; the scheme avoids an HTTPS redirect.
    headers = {"Cookie": cookie, "Accept": "application/json"}
    for name in ("host", "x-forwarded-proto", "x-forwarded-for"):
        if value := request.headers.get(name):
            headers[name.title()] = value
    url = os.environ.get("VERIFY_ARCHES_URL", "http://arches:8000").rstrip("/") + PERMISSIONS_PATH
    try:
        with urlopen(UrlRequest(url, headers=headers), timeout=5) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code in {401, 403}:
            raise HTTPException(status_code=401, detail=LOGIN_REQUIRED) from None
        logger.warning("Arches permission check returned %s", error.code)
    except (URLError, OSError, ValueError) as error:
        logger.warning("Arches permission check failed: %s", error)
    raise HTTPException(status_code=503, detail="Nie można sprawdzić uprawnień w Arches")


def require_editor(request: Request, profile: ResourceProfile) -> str:
    """Allow the write only to users who can edit this resource type in Arches; returns the username."""
    _check_same_origin(request)
    permissions = _arches_permissions(request)
    if profile.graph_id not in permissions.get("editable_graph_ids", []):
        raise HTTPException(status_code=403, detail=f"Brak uprawnień do edycji zasobów {profile.label} w Arches")
    return permissions.get("username", "")
