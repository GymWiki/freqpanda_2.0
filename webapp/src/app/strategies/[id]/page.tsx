"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader, PageBody } from "@/components/layout/PageHeader";
import { Button, LinkButton } from "@/components/ui/Button";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { EmptyState, ErrorBanner, LoadingPanel } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/jobs/StatusPill";
import { StartBacktestForm } from "@/components/jobs/StartBacktestForm";
import { StartOptimizationForm } from "@/components/jobs/StartOptimizationForm";
import { api, ApiError } from "@/lib/api-client";
import { describeCondition } from "@/lib/describe-condition";
import { formatDateTime, formatNumber, formatPct } from "@/lib/format";
import { isParamRange } from "@/lib/types";

export default function StrategyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const [openForm, setOpenForm] = useState<"backtest" | "optimization" | null>(null);

  const strategyQuery = useQuery({ queryKey: ["strategy", id], queryFn: () => api.getStrategy(id) });
  const backtestsQuery = useQuery({ queryKey: ["backtests", id], queryFn: () => api.listBacktests(id) });
  const optimizationsQuery = useQuery({ queryKey: ["optimizations", id], queryFn: () => api.listOptimizations(id) });

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteStrategy(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["strategies"] });
      router.push("/");
    },
  });

  if (strategyQuery.isLoading) {
    return (
      <>
        <PageHeader title="Loading…" />
        <PageBody>
          <LoadingPanel />
        </PageBody>
      </>
    );
  }

  if (strategyQuery.error || !strategyQuery.data) {
    return (
      <>
        <PageHeader title="Strategy not found" />
        <PageBody>
          <ErrorBanner message={strategyQuery.error instanceof ApiError ? strategyQuery.error.message : "This strategy could not be loaded."} />
        </PageBody>
      </>
    );
  }

  const strategy = strategyQuery.data;
  const def = strategy.definition;

  return (
    <>
      <PageHeader
        title={strategy.name}
        breadcrumb={<Link href="/" className="hover:text-[var(--text-muted)]">strategies</Link>}
        action={
          <>
            <LinkButton href={`/strategies/${id}/edit`}>Edit</LinkButton>
            <Button
              variant="danger"
              onClick={() => {
                if (confirm(`Delete "${strategy.name}"? This cannot be undone.`)) deleteMutation.mutate();
              }}
              disabled={deleteMutation.isPending}
            >
              Delete
            </Button>
          </>
        }
      />
      <PageBody className="space-y-6">
        {def.description && <p className="text-sm text-[var(--text-muted)] -mt-2">{def.description}</p>}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Panel className="lg:col-span-2">
            <PanelHeader title="Definition" subtitle={def.timeframe ? `default timeframe: ${def.timeframe}` : undefined} />
            <div className="space-y-4 text-sm">
              <div>
                <div className="text-xs uppercase tracking-wide text-[var(--text-faint)] mb-2">Indicators</div>
                {def.indicators.length === 0 ? (
                  <p className="text-[var(--text-muted)]">None -- conditions reference raw OHLCV.</p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {def.indicators.map((ind) => (
                      <span key={ind.alias} className="font-mono text-xs bg-[var(--panel-raised)] border border-[var(--border)] rounded-[var(--radius-sm)] px-2 py-1">
                        {ind.alias} <span className="text-[var(--text-faint)]">({ind.name}</span>
                        {Object.entries(ind.params).map(([k, v]) => (
                          <span key={k} className="text-[var(--text-faint)]">
                            {" "}
                            {k}={isParamRange(v) ? `${v.min}–${v.max}` : v}
                          </span>
                        ))}
                        <span className="text-[var(--text-faint)]">)</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-[var(--text-faint)] mb-1">Entry</div>
                <p className="font-mono text-xs text-[var(--accent-strong)]">{describeCondition(def.entry_conditions)}</p>
              </div>
              <div>
                <div className="text-xs uppercase tracking-wide text-[var(--text-faint)] mb-1">Exit</div>
                <p className="font-mono text-xs text-[var(--text)]">
                  {def.exit_conditions ? describeCondition(def.exit_conditions) : "none (risk-only exit)"}
                </p>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Risk management" />
            <dl className="text-sm space-y-2 font-mono">
              <div className="flex justify-between">
                <dt className="text-[var(--text-muted)] font-sans">Stop-loss</dt>
                <dd>{formatPct(def.risk_management.stop_loss_pct)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-[var(--text-muted)] font-sans">Take-profit</dt>
                <dd>{formatPct(def.risk_management.take_profit_pct)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-[var(--text-muted)] font-sans">Trailing stop</dt>
                <dd>{def.risk_management.trailing_stop_pct ? formatPct(def.risk_management.trailing_stop_pct) : "off"}</dd>
              </div>
            </dl>
          </Panel>
        </div>

        <Panel>
          <PanelHeader
            title="Backtests"
            action={
              <Button variant="primary" onClick={() => setOpenForm(openForm === "backtest" ? null : "backtest")}>
                {openForm === "backtest" ? "Close" : "+ Run backtest"}
              </Button>
            }
          />
          {openForm === "backtest" && <StartBacktestForm strategyId={id} onDone={() => setOpenForm(null)} />}

          {backtestsQuery.isLoading && <LoadingPanel />}
          {backtestsQuery.data && backtestsQuery.data.length === 0 && (
            <EmptyState title="No backtests yet" body="Run one to see equity curve, metrics, and trades." />
          )}
          {backtestsQuery.data && backtestsQuery.data.length > 0 && (
            <div className="overflow-x-auto -mx-5 mt-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-faint)] border-y border-[var(--border)]">
                    <th className="px-5 py-2 font-medium">Status</th>
                    <th className="px-5 py-2 font-medium text-right">Sharpe</th>
                    <th className="px-5 py-2 font-medium text-right">Return</th>
                    <th className="px-5 py-2 font-medium text-right">Trades</th>
                    <th className="px-5 py-2 font-medium text-right">Started</th>
                  </tr>
                </thead>
                <tbody>
                  {backtestsQuery.data.map((b) => (
                    <tr key={b.job_id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel-raised)]">
                      <td className="px-5 py-2.5">
                        <Link href={`/backtests/${b.job_id}`} className="inline-flex items-center gap-2">
                          <StatusPill status={b.status} />
                        </Link>
                      </td>
                      <td className="px-5 py-2.5 text-right font-mono">{formatNumber(b.metrics?.sharpe_ratio)}</td>
                      <td className="px-5 py-2.5 text-right font-mono">
                        {b.metrics ? (
                          <span className={b.metrics.total_return_pct >= 0 ? "text-[var(--good)]" : "text-[var(--critical)]"}>
                            {formatPct(b.metrics.total_return_pct)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-5 py-2.5 text-right font-mono">{b.metrics?.num_trades ?? "—"}</td>
                      <td className="px-5 py-2.5 text-right text-xs text-[var(--text-muted)]">{formatDateTime(b.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel>
          <PanelHeader
            title="Optimizations"
            action={
              <Button variant="primary" onClick={() => setOpenForm(openForm === "optimization" ? null : "optimization")}>
                {openForm === "optimization" ? "Close" : "+ Run optimization"}
              </Button>
            }
          />
          {openForm === "optimization" && <StartOptimizationForm strategyId={id} onDone={() => setOpenForm(null)} />}

          {optimizationsQuery.isLoading && <LoadingPanel />}
          {optimizationsQuery.data && optimizationsQuery.data.length === 0 && (
            <EmptyState title="No optimizations yet" body="Run a walk-forward parameter search to see in-sample vs out-of-sample results." />
          )}
          {optimizationsQuery.data && optimizationsQuery.data.length > 0 && (
            <div className="overflow-x-auto -mx-5 mt-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-faint)] border-y border-[var(--border)]">
                    <th className="px-5 py-2 font-medium">Status</th>
                    <th className="px-5 py-2 font-medium text-right">Mean in-sample</th>
                    <th className="px-5 py-2 font-medium text-right">Mean out-of-sample</th>
                    <th className="px-5 py-2 font-medium text-right">Started</th>
                  </tr>
                </thead>
                <tbody>
                  {optimizationsQuery.data.map((o) => (
                    <tr key={o.job_id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel-raised)]">
                      <td className="px-5 py-2.5">
                        <Link href={`/optimizations/${o.job_id}`} className="inline-flex items-center gap-2">
                          <StatusPill status={o.status} />
                        </Link>
                      </td>
                      <td className="px-5 py-2.5 text-right font-mono">{formatNumber(o.mean_in_sample_score)}</td>
                      <td className="px-5 py-2.5 text-right font-mono">{formatNumber(o.mean_out_of_sample_score)}</td>
                      <td className="px-5 py-2.5 text-right text-xs text-[var(--text-muted)]">{formatDateTime(o.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </PageBody>
    </>
  );
}
