"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { OptimizationWindow } from "@/lib/types";

/** In-sample vs out-of-sample score per walk-forward window -- two named
 * series (categorical, slots 1/2), always legended per the dataviz skill's
 * >=2-series rule. Window number is which walk-forward window, not a
 * magnitude, so it's a plain category on the x-axis, not an ordinal ramp.
 */
export function WindowScoreChart({ windows }: { windows: OptimizationWindow[] }) {
  const data = windows.map((w, i) => ({
    window: `W${i + 1}`,
    in_sample: w.in_sample_score,
    out_of_sample: w.out_of_sample_score,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="var(--border)" vertical={false} />
        <XAxis dataKey="window" stroke="var(--text-faint)" tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
        <YAxis stroke="var(--text-faint)" tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={false} width={48} />
        <Tooltip
          contentStyle={{ background: "var(--panel-raised)", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-sm)", fontSize: 12 }}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="in_sample" name="in-sample" fill="var(--series-1)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="out_of_sample" name="out-of-sample" fill="var(--series-2)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}
