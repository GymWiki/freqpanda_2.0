"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquityPoint } from "@/lib/types";
import { seriesColor } from "@/lib/series-colors";

export interface CompareSeries {
  jobId: string;
  label: string;
  points: EquityPoint[];
}

/**
 * Overlays multiple equity curves that may span different date ranges or
 * timeframes. Per the dataviz skill's guidance for measures of different
 * scale/base, each series is indexed to 100 at its own start and plotted
 * against hours-elapsed-since-that-series'-start, rather than absolute
 * price/date -- otherwise a $10k and a $50k backtest, or two different
 * date windows, would not be visually comparable at all.
 */
export function CompareEquityChart({ series }: { series: CompareSeries[] }) {
  const indexed = series.map((s) => {
    const start = s.points[0]?.equity ?? 1;
    const t0 = s.points[0] ? new Date(s.points[0].timestamp).getTime() : 0;
    return {
      ...s,
      data: s.points.map((p) => ({
        hours: (new Date(p.timestamp).getTime() - t0) / 3_600_000,
        indexed: (p.equity / start) * 100,
      })),
    };
  });

  return (
    <ResponsiveContainer width="100%" height={360}>
      <LineChart margin={{ top: 12, right: 24, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis
          dataKey="hours"
          type="number"
          domain={["dataMin", "dataMax"]}
          tickFormatter={(h) => `${Math.round(h / 24)}d`}
          stroke="var(--text-faint)"
          tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
          tickLine={false}
          axisLine={{ stroke: "var(--border)" }}
          label={{ value: "days elapsed", position: "insideBottom", offset: -2, fill: "var(--text-faint)", fontSize: 10 }}
        />
        <YAxis
          type="number"
          domain={["auto", "auto"]}
          tickFormatter={(v) => `${v}`}
          stroke="var(--text-faint)"
          tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
          tickLine={false}
          axisLine={false}
          width={48}
          label={{ value: "indexed (100 = start)", angle: -90, position: "insideLeft", fill: "var(--text-faint)", fontSize: 10 }}
        />
        <Tooltip
          contentStyle={{
            background: "var(--panel-raised)",
            border: "1px solid var(--border-strong)",
            borderRadius: "var(--radius-sm)",
            fontSize: 12,
          }}
          labelFormatter={(h) => `day ${(Number(h) / 24).toFixed(1)}`}
          formatter={(value) => [Number(value).toFixed(1), "indexed"]}
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
        {indexed.map((s, i) => (
          <Line
            key={s.jobId}
            data={s.data}
            dataKey="indexed"
            xAxisId={0}
            name={s.label}
            stroke={seriesColor(i)}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
