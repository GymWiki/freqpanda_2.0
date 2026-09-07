import { ReactNode } from "react";

export function PageHeader({
  title,
  subtitle,
  action,
  breadcrumb,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  breadcrumb?: ReactNode;
}) {
  return (
    <header className="h-16 flex items-center justify-between px-8 border-b border-[var(--border)] bg-[var(--panel)]/40 sticky top-0 backdrop-blur z-10">
      <div className="min-w-0">
        {breadcrumb && <div className="text-xs text-[var(--text-faint)] font-mono mb-0.5">{breadcrumb}</div>}
        <div className="flex items-baseline gap-3">
          <h1 className="font-display font-semibold text-lg truncate">{title}</h1>
          {subtitle && <span className="text-sm text-[var(--text-muted)] truncate">{subtitle}</span>}
        </div>
      </div>
      {action && <div className="shrink-0 flex items-center gap-2">{action}</div>}
    </header>
  );
}

export function PageBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`px-8 py-6 max-w-[1400px] ${className}`}>{children}</div>;
}
