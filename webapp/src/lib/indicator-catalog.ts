/**
 * Mirrors `freqpanda_strategy.indicators.INDICATOR_REGISTRY` (phase 1) --
 * which indicators exist, what parameters each takes, and what output
 * column(s) they produce. This can't be fetched from the API at runtime
 * (the registry is Python-side interpreter detail, not exposed over HTTP),
 * so it's hand-kept in sync with that module. Adding an indicator there
 * means adding one entry here too.
 */

export interface IndicatorParamSpec {
  name: string;
  label: string;
  defaultValue: number;
  min: number;
  max: number;
  step: number;
}

export interface IndicatorSpec {
  name: string;
  label: string;
  params: IndicatorParamSpec[];
  /** Output column name(s) available to reference in conditions, given an alias. */
  outputs: (alias: string) => { value: string; label: string }[];
}

export const INDICATOR_CATALOG: IndicatorSpec[] = [
  {
    name: "rsi",
    label: "RSI (Relative Strength Index)",
    params: [{ name: "period", label: "Period", defaultValue: 14, min: 2, max: 100, step: 1 }],
    outputs: (alias) => [{ value: alias, label: alias }],
  },
  {
    name: "ema",
    label: "EMA (Exponential Moving Average)",
    params: [{ name: "period", label: "Period", defaultValue: 20, min: 2, max: 300, step: 1 }],
    outputs: (alias) => [{ value: alias, label: alias }],
  },
  {
    name: "sma",
    label: "SMA (Simple Moving Average)",
    params: [{ name: "period", label: "Period", defaultValue: 20, min: 2, max: 300, step: 1 }],
    outputs: (alias) => [{ value: alias, label: alias }],
  },
  {
    name: "macd",
    label: "MACD",
    params: [
      { name: "fast_period", label: "Fast period", defaultValue: 12, min: 2, max: 100, step: 1 },
      { name: "slow_period", label: "Slow period", defaultValue: 26, min: 2, max: 300, step: 1 },
      { name: "signal_period", label: "Signal period", defaultValue: 9, min: 2, max: 100, step: 1 },
    ],
    outputs: (alias) => [
      { value: `${alias}_macd`, label: `${alias}_macd` },
      { value: `${alias}_signal`, label: `${alias}_signal` },
      { value: `${alias}_hist`, label: `${alias}_hist` },
    ],
  },
  {
    name: "bbands",
    label: "Bollinger Bands",
    params: [
      { name: "period", label: "Period", defaultValue: 20, min: 2, max: 300, step: 1 },
      { name: "std_dev", label: "Std. deviations", defaultValue: 2, min: 0.5, max: 5, step: 0.1 },
    ],
    outputs: (alias) => [
      { value: `${alias}_upper`, label: `${alias}_upper` },
      { value: `${alias}_middle`, label: `${alias}_middle` },
      { value: `${alias}_lower`, label: `${alias}_lower` },
    ],
  },
];

export const OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"];

export const COMPARISON_OPS: { value: string; label: string }[] = [
  { value: "gt", label: "> (greater than)" },
  { value: "gte", label: ">= (greater or equal)" },
  { value: "lt", label: "< (less than)" },
  { value: "lte", label: "<= (less or equal)" },
  { value: "eq", label: "== (equals)" },
  { value: "ne", label: "!= (not equal)" },
  { value: "crosses_above", label: "crosses above" },
  { value: "crosses_below", label: "crosses below" },
];

export function indicatorSpecByName(name: string): IndicatorSpec | undefined {
  return INDICATOR_CATALOG.find((i) => i.name === name);
}
