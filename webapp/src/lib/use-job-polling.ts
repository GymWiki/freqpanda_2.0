import { useQuery } from "@tanstack/react-query";
import { api } from "./api-client";
import type { BacktestDetailResponse, OptimizationDetailResponse } from "./types";

const POLL_INTERVAL_MS = 2000;

function isDone(status: string) {
  return status === "completed" || status === "failed";
}

/** Polls a backtest job until it reaches a terminal status, then stops. */
export function useBacktestPolling(jobId: string) {
  return useQuery<BacktestDetailResponse>({
    queryKey: ["backtest", jobId],
    queryFn: () => api.getBacktest(jobId),
    refetchInterval: (query) => (query.state.data && isDone(query.state.data.status) ? false : POLL_INTERVAL_MS),
  });
}

/** Same as above, for optimization jobs (which typically run much longer). */
export function useOptimizationPolling(jobId: string) {
  return useQuery<OptimizationDetailResponse>({
    queryKey: ["optimization", jobId],
    queryFn: () => api.getOptimization(jobId),
    refetchInterval: (query) => (query.state.data && isDone(query.state.data.status) ? false : POLL_INTERVAL_MS),
  });
}
