type Tone = "neutral" | "good" | "critical";

export function MetricTile({
  label,
  value,
  tone = "neutral",
  sublabel,
}: {
  label: string;
  value: string;
  tone?: Tone;
  sublabel?: string;
}) {
  const toneClass = tone === "good" ? "text-[var(--good)]" : tone === "critical" ? "text-[var(--critical)]" : "text-[var(--text)]";
  return (
    <div className="border border-[var(--border)] rounded-[var(--radius-md)] px-4 py-3 bg-[var(--bg)]">
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-faint)] mb-1.5">{label}</div>
      <div className={`font-mono text-xl font-medium ${toneClass}`}>{value}</div>
      {sublabel && <div className="text-xs text-[var(--text-muted)] mt-1">{sublabel}</div>}
    </div>
  );
}
