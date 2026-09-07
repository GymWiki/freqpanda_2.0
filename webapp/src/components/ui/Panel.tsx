import { ReactNode } from "react";

export function Panel({
  children,
  className = "",
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div
      className={`bg-[var(--panel)] border border-[var(--border)] rounded-[var(--radius-md)] ${padded ? "p-5" : ""} ${className}`}
    >
      {children}
    </div>
  );
}

export function PanelHeader({ title, action, subtitle }: { title: ReactNode; action?: ReactNode; subtitle?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-4">
      <div>
        <h2 className="font-display font-semibold text-[15px]">{title}</h2>
        {subtitle && <p className="text-xs text-[var(--text-muted)] mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
