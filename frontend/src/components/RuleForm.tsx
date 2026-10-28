import { useState } from 'preact/hooks';

import {
  API_BASE,
  sendJson,
  type BuilderOptions,
  type CustomRule,
  type GraphField,
  type GraphRelation,
  type ParamValue,
  type RuleKind,
  type RuleParam,
} from '../lib/api';
import { relationLabel } from '../lib/ruleLabels';

type Choice = { value: string; label: string; hint: string };
type ChoiceGroup = { label: string; choices: Choice[] };

type Props = {
  builder: BuilderOptions;
  rule: CustomRule | null;
  onSaved: () => void;
  onCancel: () => void;
};

/** Same prefix pattern as the builtin Special Find Order Number rule. */
const PREFIX_PATTERN = '[A-Za-z]*([0-9]+)';

const NUMBER_FORMATS: { id: string; label: string; pattern: string | null }[] = [
  { id: 'plain', label: 'Sama liczba (np. 12)', pattern: null },
  { id: 'prefix', label: 'Prefiks literowy + liczba (np. M12, SF7)', pattern: PREFIX_PATTERN },
  { id: 'last', label: 'Ostatnia liczba w tekście (np. SF-2024-15 → 15)', pattern: '.*?([0-9]+)' },
];

const PARAM_HINTS: Record<string, string> = {
  max_count: 'Puste = bez limitu.',
  excluded_fields: 'Zaznaczenie grupy pól pomija wszystkie pola w niej.',
  group_by: 'Numery są porównywane osobno w każdej grupie, np. w każdym trenchu.',
  base_scope_only: 'Porównuj tylko rekordy z wybranego okresu i trench, bez dołączonych przez Harris.',
  start_at: 'Puste = od najmniejszego numeru w grupie.',
};

const isCustomPattern = (value: ParamValue | undefined) =>
  typeof value === 'string' && !NUMBER_FORMATS.some((format) => format.pattern === value);

const fieldChoices = (fields: GraphField[]): Choice[] => fields.map((field) => ({
  value: field.node_id,
  label: field.label,
  hint: field.datatype === 'semantic' ? 'grupa pól' : field.datatype,
}));

const relationChoices = (relations: GraphRelation[]): Choice[] =>
  relations.map((relation) => ({ value: relation.id, label: relationLabel(relation), hint: relation.datatype }));

/** Options for a param, taken from the rule-builder-options list named by param.options. */
function choiceGroups(param: RuleParam, builder: BuilderOptions): ChoiceGroup[] {
  switch (param.options) {
    case 'relations': return [{ label: 'Relacje', choices: relationChoices(builder.relations) }];
    case 'fields': return [{ label: 'Pola', choices: fieldChoices(builder.fields) }];
    case 'completeness_roots': return [{ label: 'Pola i grupy pól', choices: fieldChoices(builder.completeness_roots) }];
    case 'numbering': return [{ label: 'Pola', choices: fieldChoices(builder.numbering) }];
    case 'grouping': return [
      { label: 'Pola', choices: fieldChoices(builder.grouping.fields) },
      { label: 'Relacje', choices: relationChoices(builder.grouping.relations) },
    ];
    default: return [];
  }
}

function defaults(kind: RuleKind): Record<string, ParamValue> {
  return Object.fromEntries(kind.params.map((param) => [param.name, param.default]));
}

function ChoiceList({ groups, selected, onChange }: {
  groups: ChoiceGroup[];
  selected: string[];
  onChange: (value: string[]) => void;
}) {
  const [filter, setFilter] = useState('');
  const query = filter.trim().toLocaleLowerCase('pl');
  const toggle = (value: string) => onChange(
    selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value],
  );
  const visible = groups
    .map((group) => ({
      ...group,
      choices: group.choices.filter((choice) => !query || choice.label.toLocaleLowerCase('pl').includes(query)),
    }))
    .filter((group) => group.choices.length > 0);

  return <div class="choice-list">
    <div class="choice-list__toolbar">
      <input type="search" placeholder="Szukaj pola…" value={filter} onInput={(event) => setFilter(event.currentTarget.value)} />
      <span>Wybrano: {selected.length}</span>
      {selected.length > 0 && <button type="button" class="text-button" onClick={() => onChange([])}>Wyczyść</button>}
    </div>
    <div class="choice-list__options">
      {visible.length === 0 && <p class="choice-list__empty">Brak pasujących pozycji.</p>}
      {visible.map((group) => <fieldset key={group.label}>
        {groups.length > 1 && <legend>{group.label}</legend>}
        {group.choices.map((choice) => <label key={choice.value} class="checkbox-line">
          <input type="checkbox" checked={selected.includes(choice.value)} onChange={() => toggle(choice.value)} />
          <span>{choice.label} <small>{choice.hint}</small></span>
        </label>)}
      </fieldset>)}
    </div>
  </div>;
}

