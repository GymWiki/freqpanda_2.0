import type { JobStatus } from "@/lib/types";

const STATUS_STYLES: Record<JobStatus, { dot: string; text: string; bg: string; pulse?: boolean }> = {
  pending: { dot: "bg-[var(--text-faint)]", text: "text-[var(--text-muted)]", bg: "bg-[var(--panel-raised)]" },
  running: { dot: "bg-[var(--accent)]", text: "text-[var(--accent-strong)]", bg: "bg-[var(--accent-soft)]", pulse: true },
  completed: { dot: "bg-[var(--good)]", text: "text-[var(--good)]", bg: "bg-[var(--good-soft)]" },
  failed: { dot: "bg-[var(--critical)]", text: "text-[var(--critical)]", bg: "bg-[var(--critical-soft)]" },
};

/**
 * The "phosphor readout" signature: a monospace, uppercase status line with
 * a status dot that pulses while a job is actively running -- an old
 * terminal status indicator, repurposed for the one place this app's users
 * actually watch and wait: job polling.
 */
export function StatusPill({ status }: { status: JobStatus }) {
  const s = STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-[var(--radius-sm)] font-mono text-[11px] uppercase tracking-wide ${s.bg} ${s.text}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${s.pulse ? "pulse-dot" : ""}`} aria-hidden />
      {status}
    </span>
  );
}
