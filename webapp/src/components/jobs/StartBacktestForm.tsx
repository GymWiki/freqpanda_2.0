"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/Button";
import { FieldGroup, Label, NumberInput, TextInput } from "@/components/ui/Field";
import { ErrorBanner } from "@/components/ui/EmptyState";

export function StartBacktestForm({ strategyId, onDone }: { strategyId: string; onDone: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [exchange, setExchange] = useState("binance");
  const [feePct, setFeePct] = useState(0.1);
  const [slippagePct, setSlippagePct] = useState(0);
  const [initialCapital, setInitialCapital] = useState(10000);

  const mutation = useMutation({
    mutationFn: () =>
      api.createBacktest(strategyId, {
        exchange,
        symbol,
        timeframe,
        fee_pct: feePct / 100,
        slippage_pct: slippagePct / 100,
        initial_capital: initialCapital,
      }),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["backtests", strategyId] });
      router.push(`/backtests/${job.id}`);
    },
  });

  return (
    <div className="border border-[var(--border)] rounded-[var(--radius-md)] p-4 bg-[var(--bg)] mt-3">
      <FieldGroup className="grid-cols-2 md:grid-cols-5">
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
          <Label>Fee %</Label>
          <NumberInput value={feePct} step={0.01} onChange={(e) => setFeePct(Number(e.target.value))} />
        </div>
        <div>
          <Label>Slippage %</Label>
          <NumberInput value={slippagePct} step={0.01} onChange={(e) => setSlippagePct(Number(e.target.value))} />
        </div>
        <div>
          <Label>Initial capital</Label>
          <NumberInput value={initialCapital} step={100} onChange={(e) => setInitialCapital(Number(e.target.value))} />
        </div>
      </FieldGroup>

      {mutation.error && (
        <div className="mt-3">
          <ErrorBanner
            message={
              mutation.error instanceof ApiError
                ? mutation.error.message
                : "Could not start the backtest. Make sure this symbol/timeframe has been backfilled by the data pipeline."
            }
          />
        </div>
      )}

      <div className="flex gap-2 mt-4">
        <Button variant="primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          {mutation.isPending ? "Starting…" : "Run backtest"}
        </Button>
        <Button variant="ghost" onClick={onDone} type="button">
          Cancel
        </Button>
      </div>
    </div>
  );
}
