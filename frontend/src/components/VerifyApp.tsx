import { useEffect, useState } from 'preact/hooks';

import FilterPanel from './FilterPanel';
import ReportResults from './ReportResults';
import { API_BASE, fetchJson, type Catalog, type Filters, type Options, type Report } from '../lib/api';

export default function VerifyApp() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogRetry, setCatalogRetry] = useState(0);
  const [selectedResource, setSelectedResource] = useState('');
  const [optionsRetry, setOptionsRetry] = useState(0);
  const [options, setOptions] = useState<Options | null>(null);
  const [draft, setDraft] = useState<Filters | null>(null);
  const [applied, setApplied] = useState<Filters | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState('created_desc');
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    fetchJson<Catalog>(`${API_BASE}catalog`, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setCatalog(value);
        setLoading(false);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(String(reason.message || reason));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [catalogRetry]);

  useEffect(() => {
    if (!selectedResource) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ resource_type: selectedResource });
    setLoading(true);
    setError('');
    fetchJson<Options>(`${API_BASE}options?${params}`, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setOptions(value);
        setDraft({
          from: value.defaults.from,
          to: value.defaults.to,
          trenchId: '',
          includeHarris: false,
          rules: value.defaults.rules,
        });
        setLoading(false);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(String(reason.message || reason));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedResource, optionsRetry]);

  useEffect(() => {
    if (!applied || !options) return;
    const controller = new AbortController();
    const params = new URLSearchParams({
      resource_type: options.model.resource_type,
      from: applied.from,
      to: applied.to,
      trench_id: applied.trenchId,
      include_harris: String(applied.includeHarris),
      rules: applied.rules.join(','),
      only_failed: String(onlyFailed),
      sort,
      page: String(page),
      page_size: '100',
    });
    setLoading(true);
    setError('');
    fetchJson<Report>(`${API_BASE}results?${params}`, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setReport(value);
        setLoading(false);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(String(reason.message || reason));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [applied, options, page, sort, onlyFailed]);

  function selectResource(resourceType: string) {
    setSelectedResource(resourceType);
    setOptions(null);
    setDraft(null);
    setApplied(null);
    setReport(null);
    setPage(1);
    setSort('created_desc');
    setOnlyFailed(false);
    setError('');
  }

  function apply(event: Event) {
    event.preventDefault();
    if (!draft) return;
    if (draft.rules.length === 0) {
      setError('Wybierz co najmniej jedną zasadę.');
      return;
    }
    if (draft.from && draft.to && draft.from > draft.to) {
      setError('Data początkowa jest późniejsza niż końcowa.');
      return;
    }
    setError('');
    setReport(null);
    setPage(1);
    setApplied({ ...draft, rules: [...draft.rules] });
  }

  if (!catalog) {
    return <section class="panel loading-panel" aria-live="polite">
      {error || 'Ładowanie typów zasobów…'}
      {error && <button type="button" onClick={() => setCatalogRetry((value) => value + 1)}>Ponów</button>}
    </section>;
  }

  return <>
    <section class="panel controls-panel">
      <div class="section-heading">
        <div><span class="step-label">01 / TYP ZASOBU</span><h2>Wybierz typ zasobu</h2></div>
      </div>
      <div class="filter-grid">
        <label>Typ zasobu
          <select value={selectedResource} onChange={(event) => selectResource(event.currentTarget.value)}>
            <option value="">Wybierz typ zasobu</option>
            {catalog.models.map((model) => <option key={model.resource_type} value={model.resource_type}>{model.name}</option>)}
          </select>
        </label>
      </div>
    </section>
    {selectedResource && !options && loading && <section class="panel loading-panel" aria-live="polite">Ładowanie danych zasobu…</section>}
    {error && <div class="error-banner" role="alert">
      {error}
      {selectedResource && !options && <button type="button" onClick={() => setOptionsRetry((value) => value + 1)}>Ponów</button>}
    </div>}
    {options && draft && <FilterPanel options={options} filters={draft} loading={loading} onChange={setDraft} onSubmit={apply} />}
    {options && applied && <ReportResults
      report={report}
      loading={loading}
      onlyFailed={onlyFailed}
      sort={sort}
      page={page}
      onOnlyFailed={(value) => { setOnlyFailed(value); setPage(1); }}
      onSort={(value) => { setSort(value); setPage(1); }}
      onPage={setPage}
    />}
  </>;
}
