"use client";

import { use } from "react";
import Link from "next/link";
import { useBacktestPolling } from "@/lib/use-job-polling";
import { PageHeader, PageBody } from "@/components/layout/PageHeader";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { StatusPill } from "@/components/jobs/StatusPill";
import { MetricTile } from "@/components/ui/MetricTile";
import { EquityCurveChart } from "@/components/charts/EquityCurveChart";
import { ErrorBanner, LoadingPanel } from "@/components/ui/EmptyState";
import { LinkButton } from "@/components/ui/Button";
import { ApiError } from "@/lib/api-client";
import { formatCurrency, formatDateTime, formatDuration, formatNumber, formatPct } from "@/lib/format";

export default function BacktestDetailPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const { data: job, isLoading, error } = useBacktestPolling(jobId);

  return (
    <>
      <PageHeader
        title="Backtest"
        breadcrumb={
          job ? (
            <Link href={`/strategies/${job.strategy_id}`} className="hover:text-[var(--text-muted)]">
              {job.strategy_id}
            </Link>
          ) : (
            "backtests"
          )
        }
        subtitle={<span className="font-mono text-xs">{jobId}</span>}
        action={job && <StatusPill status={job.status} />}
      />
      <PageBody className="space-y-6">
        {isLoading && <LoadingPanel />}
        {error && <ErrorBanner message={error instanceof ApiError ? error.message : "Could not load this backtest."} />}

        {job && (job.status === "pending" || job.status === "running") && (
          <Panel>
            <div className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
              <StatusPill status={job.status} />
              <span>Waiting for the worker to finish -- this page refreshes automatically every 2 seconds.</span>
            </div>
          </Panel>
        )}

        {job && job.status === "failed" && (
          <ErrorBanner message={job.error ?? "The backtest job failed for an unknown reason."} />
        )}

        {job && job.status === "completed" && job.metrics && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricTile
                label="Total return"
                value={formatPct(job.metrics.total_return_pct)}
                tone={job.metrics.total_return_pct >= 0 ? "good" : "critical"}
                sublabel={formatCurrency(job.metrics.total_return_abs)}
              />
              <MetricTile label="Sharpe ratio" value={formatNumber(job.metrics.sharpe_ratio)} />
              <MetricTile label="Sortino ratio" value={formatNumber(job.metrics.sortino_ratio)} />
              <MetricTile
                label="Max drawdown"
                value={formatPct(job.metrics.max_drawdown_pct)}
                tone="critical"
                sublabel={formatDuration(job.metrics.max_drawdown_duration_seconds)}
              />
              <MetricTile label="Win rate" value={formatPct(job.metrics.win_rate)} />
              <MetricTile label="Trades" value={String(job.metrics.num_trades)} />
              <MetricTile label="Profit factor" value={formatNumber(job.metrics.profit_factor)} />
              <MetricTile
                label="Final capital"
                value={formatCurrency(job.metrics.final_capital, 0)}
                sublabel={`from ${formatCurrency(job.metrics.initial_capital, 0)}`}
              />
            </div>

            <Panel>
              <PanelHeader
                title="Equity curve"
                action={<LinkButton href={`/compare?jobs=${jobId}`}>Add to compare</LinkButton>}
              />
              {job.equity_curve && job.equity_curve.length > 0 ? (
                <EquityCurveChart points={job.equity_curve} initialCapital={job.metrics.initial_capital} />
              ) : (
                <p className="text-sm text-[var(--text-muted)]">No equity data.</p>
              )}
            </Panel>

            <Panel padded={false}>
              <div className="p-5 pb-0">
                <PanelHeader title="Trades" subtitle={`${job.trades?.length ?? 0} total`} />
              </div>
              {job.trades && job.trades.length > 0 ? (
                <div className="overflow-auto max-h-[560px]">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-[var(--panel)]">
                      <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-faint)] border-y border-[var(--border)]">
                        <th className="px-5 py-2 font-medium">Entry</th>
                        <th className="px-5 py-2 font-medium">Exit</th>
                        <th className="px-5 py-2 font-medium text-right">Entry price</th>
                        <th className="px-5 py-2 font-medium text-right">Exit price</th>
                        <th className="px-5 py-2 font-medium">Reason</th>
                        <th className="px-5 py-2 font-medium text-right">Net P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {job.trades.map((t, i) => (
                        <tr key={i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel-raised)]">
                          <td className="px-5 py-2 text-xs text-[var(--text-muted)]">{formatDateTime(t.entry_time)}</td>
                          <td className="px-5 py-2 text-xs text-[var(--text-muted)]">{formatDateTime(t.exit_time)}</td>
                          <td className="px-5 py-2 text-right font-mono">{formatCurrency(t.entry_price)}</td>
                          <td className="px-5 py-2 text-right font-mono">{formatCurrency(t.exit_price)}</td>
                          <td className="px-5 py-2 text-xs font-mono text-[var(--text-muted)]">{t.exit_reason}</td>
                          <td className={`px-5 py-2 text-right font-mono ${t.net_pnl_abs >= 0 ? "text-[var(--good)]" : "text-[var(--critical)]"}`}>
                            {formatPct(t.net_pnl_pct)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-[var(--text-muted)] px-5 pb-5">No trades were generated in this window.</p>
              )}
            </Panel>
          </>
        )}
      </PageBody>
    </>
  );
}
