# Context verification service

Standalone Python 3.13 API and static Astro/Preact frontend. The service reads Arches PostgreSQL with a dedicated read-only role and caches a normalized Context snapshot in Redis for 300 seconds. It never imports the Arches application package.

## Deployment in this workspace

1. Set `VERIFY_DB_PASSWORD` to a strong random value in `arches-for-excavation-project/.env` (ignored by git). Compose uses `verify_reader` as the database role. The setup job creates/updates that role and grants `SELECT` only on the five required Arches tables.
2. In `arches-for-excavation-project`, run `docker compose config`, then `docker compose up -d --build verify nginx`. The `verify_db_setup` job runs before the API service.
3. Open the existing Arches host at `/verify/`. `/verify` redirects to `/verify/`.

The browser receives only normalized row facts and rule results. The current version is public and limited to Context.

## Local checks

Run pure Python tests with `PYTHONPATH=backend python3 -m unittest discover -s backend/tests`. Build the frontend with `npm ci && npm run build` in `frontend` or build the Docker image. The app exposes `/health`, `/api/options`, and `/api/results` internally; nginx publishes them below `/verify/`.
