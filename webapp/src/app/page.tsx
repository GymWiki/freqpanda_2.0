"use client";

import Link from "next/link";
import { useQueries, useQuery } from "@tanstack/react-query";
import { PageHeader, PageBody } from "@/components/layout/PageHeader";
import { LinkButton } from "@/components/ui/Button";
import { EmptyState, ErrorBanner, LoadingPanel } from "@/components/ui/EmptyState";
import { Panel } from "@/components/ui/Panel";
import { api, ApiError } from "@/lib/api-client";
import { formatDateTime, formatNumber, formatPct } from "@/lib/format";
import type { BacktestSummary, ConditionNode } from "@/lib/types";

function bestResult(backtests: BacktestSummary[]): BacktestSummary | null {
  const completed = backtests.filter((b) => b.status === "completed" && b.metrics);
  if (completed.length === 0) return null;
  return completed.reduce((best, b) => ((b.metrics!.sharpe_ratio ?? -Infinity) > (best.metrics!.sharpe_ratio ?? -Infinity) ? b : best));
}

export default function DashboardPage() {
  const strategiesQuery = useQuery({ queryKey: ["strategies"], queryFn: api.listStrategies });
  const strategies = strategiesQuery.data ?? [];

  const backtestQueries = useQueries({
    queries: strategies.map((s) => ({
      queryKey: ["backtests", s.id],
      queryFn: () => api.listBacktests(s.id),
      enabled: strategies.length > 0,
    })),
  });

  return (
    <>
      <PageHeader
        title="Strategies"
        subtitle={strategies.length > 0 ? `${strategies.length} saved` : undefined}
        action={<LinkButton href="/strategies/new" variant="primary">+ New strategy</LinkButton>}
      />
      <PageBody>
        {strategiesQuery.isLoading && <LoadingPanel />}
        {strategiesQuery.error && (
          <ErrorBanner
            message={
              strategiesQuery.error instanceof ApiError
                ? strategiesQuery.error.message
                : "Could not reach the API. Check NEXT server env vars (see README)."
            }
          />
        )}
        {strategiesQuery.data && strategies.length === 0 && (
          <EmptyState
            title="No strategies yet"
            body="Build your first strategy definition -- indicators, entry/exit conditions, and risk limits."
            action={<LinkButton href="/strategies/new" variant="primary">+ New strategy</LinkButton>}
          />
        )}

        {strategies.length > 0 && (
          <Panel padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-faint)] border-b border-[var(--border)]">
                    <th className="px-5 py-3 font-medium">Name</th>
                    <th className="px-5 py-3 font-medium">Entry</th>
                    <th className="px-5 py-3 font-medium text-right">Backtests</th>
                    <th className="px-5 py-3 font-medium text-right">Best Sharpe</th>
                    <th className="px-5 py-3 font-medium text-right">Best return</th>
                    <th className="px-5 py-3 font-medium text-right">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {strategies.map((s, i) => {
                    const backtests = backtestQueries[i]?.data ?? [];
                    const best = bestResult(backtests);
                    return (
                      <tr key={s.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--panel-raised)] transition-colors">
                        <td className="px-5 py-3">
                          <Link href={`/strategies/${s.id}`} className="font-medium text-[var(--text)] hover:text-[var(--accent)]">
                            {s.name}
                          </Link>
                          {s.definition.description && <div className="text-xs text-[var(--text-muted)] mt-0.5">{s.definition.description}</div>}
                        </td>
                        <td className="px-5 py-3 font-mono text-xs text-[var(--text-muted)]">
                          {describeEntry(s.definition.entry_conditions)}
                        </td>
                        <td className="px-5 py-3 text-right font-mono">{backtests.length}</td>
                        <td className="px-5 py-3 text-right font-mono">
                          {best ? formatNumber(best.metrics!.sharpe_ratio) : "—"}
                        </td>
                        <td className="px-5 py-3 text-right font-mono">
                          {best ? (
                            <span className={best.metrics!.total_return_pct >= 0 ? "text-[var(--good)]" : "text-[var(--critical)]"}>
                              {formatPct(best.metrics!.total_return_pct)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-5 py-3 text-right text-xs text-[var(--text-muted)]">{formatDateTime(s.updated_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </PageBody>
    </>
  );
}

function describeEntry(node: ConditionNode): string {
  if (node.type === "comparison") return "1 condition";
  return `${node.conditions.length} conditions (${node.op})`;
}
