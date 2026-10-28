import type { BuilderOptions, GraphRelation } from './api';

export function relationLabel(relation: GraphRelation): string {
  if (relation.direction === 'incoming') {
    return `${relation.label} (przychodząca${relation.alias ? `: ${relation.alias}` : ''})`;
  }
  const targets = relation.target_graphs.map((graph) => graph.name).join(', ');
  return targets ? `${relation.label} → ${targets}` : relation.label;
}

/** Builder IDs (field node IDs, "out:…"/"in:…" relation IDs) mapped to readable labels. */
export function optionLabels(builder: BuilderOptions | null): Map<string, string> {
  const labels = new Map<string, string>();
  if (!builder) return labels;
  for (const field of [...builder.fields, ...builder.completeness_roots, ...builder.numbering, ...builder.grouping.fields]) {
    labels.set(field.node_id, field.label);
  }
  for (const relation of builder.relations) labels.set(relation.id, relationLabel(relation));
  return labels;
}
