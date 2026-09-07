"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/Button";
import { FieldGroup, Label, NumberInput, Select, TextInput } from "@/components/ui/Field";
import { ErrorBanner } from "@/components/ui/EmptyState";

const METRICS = ["sharpe_ratio", "sortino_ratio", "total_return_pct", "profit_factor"];

export function StartOptimizationForm({ strategyId, onDone }: { strategyId: string; onDone: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [exchange, setExchange] = useState("binance");
  const [trainDays, setTrainDays] = useState(60);
  const [testDays, setTestDays] = useState(20);
  const [nTrials, setNTrials] = useState(30);
  const [metric, setMetric] = useState("sharpe_ratio");

  const mutation = useMutation({
    mutationFn: () =>
      api.createOptimization(strategyId, {
        exchange,
        symbol,
        timeframe,
        train_period_days: trainDays,
        test_period_days: testDays,
        n_trials: nTrials,
        metric,
      }),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["optimizations", strategyId] });
      router.push(`/optimizations/${job.id}`);
    },
  });

  return (
    <div className="border border-[var(--border)] rounded-[var(--radius-md)] p-4 bg-[var(--bg)] mt-3">
      <FieldGroup className="grid-cols-2 md:grid-cols-4">
        <div>
          <Label>Exchange</Label>
          <TextInput value={exchange} onChange={(e) => setExchange(e.target.value)} />
        </div>
        <div>
          <Label>Symbol</Label>
          <TextInput value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="BTC/USDT" />
        </div>
        <div>
          <Label>Timeframe</Label>
          <TextInput value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="1h" />
        </div>
        <div>
          <Label>Metric to maximize</Label>
          <Select value={metric} onChange={(e) => setMetric(e.target.value)}>
            {METRICS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label hint="days">Train window</Label>
          <NumberInput value={trainDays} min={1} onChange={(e) => setTrainDays(Number(e.target.value))} />
        </div>
        <div>
          <Label hint="days">Test window</Label>
          <NumberInput value={testDays} min={1} onChange={(e) => setTestDays(Number(e.target.value))} />
        </div>
        <div>
          <Label hint="per walk-forward window">Trials</Label>
          <NumberInput value={nTrials} min={1} onChange={(e) => setNTrials(Number(e.target.value))} />
        </div>
      </FieldGroup>

      {mutation.error && (
        <div className="mt-3">
          <ErrorBanner
            message={mutation.error instanceof ApiError ? mutation.error.message : "Could not start the optimization."}
          />
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <Button variant="primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending ? "Starting…" : "Run optimization"}
        </Button>
        <Button variant="ghost" onClick={onDone} type="button">
          Cancel
        </Button>
      </div>
    </div>
  );
}
