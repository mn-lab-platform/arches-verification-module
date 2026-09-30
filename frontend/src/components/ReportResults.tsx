import { formatTimestamp, SORTS, type Report, type RuleResult } from '../lib/api';

type Props = {
  report: Report | null;
  loading: boolean;
  onlyFailed: boolean;
  sort: string;
  page: number;
  onOnlyFailed: (value: boolean) => void;
  onSort: (value: string) => void;
  onPage: (page: number) => void;
};

function StatusCell({ result }: { result: RuleResult }) {
  const labels = { pass: 'OK', fail: 'Błąd', not_applicable: 'Nie dotyczy' };
  return <div class={`rule-result rule-result--${result.status}`}>
    <span class="status-pill">{labels[result.status]}</span>
    {result.messages.length > 0 && <details>
      <summary>{result.messages.length === 1 ? 'Szczegóły' : `${result.messages.length} uwag`}</summary>
      <ul>{result.messages.map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
    </details>}
  </div>;
}

export default function ReportResults({ report, loading, onlyFailed, sort, page, onOnlyFailed, onSort, onPage }: Props) {
  return <section class="results-section" aria-labelledby="results-heading">
    <div class="section-heading results-heading">
      <div><span class="step-label">03 / WYNIKI</span><h2 id="results-heading">Raport weryfikacji</h2></div>
      {report && <p>Dane odczytane: {formatTimestamp(report.generated_at)} · aktualizacja cache do 5 minut</p>}
    </div>
    {report && <>
      <div class="summary-grid" aria-live="polite">
        <div class="summary-card"><span>W zakresie bazowym</span><strong>{report.summary.base_count}</strong></div>
        <div class="summary-card"><span>Sprawdzono</span><strong>{report.summary.total_scope}</strong></div>
        <div class="summary-card summary-card--bad"><span>Wymaga uwagi</span><strong>{report.summary.failed}</strong></div>
        <div class="summary-card summary-card--good"><span>Bez błędów</span><strong>{report.summary.passed}</strong></div>
      </div>
      {report.gaps.length > 0 && <details class="gap-panel">
        <summary>Luki numeracji: {report.gaps.reduce((sum, gap) => sum + gap.missing_count, 0)} brakujących numerów</summary>
        <ul>{report.gaps.map((gap) => <li key={gap.trench_id}><strong>{gap.trench_name}:</strong> {gap.ranges.map((range) => range.from === range.to ? range.from : `${range.from}–${range.to}`).join(', ')}</li>)}</ul>
      </details>}
      <div class="table-toolbar">
        <label class="checkbox-line"><input type="checkbox" checked={onlyFailed} onChange={(event) => onOnlyFailed(event.currentTarget.checked)} /> Tylko z błędami</label>
        <label>Sortuj<select value={sort} onChange={(event) => onSort(event.currentTarget.value)}>{SORTS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></label>
      </div>
      <div class="table-wrap" aria-busy={loading}><table>
        <thead><tr><th scope="col">Context</th><th scope="col">Dodano</th><th scope="col">Trench</th><th scope="col">Numer</th>{report.rules.map((rule) => <th scope="col" key={rule.id}>{rule.label}</th>)}</tr></thead>
        <tbody>{report.rows.map((row) => <tr key={row.resource_id} class={row.overall_status === 'fail' ? 'row--fail' : ''}>
          <th scope="row"><a href={row.resource_url}>{row.name}</a>{row.source === 'harris' && <small>Dołączony przez Harris</small>}</th>
          <td>{row.created_at.slice(0, 16).replace('T', ' ')}</td><td>{row.trench_name}</td><td>{row.number ?? '—'}</td>
          {report.rules.map((rule) => <td key={rule.id}><StatusCell result={row.results[rule.id]} /></td>)}
        </tr>)}</tbody>
      </table>{report.rows.length === 0 && <p class="empty-state">Brak rekordów dla wybranych filtrów.</p>}</div>
      <div class="pagination">
        <span>{report.total} rekordów · strona {report.page} z {Math.max(report.pages, 1)}</span>
        <div><button type="button" disabled={loading || page <= 1} onClick={() => onPage(page - 1)}>← Poprzednia</button><button type="button" disabled={loading || page >= report.pages} onClick={() => onPage(page + 1)}>Następna →</button></div>
      </div>
    </>}
    {loading && <div class="loading-strip" role="status">Obliczanie wyników…</div>}
  </section>;
}
