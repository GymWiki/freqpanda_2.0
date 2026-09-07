"use client";

import { useMemo, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { Label, TextInput, Select, HelpText, ErrorText } from "@/components/ui/Field";
import { ErrorBanner } from "@/components/ui/EmptyState";
import { IndicatorsEditor } from "./IndicatorsEditor";
import { ConditionGroupEditor } from "./ConditionGroupEditor";
import { RiskEditor } from "./RiskEditor";
import { draftToDefinition, emptyGroup, StrategyDraft } from "@/lib/strategy-draft";
import { validateDraft } from "@/lib/validate-draft";
import type { StrategyDefinition } from "@/lib/types";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

function StepLabel({ n, title, subtitle }: { n: number; title: string; subtitle: string }) {
  return (
    <div className="flex items-baseline gap-3 mb-1">
      <span className="font-mono text-xs text-[var(--accent)]">{String(n).padStart(2, "0")}</span>
      <div>
        <h2 className="font-display font-semibold text-[15px]">{title}</h2>
        <p className="text-xs text-[var(--text-muted)]">{subtitle}</p>
      </div>
    </div>
  );
}

export function StrategyBuilder({
  initialDraft,
  parseWarnings,
  submitLabel,
  onSubmit,
  submitting,
  submitError,
}: {
  initialDraft: StrategyDraft;
  parseWarnings?: string[];
  submitLabel: string;
  onSubmit: (definition: StrategyDefinition) => void;
  submitting: boolean;
  submitError?: string | null;
}) {
  const [draft, setDraft] = useState<StrategyDraft>(initialDraft);
  const [showErrors, setShowErrors] = useState(false);

  const errors = useMemo(() => validateDraft(draft), [draft]);

  function patch(p: Partial<StrategyDraft>) {
    setDraft((d) => ({ ...d, ...p }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (errors.length > 0) {
      setShowErrors(true);
      return;
    }
    onSubmit(draftToDefinition(draft));
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Panel>
        <StepLabel n={1} title="Basics" subtitle="Name your strategy and pick a default timeframe." />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
          <div>
            <Label hint="required">Name</Label>
            <TextInput value={draft.name} onChange={(e) => patch({ name: e.target.value })} placeholder="ema_crossover_v2" />
          </div>
          <div>
            <Label>Timeframe</Label>
            <Select value={draft.timeframe} onChange={(e) => patch({ timeframe: e.target.value })}>
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </Select>
          </div>
          <div className="md:col-span-2">
            <Label>Description</Label>
            <TextInput value={draft.description} onChange={(e) => patch({ description: e.target.value })} placeholder="Optional" />
          </div>
        </div>
      </Panel>

      <Panel>
        <StepLabel n={2} title="Indicators" subtitle="Technical indicators available to reference in your conditions." />
        <div className="mt-4">
          <IndicatorsEditor indicators={draft.indicators} onChange={(indicators) => patch({ indicators })} />
        </div>
      </Panel>

      <Panel>
        <StepLabel n={3} title="Entry conditions" subtitle="When the strategy opens a position." />
        {parseWarnings?.includes("entry") && (
          <div className="mt-3 mb-3">
            <ErrorBanner message="This strategy's entry conditions are more complex than the visual builder supports (nested groups or a NOT) -- shown reset to a single placeholder condition. Saving will overwrite the original logic." />
          </div>
        )}
        <div className="mt-4">
          <ConditionGroupEditor group={draft.entry} indicators={draft.indicators} onChange={(entry) => patch({ entry })} />
        </div>
      </Panel>

      <Panel>
        <StepLabel n={4} title="Exit conditions" subtitle="Optional discretionary exit, on top of the risk limits below." />
        <label className="flex items-center gap-2 text-sm text-[var(--text-muted)] mt-3 mb-3">
          <input type="checkbox" checked={draft.hasExit} onChange={(e) => patch({ hasExit: e.target.checked, exit: draft.hasExit ? draft.exit : emptyGroup() })} />
          Use exit conditions
        </label>
        {parseWarnings?.includes("exit") && (
          <div className="mb-3">
            <ErrorBanner message="This strategy's exit conditions are more complex than the visual builder supports -- shown reset to a single placeholder condition. Saving will overwrite the original logic." />
          </div>
        )}
        {draft.hasExit && <ConditionGroupEditor group={draft.exit} indicators={draft.indicators} onChange={(exit) => patch({ exit })} />}
      </Panel>

      <Panel>
        <StepLabel n={5} title="Risk management" subtitle="Required stop-loss/take-profit, optional trailing stop." />
        <div className="mt-4">
          <RiskEditor draft={draft} onChange={patch} />
        </div>
      </Panel>

      {showErrors && errors.length > 0 && (
        <div className="space-y-1">
          {errors.map((err) => (
            <ErrorText key={err}>{err}</ErrorText>
          ))}
        </div>
      )}
      {submitError && <ErrorBanner message={submitError} />}

      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </Button>
        <HelpText>Validated against the strategy schema when you save.</HelpText>
      </div>
    </form>
  );
}
