/**
 * Forte UI primitives, ported from the design system bundle (docs/design/bundle.js + bundle.css).
 * W-01 adds the rest (form fields, table, banner, empty/error/loading states, dialog). Import from
 * "@/components/ui" everywhere; don't restyle these per page.
 */
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { formatCents } from "@/lib/money";

import { cx } from "./cx";

export { cx } from "./cx";
export * from "./fields";
export * from "./feedback";
export * from "./run-tracker";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet";
  size?: "md" | "sm";
};

export function Button({ variant = "secondary", size = "md", className, type = "button", ...rest }: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-full border-2 font-semibold transition-colors",
        "disabled:cursor-not-allowed disabled:border-line disabled:bg-track disabled:text-ink-muted",
        size === "md" ? "h-11 px-6 text-base" : "h-9 px-4 text-sm",
        variant === "primary" && "border-ink bg-ink text-on-ink hover:enabled:border-ink-soft hover:enabled:bg-ink-soft",
        variant === "secondary" && "border-ink bg-transparent text-ink hover:enabled:bg-paper-alt",
        variant === "quiet" &&
          "border-transparent bg-transparent text-ink underline underline-offset-3 hover:enabled:decoration-2 disabled:border-transparent disabled:bg-transparent",
        className,
      )}
      {...rest}
    />
  );
}

/** One step of a run's lifecycle. `current` fills it (the design's run tracker). */
export function StatusPill({ current, children }: { current?: boolean; children: ReactNode }) {
  return (
    <span
      aria-current={current ? "step" : undefined}
      className={cx(
        "inline-flex h-8 items-center whitespace-nowrap rounded-full border-2 border-ink px-4 text-sm",
        current ? "bg-ink text-on-ink" : "text-ink",
      )}
    >
      {children}
    </span>
  );
}

export function Card({
  tone = "muted",
  eyebrow,
  title,
  children,
  className,
}: {
  tone?: "muted" | "raised";
  eyebrow?: string;
  title?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cx(
        "flex flex-col gap-3 rounded-md p-6",
        tone === "muted" ? "bg-paper-alt" : "border border-line-soft bg-card shadow-card",
        className,
      )}
    >
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      {title && <h3 className="text-heading m-0">{title}</h3>}
      {children && <div className="text-base text-ink-soft">{children}</div>}
    </section>
  );
}

/** Integer cents -> "$1,960.00" with tabular figures. */
export function Money({ cents, className }: { cents: number; className?: string }) {
  return <span className={cx("num", className)}>{formatCents(cents)}</span>;
}

/** Skeleton-only: marks a screen whose task hasn't landed yet. Delete it when you build the page. */
export function TaskPlaceholder({ task, title, design }: { task: string; title: string; design?: string }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 p-8">
      <p className="eyebrow">Task {task}</p>
      <h1 className="text-title m-0">{title}</h1>
      <p className="text-lead m-0">This screen is not built yet.</p>
      {design && (
        <p className="text-note m-0">
          Design: <code>docs/design/screens/{design}.dc.html</code>
        </p>
      )}
    </div>
  );
}
