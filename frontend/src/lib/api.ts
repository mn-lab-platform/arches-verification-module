export type Rule = { id: string; label: string; description: string; custom?: boolean };
export type Trench = { id: string; name: string };
export type ResourceModel = { resource_type: string; graph_id: string; name: string };
export type Catalog = { models: ResourceModel[] };

export type Options = {
  model: ResourceModel;
  rules: Rule[];
  trenches: Trench[];
  defaults: { from: string; to: string; rules: string[] };
};

export type RuleResult = {
  status: 'pass' | 'fail' | 'not_applicable';
  messages: string[];
};

export type ReportRow = {
  resource_id: string;
  name: string;
  resource_url: string;
  created_at: string;
  trench_name: string;
  number: number | null;
  source: 'period' | 'harris';
  overall_status: 'pass' | 'fail' | 'not_applicable';
  results: Record<string, RuleResult>;
};

export type Report = {
  model: ResourceModel;
  generated_at: string;
  rules: { id: string; label: string }[];
  summary: { base_count: number; total_scope: number; passed: number; failed: number };
  gaps: { rule_id: string; rule_label: string; group_name: string; trench_id: string | null; trench_name: string; missing_count: number; ranges: { from: number; to: number }[] }[];
  rows: ReportRow[];
  page: number;
  pages: number;
  total: number;
};

export type Filters = {
  from: string;
  to: string;
  trenchId: string;
  includeHarris: boolean;
  rules: string[];
};

export type RuleParamType = 'choice' | 'choices' | 'integer' | 'boolean' | 'pattern';

/** One form field of a custom rule kind, as described by the backend's RULE_KINDS. */
export type RuleParam = {
  name: string;
  label: string;
  type: RuleParamType;
  options: string | null;
  default: ParamValue;
  required: boolean;
  nullable: boolean;
  minimum: number | null;
  min_items: number;
};

export type RuleKind = { kind: string; label: string; description: string; params: RuleParam[] };

export type GraphField = { node_id: string; label: string; datatype: string; nodegroup_id: string };

export type GraphRelation = {
  id: string;
  alias: string | null;
  node_id: string;
  label: string;
  datatype: string;
  direction: 'outgoing' | 'incoming';
  source_graph_id: string;
  target_graphs: { graph_id: string; name: string }[];
  any_resource_type: boolean;
};

export type BuilderOptions = {
  model: ResourceModel;
  fields: GraphField[];
  completeness_roots: GraphField[];
  numbering: GraphField[];
  grouping: { fields: GraphField[]; relations: GraphRelation[] };
  relations: GraphRelation[];
  kinds: RuleKind[];
};

export type ParamValue = string | string[] | number | boolean | null;

export type RuleDefinition = {
  resource_type: string;
  kind: string;
  label: string;
  description: string;
  params: Record<string, ParamValue>;
};

export type CustomRule = RuleDefinition & {
  id: string;
  relations: Record<string, { graph_id: string | null; node_id: string; direction: string }>;
  created_at: string;
  updated_at: string;
};

export type RulesList = {
  model: ResourceModel;
  builtin: { id: string; label: string; description: string; kind: string }[];
  custom: CustomRule[];
};

export type Permissions = { username: string; editable_graph_ids: string[] };

export const API_BASE = `${import.meta.env.BASE_URL}api/`;
/** Served by Arches itself, outside /verify/. */
export const PERMISSIONS_URL = '/api/verify/permissions';
export const LOGIN_URL = `/auth/?next=${encodeURIComponent(`${import.meta.env.BASE_URL}rules/`)}`;

export const SORTS = [
  ['created_desc', 'Najnowsze'],
  ['created_asc', 'Najstarsze'],
  ['name_asc', 'Nazwa A–Z'],
  ['name_desc', 'Nazwa Z–A'],
  ['number_asc', 'Numer rosnąco'],
  ['number_desc', 'Numer malejąco'],
  ['failures_desc', 'Najwięcej błędów'],
] as const;

/** Keeps the HTTP status, so callers can tell "not signed in" (401) from other errors. */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  const payload = response.headers.get("content-type")?.includes("application/json")
    ? await response.json() as { detail?: unknown }
    : {};
  if (!response.ok) {
    throw new ApiError(response.status, typeof payload.detail === 'string' ? payload.detail : fallback);
  }
  return payload as T;
}

export async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  return readJson<T>(response, 'Nie udało się pobrać danych.');
}

/** POST/PUT/DELETE with the Arches session cookie; the backend requires JSON for bodies. */
export async function sendJson<T>(method: 'POST' | 'PUT' | 'DELETE', url: string, body?: unknown): Promise<T | null> {
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    headers: body === undefined
      ? { Accept: 'application/json' }
      : { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  return readJson<T>(response, 'Nie udało się zapisać zmian.');
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('pl-PL', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Warsaw',
  }).format(parsed);
}
