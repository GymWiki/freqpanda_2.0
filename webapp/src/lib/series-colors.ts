/**
 * Fixed-order categorical palette (validated against the app's dark panel
 * surface with the dataviz skill's validator -- see webapp/README.md).
 * Never cycle or reassign by rank: index N always gets slot N, for every
 * chart in the compare view, so a strategy's color stays constant across
 * the equity-curve chart, the bar chart, and the legend.
 */
export const SERIES_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
];

export function seriesColor(index: number): string {
  return SERIES_COLORS[index % SERIES_COLORS.length];
}
