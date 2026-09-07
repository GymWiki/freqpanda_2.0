/**
 * Mirrors the phase-5 API's OpenAPI schema exactly (pulled from a live
 * /openapi.json during development). No client-side codegen pipeline for
 * v1 -- the surface is small and stable enough that hand-maintained types
 * checked against the real backend are less overhead than wiring up a
 * generator, but if the API grows, `openapi-typescript` against
 * `${API_URL}/openapi.json` is the natural next step and these types are
 * shaped to match what it would produce.
 */

// ---- phase-1 strategy schema ----

export type Number_ = number;

export interface ParamRange {
  default: Number_;
  min: Number_;
  max: Number_;
  step?: Number_ | null;
}

export type ParamValue = Number_ | ParamRange;

export function isParamRange(value: ParamValue): value is ParamRange {
  return typeof value === "object" && value !== null && "default" in value;
}

export interface IndicatorConfig {
  name: string;
  alias: string;
  params: Record<string, ParamValue>;
}

export type ComparisonOp = "gt" | "gte" | "lt" | "lte" | "eq" | "ne" | "crosses_above" | "crosses_below";
export type LogicalOp = "and" | "or" | "not";
export type Operand = Number_ | string;

export interface Comparison {
  type: "comparison";
  left: Operand;
  op: ComparisonOp;
  right: Operand;
}

export interface Logical {
  type: "logical";
  op: LogicalOp;
  conditions: ConditionNode[];
}

export type ConditionNode = Comparison | Logical;

export interface RiskManagement {
  stop_loss_pct: Number_;
  take_profit_pct: Number_;
  trailing_stop_pct?: Number_ | null;
}

export interface StrategyDefinition {
  name: string;
  description?: string | null;
  timeframe?: string | null;
  indicators: IndicatorConfig[];
  entry_conditions: ConditionNode;
  exit_conditions?: ConditionNode | null;
  risk_management: RiskManagement;
}

// ---- phase-5 API: strategies ----

export interface StrategyResponse {
  id: string;
  name: string;
  definition: StrategyDefinition;
  created_at: string;
  updated_at: string;
}

// ---- phase-5 API: jobs ----

export type JobType = "backtest" | "optimization";
export type JobStatus = "pending" | "running" | "completed" | "failed";

export interface JobResponse {
  id: string;
  job_type: JobType;
  status: JobStatus;
  strategy_id: string;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface BacktestJobRequest {
  exchange?: string;
  symbol: string;
  timeframe: string;
  start?: string | null;
  end?: string | null;
  initial_capital?: number;
  fee_pct?: number;
  slippage_pct?: number;
}

export interface OptimizationJobRequest {
  exchange?: string;
  symbol: string;
  timeframe: string;
  start?: string | null;
  end?: string | null;
  train_period_days: number;
  test_period_days: number;
  metric?: string;
  n_trials?: number;
  timeout_seconds?: number | null;
  initial_capital?: number;
  fee_pct?: number;
  slippage_pct?: number;
}

// Flattened BacktestResult.metrics_dict() -- see freqpanda_backtest/result.py
export interface BacktestMetrics {
  strategy_name: string;
  initial_capital: number;
  final_capital: number;
  total_return_pct: number;
  total_return_abs: number;
  sharpe_ratio: number | null;
  sortino_ratio: number | null;
  max_drawdown_pct: number;
  max_drawdown_duration_seconds: number;
  num_trades: number;
  win_rate: number | null;
  avg_win_pct: number;
  avg_loss_pct: number;
  profit_factor: number | null;
  fee_pct: number;
  slippage_pct: number;
}

export interface TradeRecord {
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  entry_fill_price: number;
  exit_fill_price: number;
  exit_reason: "stop_loss" | "take_profit" | "trailing_stop" | "exit_signal";
  quantity: number;
  net_pnl_pct: number;
  net_pnl_abs: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
}

export interface BacktestSummary {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  metrics: BacktestMetrics | null;
}

export interface BacktestDetailResponse extends JobResponse {
  metrics: BacktestMetrics | null;
  trades: TradeRecord[] | null;
  equity_curve: EquityPoint[] | null;
}

export interface OptimizationSummary {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  mean_in_sample_score: number | null;
  mean_out_of_sample_score: number | null;
}

export interface OptimizationWindow {
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  best_params: Record<string, number>;
  in_sample_score: number;
  out_of_sample_score: number;
  in_sample_metrics: BacktestMetrics;
  out_of_sample_metrics: BacktestMetrics;
}

export interface OptimizationDetailResponse extends JobResponse {
  metric: string | null;
  windows: OptimizationWindow[] | null;
  mean_in_sample_score: number | null;
  mean_out_of_sample_score: number | null;
  final_params: Record<string, number> | null;
  final_definition: StrategyDefinition | null;
}

export interface CompareRow {
  job_id: string;
  strategy_id: string;
  strategy_name: string;
  metrics: BacktestMetrics;
}

export interface ApiErrorBody {
  detail: string | { msg: string; loc: (string | number)[] }[];
}
