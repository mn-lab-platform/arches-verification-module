import { useEffect, useState } from 'preact/hooks';

import {
  API_BASE,
  ApiError,
  LOGIN_URL,
  PERMISSIONS_URL,
  fetchJson,
  formatTimestamp,
  sendJson,
  type BuilderOptions,
  type Catalog,
  type CustomRule,
  type ParamValue,
  type Permissions,
  type RuleKind,
  type RulesList,
} from '../lib/api';
import { optionLabels } from '../lib/ruleLabels';
import RuleForm from './RuleForm';

type Access = { state: 'loading' } | { state: 'anonymous' } | { state: 'error' } | { state: 'signed_in'; permissions: Permissions };

function formatValue(value: ParamValue, labels: Map<string, string>): string {
  if (value === null) return '—';
  if (typeof value === 'boolean') return value ? 'tak' : 'nie';
  if (Array.isArray(value)) return value.length ? value.map((item) => labels.get(item) ?? item).join(', ') : '—';
  return typeof value === 'string' ? labels.get(value) ?? value : String(value);
}

function RuleCard({ rule, kind, labels, canEdit, deleting, onDelete, onEdit }: {
  rule: CustomRule;
  kind: RuleKind | undefined;
  labels: Map<string, string>;
  canEdit: boolean;
  deleting: boolean;
  onDelete: (rule: CustomRule) => void;
  onEdit: ((rule: CustomRule) => void) | null;
}) {
  const params = kind
    ? kind.params.map((param) => [param.label, param.name === 'fields' && rule.params.fields === null ? 'wszystkie pola' : formatValue(rule.params[param.name] ?? null, labels)])
    : Object.entries(rule.params).map(([name, value]) => [name, formatValue(value, labels)]);
  return <article class="rule-card">
    <div class="rule-card__head">
      <div>
        <span class="badge">{kind?.label ?? rule.kind}</span>
        <h3>{rule.label}</h3>
        {rule.description && <p>{rule.description}</p>}
      </div>
      {canEdit && <div class="rule-card__actions">
        {onEdit && <button type="button" class="text-button" disabled={deleting} onClick={() => onEdit(rule)}>Edytuj</button>}
        <button type="button" class="text-button text-button--danger" disabled={deleting} onClick={() => onDelete(rule)}>
          {deleting ? 'Usuwanie…' : 'Usuń'}
        </button>
      </div>}
    </div>
    <dl>{params.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    <small>Zmieniono: {formatTimestamp(rule.updated_at)}</small>
  </article>;
}

export default function RulesApp() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [access, setAccess] = useState<Access>({ state: 'loading' });
  const [resourceType, setResourceType] = useState('');
  const [rules, setRules] = useState<RulesList | null>(null);
  const [builder, setBuilder] = useState<BuilderOptions | null>(null);
  const [builderError, setBuilderError] = useState('');
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState('');
  const [editing, setEditing] = useState<CustomRule | 'new' | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    fetchJson<Catalog>(`${API_BASE}catalog`, controller.signal)
      .then(setCatalog)
      .catch((reason) => { if (!controller.signal.aborted) setError(String(reason.message || reason)); });
    fetchJson<Permissions>(PERMISSIONS_URL, controller.signal)
      .then((permissions) => setAccess({ state: 'signed_in', permissions }))
      .catch((reason) => {
        if (controller.signal.aborted) return;
        setAccess({ state: reason instanceof ApiError && reason.status === 401 ? 'anonymous' : 'error' });
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!resourceType) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ resource_type: resourceType });
    setLoading(true);
    setError('');
    setBuilderError('');
    // The graph definition is only needed for labels (and later the form), so its failure is not fatal.
    Promise.allSettled([
      fetchJson<RulesList>(`${API_BASE}rules?${params}`, controller.signal),
      fetchJson<BuilderOptions>(`${API_BASE}rule-builder-options?${params}`, controller.signal),
    ]).then(([rulesResult, builderResult]) => {
      if (controller.signal.aborted) return;
      if (rulesResult.status === 'fulfilled') setRules(rulesResult.value);
      else setError(String(rulesResult.reason?.message || rulesResult.reason));
      if (builderResult.status === 'fulfilled') setBuilder(builderResult.value);
      else setBuilderError(String(builderResult.reason?.message || builderResult.reason));
      setLoading(false);
    });
    return () => controller.abort();
  }, [resourceType, reload]);

  function selectResource(value: string) {
    setResourceType(value);
    setRules(null);
    setBuilder(null);
    setBuilderError('');
    setEditing(null);
    setError('');
  }

  function saved() {
    setEditing(null);
    setReload((value) => value + 1);
  }

  async function deleteRule(rule: CustomRule) {
    if (!window.confirm(`Usunąć zasadę „${rule.label}”? Tej operacji nie można cofnąć.`)) return;
    setDeleting(rule.id);
    setError('');
    try {
      await sendJson('DELETE', `${API_BASE}rules/${encodeURIComponent(rule.id)}`);
      setReload((value) => value + 1);
    } catch (reason) {
      setError(String((reason as Error).message || reason));
    } finally {
      setDeleting('');
    }
  }

  const canEdit = access.state === 'signed_in' && !!rules
    && access.permissions.editable_graph_ids.includes(rules.model.graph_id);
  // Adding and editing need the graph definition for the form's choices.
  const canManage = canEdit && !!builder && builder.kinds.length > 0;
  const labels = optionLabels(builder);
  const kinds = new Map((builder?.kinds ?? []).map((kind) => [kind.kind, kind]));

  if (!catalog) {
    return <section class="panel loading-panel" aria-live="polite">{error || 'Ładowanie typów zasobów…'}</section>;
  }

  return <>
    {access.state === 'anonymous' && <div class="notice-banner">
      Przeglądasz zasady bez logowania. Aby je dodawać i usuwać, <a href={LOGIN_URL}>zaloguj się w Arches</a>.
    </div>}
    {access.state === 'error' && <div class="notice-banner">Nie udało się sprawdzić uprawnień w Arches — zasady są tylko do odczytu.</div>}

    <section class="panel controls-panel">
      <div class="section-heading">
        <div><span class="step-label">01 / TYP ZASOBU</span><h2>Wybierz typ zasobu</h2></div>
        {access.state === 'signed_in' && <p>Zalogowano jako {access.permissions.username}</p>}
      </div>
      <div class="filter-grid">
        <label>Typ zasobu
          <select value={resourceType} onChange={(event) => selectResource(event.currentTarget.value)}>
            <option value="">Wybierz typ zasobu</option>
            {catalog.models.map((model) => <option key={model.resource_type} value={model.resource_type}>{model.name}</option>)}
          </select>
        </label>
      </div>
    </section>

    {error && <div class="error-banner" role="alert">{error}</div>}
    {resourceType && loading && !rules && <section class="panel loading-panel" aria-live="polite">Ładowanie zasad…</section>}

    {rules && <>
      {access.state === 'signed_in' && !canEdit && <div class="notice-banner">
        Nie masz uprawnień do edycji zasobów {rules.model.name} w Arches, więc zasady tego typu są tylko do odczytu.
      </div>}
      {builderError && <div class="notice-banner">
        Nie udało się wczytać definicji grafu ({builderError}). Pola zasad są pokazane jako identyfikatory.
      </div>}

      <section class="panel controls-panel rules-panel">
        <div class="section-heading">
          <div><span class="step-label">02 / ZASADY WŁASNE</span><h2>Zasady dodane przez użytkowników</h2></div>
          {canManage && !editing
            ? <button type="button" class="primary-button" onClick={() => setEditing('new')}>Dodaj zasadę <span aria-hidden="true">+</span></button>
            : <p>Uruchamiane w raporcie razem z wbudowanymi.</p>}
        </div>
        {editing && builder && <RuleForm
          key={editing === 'new' ? 'new' : editing.id}
          builder={builder}
          rule={editing === 'new' ? null : editing}
          onSaved={saved}
          onCancel={() => setEditing(null)}
        />}
        {rules.custom.length === 0
          ? <p class="empty-state">Brak własnych zasad dla {rules.model.name}.</p>
          : <div class="rule-card-list">{rules.custom.map((rule) => <RuleCard
              key={rule.id}
              rule={rule}
              kind={kinds.get(rule.kind)}
              labels={labels}
              canEdit={canEdit}
              deleting={deleting === rule.id}
              onDelete={deleteRule}
              onEdit={canManage && !editing ? setEditing : null}
            />)}</div>}
      </section>

      <section class="panel controls-panel rules-panel">
        <div class="section-heading">
          <div><span class="step-label">03 / ZASADY WBUDOWANE</span><h2>Zasady wbudowane</h2></div>
          <p>Zdefiniowane w kodzie, tylko do odczytu.</p>
        </div>
        <div class="rule-grid">
          {rules.builtin.map((rule) => <div key={rule.id} class="rule-choice">
            <span><strong>{rule.label}</strong><small>{rule.description}</small></span>
          </div>)}
        </div>
      </section>
    </>}
  </>;
}
