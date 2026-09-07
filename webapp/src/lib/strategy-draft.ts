/**
 * The strategy builder's internal "draft" shape, plus conversion to/from
 * the real `StrategyDefinition` the API expects.
 *
 * Deliberate v1 scope: fase 1's condition schema allows arbitrarily nested
 * and/or/not trees, but a visual builder for arbitrary trees is a lot of
 * interface for a first version. The builder instead supports one flat
 * group of comparisons per side (entry/exit), combined with a single
 * and/or -- covering both of phase 1's own example strategies (a lone
 * crossover, and an AND of two comparisons). `definitionToDraft` best-
 * effort-parses an existing definition into this shape and flags when it
 * can't (a nested group, or a `not`), so editing degrades honestly instead
 * of silently mangling a more complex definition.
 */
import type { Comparison, ComparisonOp, ConditionNode, IndicatorConfig, Operand, ParamValue, StrategyDefinition } from "./types";
import { indicatorSpecByName } from "./indicator-catalog";

let idCounter = 0;
export function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}_${idCounter}`;
}

export type OperandDraft = { kind: "column"; value: string } | { kind: "number"; value: number };

export interface ComparisonRowDraft {
  id: string;
  left: OperandDraft;
  op: ComparisonOp;
  right: OperandDraft;
}

export interface ConditionGroupDraft {
  op: "and" | "or";
  rows: ComparisonRowDraft[];
}

export type IndicatorParamDraft =
  | { mode: "fixed"; value: number }
  | { mode: "range"; default: number; min: number; max: number; step: number };

export interface IndicatorDraft {
  id: string;
  name: string;
  alias: string;
  params: Record<string, IndicatorParamDraft>;
}

export interface StrategyDraft {
  name: string;
  description: string;
  timeframe: string;
  indicators: IndicatorDraft[];
  entry: ConditionGroupDraft;
  hasExit: boolean;
  exit: ConditionGroupDraft;
  stopLossPct: number;
  takeProfitPct: number;
  hasTrailingStop: boolean;
  trailingStopPct: number;
}

export function emptyComparisonRow(): ComparisonRowDraft {
  return {
    id: nextId("row"),
    left: { kind: "column", value: "close" },
    op: "gt",
    right: { kind: "number", value: 0 },
  };
}

export function emptyGroup(): ConditionGroupDraft {
  return { op: "and", rows: [emptyComparisonRow()] };
}

export function defaultIndicatorDraft(name: string, alias: string): IndicatorDraft {
  const spec = indicatorSpecByName(name);
  const params: Record<string, IndicatorParamDraft> = {};
  spec?.params.forEach((p) => {
    params[p.name] = { mode: "fixed", value: p.defaultValue };
  });
  return { id: nextId("ind"), name, alias, params };
}

export function emptyDraft(): StrategyDraft {
  return {
    name: "",
    description: "",
    timeframe: "1h",
    indicators: [],
    entry: emptyGroup(),
    hasExit: true,
    exit: emptyGroup(),
    stopLossPct: 2,
    takeProfitPct: 6,
    hasTrailingStop: false,
    trailingStopPct: 3,
  };
}

/** All operand choices a condition row can reference, given the configured indicators. */
export function operandColumnOptions(indicators: IndicatorDraft[]): { value: string; label: string }[] {
  const columns = [
    { value: "open", label: "open" },
    { value: "high", label: "high" },
    { value: "low", label: "low" },
    { value: "close", label: "close" },
    { value: "volume", label: "volume" },
  ];
  for (const ind of indicators) {
    const spec = indicatorSpecByName(ind.name);
    if (spec) columns.push(...spec.outputs(ind.alias));
  }
  return columns;
}

function operandToApi(o: OperandDraft): Operand {
  return o.kind === "number" ? o.value : o.value;
}

function rowToComparison(row: ComparisonRowDraft): Comparison {
  return { type: "comparison", left: operandToApi(row.left), op: row.op, right: operandToApi(row.right) };
}

function groupToCondition(group: ConditionGroupDraft): ConditionNode {
  const comparisons = group.rows.map(rowToComparison);
  if (comparisons.length === 1) return comparisons[0];
  return { type: "logical", op: group.op, conditions: comparisons };
}

function indicatorParamsToApi(params: Record<string, IndicatorParamDraft>): Record<string, ParamValue> {
  const out: Record<string, ParamValue> = {};
  for (const [key, p] of Object.entries(params)) {
    out[key] = p.mode === "fixed" ? p.value : { default: p.default, min: p.min, max: p.max, step: p.step };
  }
  return out;
}

function indicatorToApi(ind: IndicatorDraft): IndicatorConfig {
  return { name: ind.name, alias: ind.alias, params: indicatorParamsToApi(ind.params) };
}

export function draftToDefinition(draft: StrategyDraft): StrategyDefinition {
  return {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    timeframe: draft.timeframe.trim() || null,
    indicators: draft.indicators.map(indicatorToApi),
    entry_conditions: groupToCondition(draft.entry),
    exit_conditions: draft.hasExit ? groupToCondition(draft.exit) : null,
    risk_management: {
      stop_loss_pct: draft.stopLossPct / 100,
      take_profit_pct: draft.takeProfitPct / 100,
      trailing_stop_pct: draft.hasTrailingStop ? draft.trailingStopPct / 100 : null,
    },
  };
}

function operandFromApi(o: Operand): OperandDraft {
  return typeof o === "number" ? { kind: "number", value: o } : { kind: "column", value: o };
}

/** Parses a ConditionNode into a flat group, or returns null if it's more
 * complex than the builder supports (nested logical, a `not`, mixed types).
 */
function conditionToGroup(node: ConditionNode): ConditionGroupDraft | null {
  if (node.type === "comparison") {
    return { op: "and", rows: [{ id: nextId("row"), left: operandFromApi(node.left), op: node.op, right: operandFromApi(node.right) }] };
  }
  if (node.op === "not") return null;
  if (node.conditions.some((c) => c.type !== "comparison")) return null;
  return {
    op: node.op,
    rows: node.conditions.map((c) => {
      const cmp = c as Comparison;
      return { id: nextId("row"), left: operandFromApi(cmp.left), op: cmp.op, right: operandFromApi(cmp.right) };
    }),
  };
}

export interface ParsedDraft {
  draft: StrategyDraft;
  unsupportedEntry: boolean;
  unsupportedExit: boolean;
}

export function definitionToDraft(definition: StrategyDefinition): ParsedDraft {
  const indicators: IndicatorDraft[] = definition.indicators.map((ind) => {
    const params: Record<string, IndicatorParamDraft> = {};
    for (const [key, value] of Object.entries(ind.params)) {
      params[key] =
        typeof value === "number"
          ? { mode: "fixed", value }
          : { mode: "range", default: value.default, min: value.min, max: value.max, step: value.step ?? 1 };
    }
    return { id: nextId("ind"), name: ind.name, alias: ind.alias, params };
  });

  const entryGroup = conditionToGroup(definition.entry_conditions);
  const exitGroup = definition.exit_conditions ? conditionToGroup(definition.exit_conditions) : emptyGroup();

  const riskManagement = definition.risk_management;
  return {
    draft: {
      name: definition.name,
      description: definition.description ?? "",
      timeframe: definition.timeframe ?? "1h",
      indicators,
      entry: entryGroup ?? emptyGroup(),
      hasExit: Boolean(definition.exit_conditions),
      exit: exitGroup ?? emptyGroup(),
      stopLossPct: riskManagement.stop_loss_pct * 100,
      takeProfitPct: riskManagement.take_profit_pct * 100,
      hasTrailingStop: riskManagement.trailing_stop_pct !== null && riskManagement.trailing_stop_pct !== undefined,
      trailingStopPct: (riskManagement.trailing_stop_pct ?? 0.03) * 100,
    },
    unsupportedEntry: entryGroup === null,
    unsupportedExit: Boolean(definition.exit_conditions) && exitGroup === null,
  };
}

export function suggestAlias(name: string, existing: string[]): string {
  let n = 1;
  let candidate = `${name}_${n}`;
  while (existing.includes(candidate)) {
    n += 1;
    candidate = `${name}_${n}`;
  }
  return candidate;
}
