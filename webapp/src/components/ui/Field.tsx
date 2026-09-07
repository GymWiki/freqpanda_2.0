import { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { twMerge } from "tailwind-merge";

const CONTROL_CLASSES =
  "w-full bg-[var(--bg)] border border-[var(--border-strong)] rounded-[var(--radius-sm)] px-2.5 py-1.5 text-sm text-[var(--text)] focus:border-[var(--accent)] outline-none transition-colors placeholder:text-[var(--text-faint)] disabled:opacity-40";

export function Label({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">
      {children}
      {hint && <span className="text-[var(--text-faint)] font-normal"> · {hint}</span>}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={twMerge(CONTROL_CLASSES, props.className)} />;
}

export function NumberInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input type="number" {...props} className={twMerge(CONTROL_CLASSES, "font-mono", props.className)} />;
}

export function Select({ children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...props} className={twMerge(CONTROL_CLASSES, props.className)}>
      {children}
    </select>
  );
}

export function FieldGroup({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`grid gap-3 ${className}`}>{children}</div>;
}

export function HelpText({ children }: { children: ReactNode }) {
  return <p className="text-xs text-[var(--text-faint)] mt-1">{children}</p>;
}

export function ErrorText({ children }: { children: ReactNode }) {
  return <p className="text-xs text-[var(--critical)] mt-1">{children}</p>;
}
