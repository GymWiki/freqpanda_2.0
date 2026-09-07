"use client";

import { use } from "react";
import Link from "next/link";
import { useOptimizationPolling } from "@/lib/use-job-polling";
import { PageHeader, PageBody } from "@/components/layout/PageHeader";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import { StatusPill } from "@/components/jobs/StatusPill";
import { MetricTile } from "@/components/ui/MetricTile";
import { WindowScoreChart } from "@/components/charts/WindowScoreChart";
import { ErrorBanner, LoadingPanel } from "@/components/ui/EmptyState";
import { ApiError } from "@/lib/api-client";
import { formatDate, formatNumber } from "@/lib/format";

export default function OptimizationDetailPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = use(params);
  const { data: job, isLoading, error } = useOptimizationPolling(jobId);

  return (
    <>
      <PageHeader
        title="Optimization"
        breadcrumb={
          job ? (
            <Link href={`/strategies/${job.strategy_id}`} className="hover:text-[var(--text-muted)]">
              {job.strategy_id}
            </Link>
          ) : (
            "optimizations"
          )
        }
        subtitle={<span className="font-mono text-xs">{jobId}</span>}
        action={job && <StatusPill status={job.status} />}
      />
      <PageBody className="space-y-6">
        {isLoading && <LoadingPanel />}
        {error && <ErrorBanner message={error instanceof ApiError ? error.message : "Could not load this optimization."} />}

        {job && (job.status === "pending" || job.status === "running") && (
          <Panel>
            <div className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
              <StatusPill status={job.status} />
              <span>Walk-forward optimization can take a while (one Optuna study per window). Refreshing every 2 seconds.</span>
            </div>
          </Panel>
        )}

        {job && job.status === "failed" && <ErrorBanner message={job.error ?? "The optimization job failed for an unknown reason."} />}

        {job && job.status === "completed" && job.windows && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <MetricTile label="Metric optimized" value={job.metric ?? "—"} />
              <MetricTile label="Mean in-sample" value={formatNumber(job.mean_in_sample_score)} />
              <MetricTile label="Mean out-of-sample" value={formatNumber(job.mean_out_of_sample_score)} />
              <MetricTile
                label="Degradation"
                value={
                  job.mean_in_sample_score != null && job.mean_out_of_sample_score != null
                    ? formatNumber(job.mean_in_sample_score - job.mean_out_of_sample_score)
                    : "—"
                }
                sublabel="in-sample minus out-of-sample"
                tone={
                  job.mean_in_sample_score != null && job.mean_out_of_sample_score != null && job.mean_in_sample_score - job.mean_out_of_sample_score > 0
                    ? "critical"
                    : "good"
                }
              />
            </div>

            <Panel>
              <PanelHeader title="In-sample vs out-of-sample, per window" subtitle="A large, consistent gap signals overfitting." />
              <WindowScoreChart windows={job.windows} />
            </Panel>

            <Panel padded={false}>
              <div className="p-5 pb-0">
                <PanelHeader title="Walk-forward windows" />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-faint)] border-y border-[var(--border)]">
                      <th className="px-5 py-2 font-medium">Train</th>
                      <th className="px-5 py-2 font-medium">Test</th>
                      <th className="px-5 py-2 font-medium">Best params</th>
                      <th className="px-5 py-2 font-medium text-right">In-sample</th>
                      <th className="px-5 py-2 font-medium text-right">Out-of-sample</th>
                    </tr>
                  </thead>
                  <tbody>
                    {job.windows.map((w, i) => (
                      <tr key={i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel-raised)]">
                        <td className="px-5 py-2.5 text-xs text-[var(--text-muted)] font-mono">
                          {formatDate(w.train_start)} – {formatDate(w.train_end)}
                        </td>
                        <td className="px-5 py-2.5 text-xs text-[var(--text-muted)] font-mono">
                          {formatDate(w.test_start)} – {formatDate(w.test_end)}
                        </td>
                        <td className="px-5 py-2.5 text-xs font-mono">
                          {Object.entries(w.best_params)
                            .map(([k, v]) => `${k}=${v}`)
                            .join(", ")}
                        </td>
                        <td className="px-5 py-2.5 text-right font-mono">{formatNumber(w.in_sample_score)}</td>
                        <td className="px-5 py-2.5 text-right font-mono">{formatNumber(w.out_of_sample_score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            {job.final_params && (
              <Panel>
                <PanelHeader title="Recommended parameters" subtitle="Refit on the full dataset after walk-forward validation -- see freqpanda_optimize's README on why this has no held-out score of its own." />
                <div className="flex flex-wrap gap-2">
                  {Object.entries(job.final_params).map(([k, v]) => (
                    <span key={k} className="font-mono text-xs bg-[var(--panel-raised)] border border-[var(--border)] rounded-[var(--radius-sm)] px-2.5 py-1.5">
                      {k} = {v}
                    </span>
                  ))}
                </div>
              </Panel>
            )}
          </>
        )}
      </PageBody>
    </>
  );
}
