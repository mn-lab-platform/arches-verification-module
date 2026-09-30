import { useEffect, useState } from 'preact/hooks';

import FilterPanel from './FilterPanel';
import ReportResults from './ReportResults';
import { API_BASE, fetchJson, type Filters, type Options, type Report } from '../lib/api';

export default function VerifyApp() {
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
    fetchJson<Options>(`${API_BASE}options`, controller.signal)
      .then((value) => {
        const defaults: Filters = {
          from: value.defaults.from,
          to: value.defaults.to,
          trenchId: '',
          includeHarris: false,
          rules: value.defaults.rules,
        };
        setOptions(value);
        setDraft(defaults);
        setApplied(defaults);
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(String(reason.message || reason));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!applied || !options) return;
    const controller = new AbortController();
    const params = new URLSearchParams({
      graph_id: options.model.graph_id,
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
    setPage(1);
    setApplied({ ...draft, rules: [...draft.rules] });
  }

  if (!options || !draft) {
    return <section class="panel loading-panel" aria-live="polite">{error || 'Ładowanie danych…'}</section>;
  }

  return <>
    <FilterPanel options={options} filters={draft} loading={loading} onChange={setDraft} onSubmit={apply} />
    {error && <div class="error-banner" role="alert">{error}</div>}
    <ReportResults
      report={report}
      loading={loading}
      onlyFailed={onlyFailed}
      sort={sort}
      page={page}
      onOnlyFailed={(value) => { setOnlyFailed(value); setPage(1); }}
      onSort={(value) => { setSort(value); setPage(1); }}
      onPage={setPage}
    />
  </>;
}
