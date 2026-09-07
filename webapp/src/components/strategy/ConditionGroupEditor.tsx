"use client";

import { COMPARISON_OPS } from "@/lib/indicator-catalog";
import { ComparisonRowDraft, ConditionGroupDraft, emptyComparisonRow, IndicatorDraft, operandColumnOptions, OperandDraft } from "@/lib/strategy-draft";
import { Button } from "@/components/ui/Button";
import { NumberInput, Select } from "@/components/ui/Field";

function OperandEditor({
  operand,
  columns,
  onChange,
}: {
  operand: OperandDraft;
  columns: { value: string; label: string }[];
  onChange: (next: OperandDraft) => void;
}) {
  return (
    <div className="flex gap-1.5 flex-1 min-w-0">
      <Select
        className="w-24 shrink-0"
        value={operand.kind}
        onChange={(e) => {
          const kind = e.target.value as "column" | "number";
          onChange(kind === "column" ? { kind, value: columns[0]?.value ?? "close" } : { kind, value: 0 });
        }}
      >
        <option value="column">column</option>
        <option value="number">number</option>
      </Select>
      {operand.kind === "column" ? (
        <Select className="flex-1 min-w-0" value={operand.value} onChange={(e) => onChange({ kind: "column", value: e.target.value })}>
          {columns.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </Select>
      ) : (
        <NumberInput
          className="flex-1 min-w-0"
          value={operand.value}
          onChange={(e) => onChange({ kind: "number", value: Number(e.target.value) })}
        />
      )}
    </div>
  );
}

export function ConditionGroupEditor({
  group,
  indicators,
  onChange,
}: {
  group: ConditionGroupDraft;
  indicators: IndicatorDraft[];
  onChange: (next: ConditionGroupDraft) => void;
}) {
  const columns = operandColumnOptions(indicators);

  function updateRow(id: string, patch: Partial<ComparisonRowDraft>) {
    onChange({ ...group, rows: group.rows.map((r) => (r.id === id ? { ...r, ...patch } : r)) });
  }

  function removeRow(id: string) {
    onChange({ ...group, rows: group.rows.filter((r) => r.id !== id) });
  }

  function addRow() {
    onChange({ ...group, rows: [...group.rows, emptyComparisonRow()] });
  }

  return (
    <div className="space-y-2.5">
      {group.rows.map((row, i) => (
        <div key={row.id} className="flex items-center gap-2">
          {i === 0 ? (
            <span className="w-12 shrink-0 text-xs font-mono text-[var(--text-faint)]">IF</span>
          ) : (
            <Select
              className="w-12 shrink-0 px-1 text-center font-mono uppercase"
              value={group.op}
              onChange={(e) => onChange({ ...group, op: e.target.value as "and" | "or" })}
            >
              <option value="and">AND</option>
              <option value="or">OR</option>
            </Select>
          )}
          <OperandEditor operand={row.left} columns={columns} onChange={(v) => updateRow(row.id, { left: v })} />
          <Select className="w-40 shrink-0" value={row.op} onChange={(e) => updateRow(row.id, { op: e.target.value as ComparisonRowDraft["op"] })}>
            {COMPARISON_OPS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <OperandEditor operand={row.right} columns={columns} onChange={(v) => updateRow(row.id, { right: v })} />
          <Button variant="ghost" type="button" onClick={() => removeRow(row.id)} aria-label="Remove condition">
            ✕
          </Button>
        </div>
      ))}
      <Button variant="ghost" type="button" onClick={addRow} className="px-0 text-[var(--accent)] hover:text-[var(--accent-strong)]">
        + Add condition
      </Button>
    </div>
  );
}
