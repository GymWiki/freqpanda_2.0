import Link from "next/link";
import { ButtonHTMLAttributes, ReactNode } from "react";
import { twMerge } from "tailwind-merge";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-[var(--accent)] text-[#1a1206] hover:bg-[var(--accent-strong)] font-semibold",
  secondary:
    "bg-[var(--panel-raised)] text-[var(--text)] border border-[var(--border-strong)] hover:border-[var(--accent)]",
  ghost: "text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--panel-raised)]",
  danger: "bg-transparent text-[var(--critical)] border border-[var(--critical)]/40 hover:bg-[var(--critical-soft)]",
};

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius-md)] text-sm px-3.5 py-2 transition-colors disabled:opacity-40 disabled:pointer-events-none";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

export function Button({ variant = "secondary", className, children, ...rest }: ButtonProps) {
  return (
    <button className={twMerge(BASE, VARIANT_CLASSES[variant], className)} {...rest}>
      {children}
    </button>
  );
}

export function LinkButton({
  href,
  variant = "secondary",
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={twMerge(BASE, VARIANT_CLASSES[variant], className)}>
      {children}
    </Link>
  );
}
