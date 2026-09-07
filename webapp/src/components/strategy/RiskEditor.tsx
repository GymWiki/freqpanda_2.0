"use client";

import type { StrategyDraft } from "@/lib/strategy-draft";
import { Label, NumberInput } from "@/components/ui/Field";

export function RiskEditor({
  draft,
  onChange,
}: {
  draft: StrategyDraft;
  onChange: (patch: Partial<StrategyDraft>) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div>
        <Label hint="required">Stop-loss %</Label>
        <NumberInput
          value={draft.stopLossPct}
          min={0}
          max={99}
          step="any"
          onChange={(e) => onChange({ stopLossPct: Number(e.target.value) })}
        />
      </div>
      <div>
        <Label hint="required">Take-profit %</Label>
        <NumberInput value={draft.takeProfitPct} min={0} step="any" onChange={(e) => onChange({ takeProfitPct: Number(e.target.value) })} />
      </div>
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <Label>Trailing stop %</Label>
          <label className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
            <input type="checkbox" checked={draft.hasTrailingStop} onChange={(e) => onChange({ hasTrailingStop: e.target.checked })} />
            enabled
          </label>
        </div>
        <NumberInput
          value={draft.trailingStopPct}
          min={0}
          max={99}
          step="any"
          disabled={!draft.hasTrailingStop}
          onChange={(e) => onChange({ trailingStopPct: Number(e.target.value) })}
        />
      </div>
    </div>
  );
}
