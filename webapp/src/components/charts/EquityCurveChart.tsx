"use client";

import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquityPoint } from "@/lib/types";
import { formatCurrency, formatDateTime } from "@/lib/format";

/**
 * A single series needs no legend (the panel title names it) -- see
 * dataviz skill. The amber glow on the line is this app's signature,
 * reused here since the equity curve is the one artifact every backtest
 * view centers on.
 */
export function EquityCurveChart({ points, initialCapital }: { points: EquityPoint[]; initialCapital: number }) {
  const data = points.map((p) => ({ t: new Date(p.timestamp).getTime(), equity: p.equity }));

  return (
    <div className="scanlines rounded-[var(--radius-md)] -mx-2">
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={data} margin={{ top: 12, right: 16, left: 8, bottom: 0 }}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.28} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--border)" strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
            stroke="var(--text-faint)"
            tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={{ stroke: "var(--border)" }}
            minTickGap={40}
          />
          <YAxis
            dataKey="equity"
            domain={["auto", "auto"]}
            tickFormatter={(v) => formatCurrency(v, 0)}
            stroke="var(--text-faint)"
            tick={{ fontSize: 11, fontFamily: "var(--font-mono)" }}
            tickLine={false}
            axisLine={false}
            width={72}
          />
          <ReferenceLine
            y={initialCapital}
            stroke="var(--text-faint)"
            strokeDasharray="3 3"
            label={{ value: "start capital", position: "insideTopLeft", fill: "var(--text-faint)", fontSize: 10 }}
          />
          <Tooltip content={<EquityTooltip />} />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="var(--accent)"
            strokeWidth={2}
            fill="url(#equityFill)"
            className="glow-amber"
            dot={false}
            activeDot={{ r: 4, fill: "var(--accent)", stroke: "var(--bg)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function EquityTooltip({ active, payload }: { active?: boolean; payload?: { value: number; payload: { t: number } }[] }) {
  if (!active || !payload?.length) return null;
  const { value, payload: point } = payload[0];
  return (
    <div className="bg-[var(--panel-raised)] border border-[var(--border-strong)] rounded-[var(--radius-sm)] px-3 py-2 text-xs shadow-lg">
      <div className="text-[var(--text-faint)] font-mono mb-1">{formatDateTime(new Date(point.t).toISOString())}</div>
      <div className="font-mono text-[var(--accent-strong)] text-sm">{formatCurrency(value)}</div>
    </div>
  );
}
