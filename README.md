# Arches verification service

Standalone Python 3.13 API and static Astro/Preact frontend. The service reads Arches PostgreSQL with a dedicated read-only role and caches one normalized snapshot per selected resource type in Redis for 300 seconds. It never imports the Arches application package.

## Deployment in this workspace

1. Set `VERIFY_DB_PASSWORD` to a strong random value in `arches-for-excavation-project/.env` (ignored by git). Compose uses `verify_reader` as the database role. The Arches startup script creates/updates that role and grants `SELECT` only on the six required Arches tables, including `geojson_geometries`.
2. In `arches-for-excavation-project`, run `docker compose config`, then `docker compose up -d --build arches verify nginx`. The Arches image contains the reader grant script, which runs at startup; verify waits for the database role to become available.
3. Open the existing Arches host at `/verify/`. `/verify` redirects to `/verify/`.

The browser receives only normalized row facts and rule results. The current version is public. The catalog includes Context, Special Find, Digital Resource 3D, Digital Resource IIIF, Annotation, Pottery Collection, and six Pottery Record graphs. Each type has a separate five-minute snapshot. Rules are declared in `backend/verify_service/rules.py` and compiled by shared factories in `rule_engine.py`; no rule runs in the browser.

The shared rule types are required relation, required fields, unique number, continuous number, and spatial containment. Special Find's `Order Number` accepts a letter prefix followed by digits (for example `M1`) as well as plain digits. Its spatial rules compare the Position point with the footprints of its linked Context and Trench using PostGIS `ST_Within`. Missing relations or geometries fail the relevant rule; all points must be inside each linked footprint. The pottery fragment sum is not implemented yet.

## Local checks

Build the frontend with `npm ci && npm run build` in `frontend` or build the Docker image. The app exposes `/health`, `/api/catalog`, `/api/options`, and `/api/results` internally; nginx publishes them below `/verify/`.
