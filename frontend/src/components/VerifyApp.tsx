import { useEffect, useRef, useState } from 'preact/hooks';

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
  const [searchIds, setSearchIds] = useState<string[] | null>(null);
  const [appliedSearchIds, setAppliedSearchIds] = useState<string[] | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const searchFrame = useRef<HTMLIFrameElement>(null);
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
    const fields = {
      resource_type: options.model.resource_type,
      from: applied.from,
      to: applied.to,
      trench_id: applied.trenchId,
      include_harris: applied.includeHarris,
      rules: applied.rules,
      only_failed: onlyFailed,
      sort,
      page,
      page_size: 100,
    };
    setLoading(true);
    setError('');
    const request = appliedSearchIds === null
      ? fetchJson<Report>(`${API_BASE}results?${new URLSearchParams({
          ...fields,
          include_harris: String(fields.include_harris),
          rules: fields.rules.join(','),
          only_failed: String(fields.only_failed),
          page: String(fields.page),
          page_size: String(fields.page_size),
        })}`, controller.signal)
      : fetchJson<Report>(`${API_BASE}results`, controller.signal, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...fields, resource_ids: appliedSearchIds }),
        });
    request
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
  }, [applied, appliedSearchIds, options, page, sort, onlyFailed]);

  useEffect(() => {
    if (!searchOpen || !options) return;
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== searchFrame.current?.contentWindow) return;
      const data = event.data;
      if (data?.type !== 'verify-search:applied' || data.graphId !== options.model.graph_id) return;
      if (!Array.isArray(data.resourceIds) || data.total !== data.resourceIds.length ||
          !data.resourceIds.every((id: unknown) => typeof id === 'string')) return;
      setSearchIds(data.resourceIds);
      setApplied(null);
      setAppliedSearchIds(null);
      setReport(null);
      setPage(1);
      setSearchOpen(false);
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [searchOpen, options]);

  function selectResource(resourceType: string) {
    setSelectedResource(resourceType);
    setOptions(null);
    setDraft(null);
    setApplied(null);
    setSearchIds(null);
    setAppliedSearchIds(null);
    setSearchOpen(false);
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
    setAppliedSearchIds(searchIds === null ? null : [...searchIds]);
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
    {options && <section class="panel controls-panel search-scope-panel" aria-labelledby="search-scope-heading">
      <div class="section-heading">
        <div><span class="step-label">02 / WYSZUKIWANIE</span><h2 id="search-scope-heading">Wyszukiwanie zaawansowane</h2></div>
        <p>Wyniki wyszukiwania połączą się z datami i Trench poniżej.</p>
      </div>
      <div class="search-scope-actions">
        <button type="button" class="secondary-button" onClick={() => setSearchOpen(true)}>Otwórz wyszukiwanie</button>
        <span role="status">{searchIds === null ? 'Bez dodatkowego filtra — wszystkie rekordy' : `${searchIds.length} pasujących rekordów z wyszukiwania`}</span>
        {searchIds !== null && <button type="button" class="text-button" onClick={() => {
          setSearchIds(null);
          setApplied(null);
          setAppliedSearchIds(null);
          setReport(null);
        }}>Wyczyść wyszukiwanie</button>}
      </div>
    </section>}
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
    {searchOpen && options && <div class="search-dialog-backdrop" role="presentation">
      <section class="search-dialog" role="dialog" aria-modal="true" aria-label="Wyszukiwanie zaawansowane">
        <div class="search-dialog-topbar">
          <strong>Wybierz rekordy do weryfikacji</strong>
          <button type="button" class="secondary-button" onClick={() => setSearchOpen(false)}>Zamknij</button>
        </div>
        <iframe
          ref={searchFrame}
          title="Wyszukiwanie zaawansowane Arches"
          src={`/verify-search/?graph_id=${encodeURIComponent(options.model.graph_id)}`}
        />
      </section>
    </div>}
  </>;
}