/** Presets instead of a raw regex; the custom pattern stays available as an advanced option. */
function NumberFormatField({ title, value, custom, onChange, onCustom }: {
  title: preact.JSX.Element;
  value: ParamValue;
  custom: boolean;
  onChange: (value: ParamValue) => void;
  onCustom: (custom: boolean) => void;
}) {
  const selected = custom ? 'custom' : NUMBER_FORMATS.find((format) => format.pattern === value)?.id ?? 'plain';
  function select(id: string) {
    if (id === 'custom') {
      onCustom(true);  // The current preset's pattern is a starting point for editing.
      return;
    }
    onCustom(false);
    onChange(NUMBER_FORMATS.find((format) => format.id === id)?.pattern ?? null);
  }

  return <div class="form-field">
    <label class="form-field">{title}
      <select value={selected} onChange={(event) => select(event.currentTarget.value)}>
        {NUMBER_FORMATS.map((format) => <option key={format.id} value={format.id}>{format.label}</option>)}
        <option value="custom">Własny wzorzec (zaawansowane)</option>
      </select>
    </label>
    {custom
      ? <>
        <input
          type="text"
          aria-label="Własny wzorzec numeru"
          placeholder="np. [A-Z]+-([0-9]+)"
          value={typeof value === 'string' ? value : ''}
          onInput={(event) => onChange(event.currentTarget.value || null)}
        />
        <small>Wyrażenie regularne dopasowane do całej wartości; grupa w nawiasach wskazuje część z numerem.</small>
      </>
      : <small>Dobierany automatycznie do typu pola numeru; możesz go zmienić.</small>}
  </div>;
}

