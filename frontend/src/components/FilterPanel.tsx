import type { Filters, Options } from '../lib/api';

type Props = {
  options: Options;
  filters: Filters;
  loading: boolean;
  onChange: (filters: Filters) => void;
  onSubmit: (event: Event) => void;
};

export default function FilterPanel({ options, filters, loading, onChange, onSubmit }: Props) {
  const update = (changes: Partial<Filters>) => onChange({ ...filters, ...changes });
  const toggleRule = (ruleId: string) => update({
    rules: filters.rules.includes(ruleId)
      ? filters.rules.filter((id) => id !== ruleId)
      : [...filters.rules, ruleId],
  });

  return <section class="panel controls-panel" aria-labelledby="filters-heading">
    <div class="section-heading">
      <div><span class="step-label">03 / ZAKRES</span><h2 id="filters-heading">Wybierz rekordy</h2></div>
      <p>Daty dotyczą momentu dodania zasobu do Arches.</p>
    </div>
    <form onSubmit={onSubmit}>
      <div class="filter-grid">
        <label>Data od<input type="date" value={filters.from} onInput={(event) => update({ from: event.currentTarget.value })} /></label>
        <label>Data do<input type="date" value={filters.to} onInput={(event) => update({ to: event.currentTarget.value })} /></label>
        {options.trenches.length > 0 && <label>Trench<select value={filters.trenchId} onChange={(event) => update({ trenchId: event.currentTarget.value })}>
          <option value="">Wszystkie trenches</option>
          {options.trenches.map((trench) => <option key={trench.id} value={trench.id}>{trench.name}</option>)}
        </select></label>}
      </div>
      <div class="scope-actions">
        <button type="button" class="text-button" onClick={() => update({ from: '', to: '' })}>Wyczyść daty — pokaż całą historię</button>
        {options.model.resource_type === 'context' && <label class="checkbox-line"><input type="checkbox" checked={filters.includeHarris} onChange={(event) => update({ includeHarris: event.currentTarget.checked })} /> Dołącz Context powiązane przez Harris</label>}
      </div>
      <div class="section-heading rules-heading">
        <div><span class="step-label">04 / ZASADY</span><h2>Co sprawdzić?</h2></div>
        <div class="rule-actions">
          <button type="button" class="text-button" onClick={() => update({ rules: options.rules.map((rule) => rule.id) })}>Zaznacz wszystkie</button>
          <button type="button" class="text-button" onClick={() => update({ rules: [] })}>Wyczyść</button>
        </div>
      </div>
      <div class="rule-grid">
        {options.rules.map((rule) => <label key={rule.id} class={`rule-choice ${filters.rules.includes(rule.id) ? 'rule-choice--active' : ''}`}>
          <input type="checkbox" checked={filters.rules.includes(rule.id)} onChange={() => toggleRule(rule.id)} />
          <span><strong>{rule.label}</strong><small>{rule.description}</small></span>
        </label>)}
      </div>
      <div class="form-footer">
        <button type="submit" class="primary-button" disabled={loading}>Sprawdź rekordy <span aria-hidden="true">→</span></button>
        <span>Wynik obejmuje wszystkie pasujące rekordy.</span>
      </div>
    </form>
  </section>;
}
