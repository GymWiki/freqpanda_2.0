"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueries, useQuery } from "@tanstack/react-query";
import { PageHeader, PageBody } from "@/components/layout/PageHeader";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { Button } from "@/components/ui/Button";
import { TextInput } from "@/components/ui/Field";
import { EmptyState, ErrorBanner, LoadingPanel } from "@/components/ui/EmptyState";
import { StatusPill } from "@/components/jobs/StatusPill";
import { CompareEquityChart } from "@/components/charts/CompareEquityChart";
import { seriesColor } from "@/lib/series-colors";
import { api, ApiError } from "@/lib/api-client";
import { formatNumber, formatPct } from "@/lib/format";
import type { BacktestDetailResponse } from "@/lib/types";

function useJobIds() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const jobIds = useMemo(() => (searchParams.get("jobs") ?? "").split(",").filter(Boolean), [searchParams]);

  function setJobIds(ids: string[]) {
    const unique = Array.from(new Set(ids));
    router.replace(unique.length > 0 ? `/compare?jobs=${unique.join(",")}` : "/compare");
  }

  return { jobIds, setJobIds };
}

function ComparePageInner() {
  const { jobIds, setJobIds } = useJobIds();
  const [manualId, setManualId] = useState("");

  const detailQueries = useQueries({
    queries: jobIds.map((id) => ({ queryKey: ["backtest", id], queryFn: () => api.getBacktest(id) })),
  });

  const completedIds = jobIds.filter((_, i) => detailQueries[i]?.data?.status === "completed");

  const compareQuery = useQuery({
    queryKey: ["compare", completedIds],
    queryFn: () => api.compareBacktests(completedIds),
    enabled: completedIds.length > 0,
  });

  function addJob() {
    if (manualId.trim()) {
      setJobIds([...jobIds, manualId.trim()]);
      setManualId("");
    }
  }

  function removeJob(id: string) {
    setJobIds(jobIds.filter((j) => j !== id));
  }

  const strategyNameByJobId = new Map((compareQuery.data ?? []).map((row) => [row.job_id, row.strategy_name]));

  const seriesForChart = jobIds
    .map((id, i) => ({ id, detail: detailQueries[i]?.data }))
    .filter((x): x is { id: string; detail: BacktestDetailResponse } => x.detail?.status === "completed" && !!x.detail.equity_curve?.length)
    .map((x) => ({ jobId: x.id, label: strategyNameByJobId.get(x.id) ?? x.detail.strategy_id, points: x.detail.equity_curve! }));

  return (
    <>
      <PageHeader title="Compare" subtitle={jobIds.length > 0 ? `${jobIds.length} backtests` : undefined} />
      <PageBody className="space-y-6">
        <Panel>
          <PanelHeader title="Backtests to compare" subtitle="Paste a job id from a backtest detail page, or use its 'Add to compare' button." />
          <div className="flex gap-2 mb-4">
            <TextInput
              value={manualId}
              onChange={(e) => setManualId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addJob()}
              placeholder="job_..."
              className="font-mono max-w-xs"
            />
            <Button onClick={addJob}>Add</Button>
          </div>

          {jobIds.length === 0 ? (
            <EmptyState title="Nothing to compare yet" body="Add at least two backtest job ids to see them side by side." />
          ) : (
            <div className="flex flex-wrap gap-2">
              {jobIds.map((id, i) => {
                const detail = detailQueries[i]?.data;
                return (
                  <span key={id} className="inline-flex items-center gap-2 bg-[var(--panel-raised)] border border-[var(--border)] rounded-[var(--radius-sm)] pl-2.5 pr-1.5 py-1">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: seriesColor(i) }} aria-hidden />
                    <span className="font-mono text-xs">{id.slice(0, 14)}…</span>
                    {detail && <StatusPill status={detail.status} />}
                    <button onClick={() => removeJob(id)} className="text-[var(--text-faint)] hover:text-[var(--critical)] px-1" aria-label="Remove">
                      ✕
                    </button>
                  </span>
                );
              })}
            </div>
          )}
        </Panel>

        {seriesForChart.length > 0 && (
          <Panel>
            <PanelHeader title="Equity curves" subtitle="Indexed to 100 at each backtest's own start." />
            <CompareEquityChart series={seriesForChart} />
          </Panel>
        )}

        {completedIds.length > 0 && (
          <Panel padded={false}>
            <div className="p-5 pb-0">
              <PanelHeader title="Metrics" />
            </div>
            {compareQuery.isLoading && <div className="px-5 pb-5"><LoadingPanel /></div>}
            {compareQuery.error && (
              <div className="px-5 pb-5">
                <ErrorBanner message={compareQuery.error instanceof ApiError ? compareQuery.error.message : "Could not load comparison."} />
              </div>
            )}
            {compareQuery.data && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-faint)] border-y border-[var(--border)]">
                      <th className="px-5 py-2 font-medium">Strategy</th>
                      <th className="px-5 py-2 font-medium text-right">Return</th>
                      <th className="px-5 py-2 font-medium text-right">Sharpe</th>
                      <th className="px-5 py-2 font-medium text-right">Sortino</th>
                      <th className="px-5 py-2 font-medium text-right">Max DD</th>
                      <th className="px-5 py-2 font-medium text-right">Win rate</th>
                      <th className="px-5 py-2 font-medium text-right">Trades</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareQuery.data.map((row) => (
                      <tr key={row.job_id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel-raised)]">
                        <td className="px-5 py-2.5">
                          <span className="inline-flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: seriesColor(jobIds.indexOf(row.job_id)) }} aria-hidden />
                            {row.strategy_name}
                          </span>
                        </td>
                        <td className={`px-5 py-2.5 text-right font-mono ${row.metrics.total_return_pct >= 0 ? "text-[var(--good)]" : "text-[var(--critical)]"}`}>
                          {formatPct(row.metrics.total_return_pct)}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono">{formatNumber(row.metrics.sharpe_ratio)}</td>
                        <td className="px-5 py-2.5 text-right font-mono">{formatNumber(row.metrics.sortino_ratio)}</td>
                        <td className="px-5 py-2.5 text-right font-mono text-[var(--critical)]">{formatPct(row.metrics.max_drawdown_pct)}</td>
                        <td className="px-5 py-2.5 text-right font-mono">{formatPct(row.metrics.win_rate)}</td>
                        <td className="px-5 py-2.5 text-right font-mono">{row.metrics.num_trades}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        )}
      </PageBody>
    </>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<LoadingPanel />}>
      <ComparePageInner />
    </Suspense>
  );
}
