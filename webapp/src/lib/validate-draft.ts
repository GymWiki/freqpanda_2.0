import type { StrategyDraft } from "./strategy-draft";

const IDENTIFIER_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Client-side mirror of the fase-1 structural checks that matter most for
 * a form -- unique/valid aliases, required risk bounds -- so a mistake
 * surfaces next to the field that caused it instead of only as a 422 after
 * submit. The API's own validation is still the final word (see the
 * `validate_definition` semantic layer it runs, which this intentionally
 * does not try to fully replicate).
 */
export function validateDraft(draft: StrategyDraft): string[] {
  const errors: string[] = [];

  if (!draft.name.trim()) errors.push("Name is required.");

  const aliases = draft.indicators.map((i) => i.alias);
  const seen = new Set<string>();
  for (const alias of aliases) {
    if (!IDENTIFIER_RE.test(alias)) {
      errors.push(`Indicator alias "${alias}" must be a valid identifier (letters, digits, underscore).`);
    }
    if (seen.has(alias)) errors.push(`Duplicate indicator alias "${alias}" -- aliases must be unique.`);
    seen.add(alias);
  }

  if (draft.entry.rows.length === 0) errors.push("Add at least one entry condition.");
  if (draft.hasExit && draft.exit.rows.length === 0) errors.push("Add at least one exit condition, or turn exit conditions off.");

  if (!(draft.stopLossPct > 0 && draft.stopLossPct < 100)) errors.push("Stop-loss must be between 0 and 100%.");
  if (!(draft.takeProfitPct > 0)) errors.push("Take-profit must be greater than 0%.");
  if (draft.hasTrailingStop && !(draft.trailingStopPct > 0 && draft.trailingStopPct < 100)) {
    errors.push("Trailing stop must be between 0 and 100%.");
  }

  for (const ind of draft.indicators) {
    for (const [paramName, p] of Object.entries(ind.params)) {
      if (p.mode === "range" && !(p.min <= p.default && p.default <= p.max)) {
        errors.push(`${ind.alias}.${paramName}: default must be between min and max.`);
      }
      if (p.mode === "range" && p.min > p.max) {
        errors.push(`${ind.alias}.${paramName}: min must be <= max.`);
      }
    }
  }

  return errors;
}
