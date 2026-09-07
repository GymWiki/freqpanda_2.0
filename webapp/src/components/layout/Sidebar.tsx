"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Strategies", icon: StrategiesIcon },
  { href: "/compare", label: "Compare", icon: CompareIcon },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 shrink-0 border-r border-[var(--border)] bg-[var(--panel)] flex flex-col">
      <div className="h-16 flex items-center gap-2 px-5 border-b border-[var(--border)]">
        <span className="w-2 h-2 rounded-full bg-[var(--accent)] glow-amber" aria-hidden />
        <span className="font-display font-semibold text-[15px] tracking-tight">freqpanda</span>
      </div>

      <nav className="flex-1 px-3 py-4 flex flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-[var(--radius-md)] text-sm font-medium transition-colors ${
                active
                  ? "bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--panel-raised)]"
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-5 py-4 border-t border-[var(--border)] text-xs text-[var(--text-faint)] font-mono">
        phase 6 · webapp
      </div>
    </aside>
  );
}

function StrategiesIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} aria-hidden>
      <path d="M2 12.5 6 7l3 3 5-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2 13.5h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function CompareIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" className={className} aria-hidden>
      <rect x="2" y="2.5" width="5" height="11" rx="1" stroke="currentColor" strokeWidth="1.5" />
      <rect x="9" y="5.5" width="5" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
