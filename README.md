# Context verification service

Standalone Python 3.13 API and static Astro/Preact frontend. The service reads Arches PostgreSQL with a dedicated read-only role and caches one normalized snapshot per selected resource type in Redis for 300 seconds. It never imports the Arches application package.

## Deployment in this workspace

1. Set `VERIFY_DB_PASSWORD` to a strong random value in `arches-for-excavation-project/.env` (ignored by git). Compose uses `verify_reader` as the database role. The Arches startup script creates/updates that role and grants `SELECT` only on the five required Arches tables.
2. In `arches-for-excavation-project`, run `docker compose config`, then `docker compose up -d --build verify nginx`. The verify service waits for its database role to become available.
3. Open the existing Arches host at `/verify/`. `/verify` redirects to `/verify/`.

The browser receives only normalized row facts and rule results. The current version is public and limited to Context.

## Local checks

Build the frontend with `npm ci && npm run build` in `frontend` or build the Docker image. The app exposes `/health`, `/api/catalog`, `/api/options`, and `/api/results` internally; nginx publishes them below `/verify/`.

## Search-result report API

`POST /verify/api/results` accepts JSON with a required `resource_ids` array containing **all** IDs returned by an Arches advanced search, not just one results page. It accepts the existing report options (`resource_type`, `graph_id`, `from`, `to`, `trench_id`, `include_harris`, `rules`, `only_failed`, `sort`, `page`, `page_size`). `rules` may be an array or a comma-separated string; booleans may be JSON booleans. For example:

```json
{"resource_type":"context","resource_ids":["00000000-0000-4000-8000-000000000001"],"rules":["trench","number_unique"],"include_harris":false,"page":1}
```

The response has the same shape as `GET /verify/api/results`. Search IDs are intersected with the selected resource model, dates, and trench before optional Harris expansion. An empty `resource_ids` array returns an empty report. The existing GET endpoint remains available for unfiltered reports.

## Advanced search in the frontend

The Astro/Preact report page opens the existing Arches Vue `AdvancedSearch` component in a same-origin dialog. Arches compiles the applied query with the signed-in user's permissions and returns **all** matching Context IDs through `/api/verify/search-ids`; the browser then sends that ID set to the POST report API. Sign in to Arches before using advanced search. Date and Trench controls further narrow the selected set, and optional Harris expansion runs afterward. Clearing the search returns to the original unfiltered GET report flow.
