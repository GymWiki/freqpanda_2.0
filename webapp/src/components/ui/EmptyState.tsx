import { ReactNode } from "react";

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-16 px-6 border border-dashed border-[var(--border-strong)] rounded-[var(--radius-md)]">
      <p className="font-display font-medium text-[var(--text)] mb-1">{title}</p>
      {body && <p className="text-sm text-[var(--text-muted)] max-w-sm mb-4">{body}</p>}
      {action}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2.5 px-4 py-3 rounded-[var(--radius-md)] bg-[var(--critical-soft)] border border-[var(--critical)]/30 text-sm text-[var(--critical)]">
      <span className="font-mono text-xs mt-0.5">ERR</span>
      <span>{message}</span>
    </div>
  );
}

export function LoadingPanel() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 bg-[var(--panel-raised)] rounded w-1/3" />
      <div className="h-24 bg-[var(--panel-raised)] rounded" />
    </div>
  );
}
