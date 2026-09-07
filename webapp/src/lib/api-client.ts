import type {
  BacktestDetailResponse,
  BacktestJobRequest,
  BacktestSummary,
  CompareRow,
  JobResponse,
  OptimizationDetailResponse,
  OptimizationJobRequest,
  OptimizationSummary,
  StrategyDefinition,
  StrategyResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/proxy/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail.map((e: { loc: (string | number)[]; msg: string }) => `${e.loc.join(".")}: ${e.msg}`).join("; ");
      }
    } catch {
      // response wasn't JSON -- keep the generic message
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  // strategies
  listStrategies: () => request<StrategyResponse[]>("strategies"),
  getStrategy: (id: string) => request<StrategyResponse>(`strategies/${id}`),
  createStrategy: (definition: StrategyDefinition) =>
    request<StrategyResponse>("strategies", { method: "POST", body: JSON.stringify(definition) }),
  updateStrategy: (id: string, definition: StrategyDefinition) =>
    request<StrategyResponse>(`strategies/${id}`, { method: "PUT", body: JSON.stringify(definition) }),
  deleteStrategy: (id: string) => request<void>(`strategies/${id}`, { method: "DELETE" }),

  // backtests
  createBacktest: (strategyId: string, body: BacktestJobRequest) =>
    request<JobResponse>(`strategies/${strategyId}/backtests`, { method: "POST", body: JSON.stringify(body) }),
  listBacktests: (strategyId: string) => request<BacktestSummary[]>(`strategies/${strategyId}/backtests`),
  getBacktest: (jobId: string) => request<BacktestDetailResponse>(`backtests/${jobId}`),

  // optimizations
  createOptimization: (strategyId: string, body: OptimizationJobRequest) =>
    request<JobResponse>(`strategies/${strategyId}/optimizations`, { method: "POST", body: JSON.stringify(body) }),
  listOptimizations: (strategyId: string) => request<OptimizationSummary[]>(`strategies/${strategyId}/optimizations`),
  getOptimization: (jobId: string) => request<OptimizationDetailResponse>(`optimizations/${jobId}`),

  // compare
  compareBacktests: (jobIds: string[]) =>
    request<CompareRow[]>("compare", { method: "POST", body: JSON.stringify({ job_ids: jobIds }) }),
};
