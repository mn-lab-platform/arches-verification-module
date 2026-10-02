export type Rule = { id: string; label: string; description: string };
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
  generated_at: string;
  rules: { id: string; label: string }[];
  summary: { base_count: number; total_scope: number; passed: number; failed: number };
  gaps: { trench_id: string; trench_name: string; missing_count: number; ranges: { from: number; to: number }[] }[];
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

export const API_BASE = `${import.meta.env.BASE_URL}api/`;

export const SORTS = [
  ['created_desc', 'Najnowsze'],
  ['created_asc', 'Najstarsze'],
  ['name_asc', 'Nazwa A–Z'],
  ['name_desc', 'Nazwa Z–A'],
  ['number_asc', 'Numer rosnąco'],
  ['number_desc', 'Numer malejąco'],
  ['failures_desc', 'Najwięcej błędów'],
] as const;

export async function fetchJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } });
  const payload = response.headers.get("content-type")?.includes("application/json")
    ? await response.json() as { detail?: string }
    : {};
  if (!response.ok) throw new Error(payload.detail || 'Nie udało się pobrać danych.');
  return payload as T;
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat('pl-PL', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Warsaw',
  }).format(parsed);
}