function ParamField({ param, value, groups, customPattern, onChange, onCustomPattern }: {
  param: RuleParam;
  value: ParamValue;
  groups: ChoiceGroup[];
  customPattern: boolean;
  onChange: (value: ParamValue) => void;
  onCustomPattern: (custom: boolean) => void;
}) {
  // One element, so the flex-column label keeps the asterisk on the same line as the name.
  const title = <span class="form-field__label">{param.label}{param.required && <span class="required-mark"> *</span>}</span>;
  const hint = PARAM_HINTS[param.name] && <small>{PARAM_HINTS[param.name]}</small>;

  if (param.type === 'boolean') {
    return <div class="form-field form-field--wide">
      <label class="checkbox-line">
        <input type="checkbox" checked={value === true} onChange={(event) => onChange(event.currentTarget.checked)} />
        {param.label}
      </label>
      {hint}
    </div>;
  }

  if (param.type === 'choices') {
    const selected = Array.isArray(value) ? value : [];
    return <div class="form-field form-field--wide">
      {title}
      {hint}
      {/* Only "fields" is nullable: null means every field of the graph. */}
      {param.nullable && <div class="radio-row">
        <label class="checkbox-line"><input type="radio" name={param.name} checked={value === null} onChange={() => onChange(null)} /> Wszystkie</label>
        <label class="checkbox-line"><input type="radio" name={param.name} checked={value !== null} onChange={() => onChange([])} /> Wybrane</label>
      </div>}
      {value !== null && <ChoiceList groups={groups} selected={selected} onChange={onChange} />}
    </div>;
  }

  if (param.type === 'choice') {
    return <label class="form-field">{title}
      <select value={typeof value === 'string' ? value : ''} onChange={(event) => onChange(event.currentTarget.value || null)}>
        <option value="">Wybierz…</option>
        {groups.map((group) => <optgroup key={group.label} label={group.label}>
          {group.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
        </optgroup>)}
      </select>
      {hint}
    </label>;
  }

  if (param.type === 'integer') {
    return <label class="form-field">{title}
      <input
        type="number"
        step="1"
        min={param.minimum ?? undefined}
        placeholder={param.nullable ? 'brak' : undefined}
        value={typeof value === 'number' ? value : ''}
        onInput={(event) => onChange(event.currentTarget.value === '' ? null : Number(event.currentTarget.value))}
      />
      {hint}
    </label>;
  }

  return <NumberFormatField title={title} value={value} custom={customPattern} onChange={onChange} onCustom={onCustomPattern} />;
}

export default function RuleForm({ builder, rule, onSaved, onCancel }: Props) {
  const initialKind = builder.kinds.find((kind) => kind.kind === rule?.kind) ?? builder.kinds[0];
  const [kindId, setKindId] = useState(initialKind.kind);
  const [label, setLabel] = useState(rule?.label ?? '');
  const [description, setDescription] = useState(rule?.description ?? '');
  const [params, setParams] = useState<Record<string, ParamValue>>(
    rule ? { ...defaults(initialKind), ...rule.params } : defaults(initialKind),
  );
  const [customPattern, setCustomPattern] = useState(isCustomPattern(rule?.params.number_pattern));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const kind = builder.kinds.find((item) => item.kind === kindId) ?? initialKind;

  function changeKind(value: string) {
    const next = builder.kinds.find((item) => item.kind === value);
    if (!next) return;
    const restore = rule && next.kind === rule.kind;
    setKindId(next.kind);
    setParams(restore ? { ...defaults(next), ...rule.params } : defaults(next));
    setCustomPattern(restore ? isCustomPattern(rule.params.number_pattern) : false);
  }

  function updateParam(name: string, value: ParamValue) {
    setParams((current) => {
      const next = { ...current, [name]: value };
      // Like the builtin rules: numeric fields hold plain numbers, text fields may carry a letter prefix.
      if ((name === 'value_field' || name === 'value_fields') && 'number_pattern' in current && !customPattern) {
        const field = builder.numbering.find((item) => item.node_id === (Array.isArray(value) ? value[0] : value));
        if (field) next.number_pattern = field.datatype === 'number' ? null : PREFIX_PATTERN;
      }
      return next;
    });
  }

  async function submit(event: Event) {
    event.preventDefault();
    setSaving(true);
    setError('');
    const body = {
      resource_type: builder.model.resource_type,
      kind: kind.kind,
      label,
      description,
      params: Object.fromEntries(kind.params.map((param) => [param.name, params[param.name] ?? null])),
    };
    try {
      await sendJson(
        rule ? 'PUT' : 'POST',
        rule ? `${API_BASE}rules/${encodeURIComponent(rule.id)}` : `${API_BASE}rules`,
        body,
      );
      onSaved();
    } catch (reason) {
      setError(String((reason as Error).message || reason));
      setSaving(false);
    }
  }

  return <form class="rule-form" onSubmit={submit}>
    <h3>{rule ? `Edycja zasady: ${rule.label}` : `Nowa zasada dla ${builder.model.name}`}</h3>
    <div class="rule-form__grid">
      <label class="form-field">Rodzaj zasady
        <select value={kind.kind} onChange={(event) => changeKind(event.currentTarget.value)}>
          {builder.kinds.map((item) => <option key={item.kind} value={item.kind}>{item.label}</option>)}
        </select>
        <small>{kind.description}</small>
      </label>
      <label class="form-field"><span class="form-field__label">Nazwa<span class="required-mark"> *</span></span>
        <input type="text" required maxLength={120} value={label} onInput={(event) => setLabel(event.currentTarget.value)} />
      </label>
      <label class="form-field form-field--wide">Opis
        <textarea rows={2} maxLength={500} value={description} onInput={(event) => setDescription(event.currentTarget.value)} />
      </label>
      {kind.params.map((param) => <ParamField
        key={`${kind.kind}-${param.name}`}
        param={param}
        value={params[param.name] ?? null}
        groups={choiceGroups(param, builder)}
        customPattern={customPattern}
        onChange={(value) => updateParam(param.name, value)}
        onCustomPattern={setCustomPattern}
      />)}
    </div>
    {error && <div class="error-banner" role="alert">{error}</div>}
    <div class="form-actions">
      <button type="submit" class="primary-button" disabled={saving}>{saving ? 'Zapisywanie…' : 'Zapisz zasadę'}</button>
      <button type="button" class="secondary-button" disabled={saving} onClick={onCancel}>Anuluj</button>
    </div>
  </form>;
}
