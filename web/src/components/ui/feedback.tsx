"use client";
/**
 * Page furniture and feedback (W-01): PageHeader, Banner, EmptyState, LoadingState, ErrorState,
 * ConfirmDialog (native <dialog>), Table. Grayscale; only alert uses the --alert token (D28).
 */
import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";

import { apiErrorMessage } from "@/lib/api/client";

import { cx } from "./cx";
import { Button } from "./index";

export function PageHeader({
  eyebrow,
  title,
  lead,
  actions,
}: {
  eyebrow?: string;
  title: string;
  lead?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-2">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="text-title m-0">{title}</h1>
        {lead && <p className="text-lead m-0">{lead}</p>}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </header>
  );
}

export type BannerTone = "info" | "preview" | "warning" | "alert";

const BANNER: Record<BannerTone, { box: string; label: string }> = {
  info: { box: "border-line bg-paper-alt", label: "Note" },
  preview: { box: "border-dashed border-ink bg-card", label: "Preview" },
  warning: { box: "border-ink bg-paper-alt", label: "Heads up" },
  alert: { box: "border-alert bg-card", label: "Problem" },
};

/** `alert` uses role="alert"; the others role="status". The label word keeps meaning out of color alone. */
export function Banner({ tone = "info", title, children }: { tone?: BannerTone; title?: string; children?: ReactNode }) {
  const t = BANNER[tone];
  return (
    <div role={tone === "alert" ? "alert" : "status"} className={cx("flex flex-col gap-1 rounded-md border-2 p-4", t.box)}>
      <p className={cx("eyebrow", tone === "alert" && "text-alert")}>{t.label}</p>
      {title && <p className="m-0 text-base font-semibold text-ink">{title}</p>}
      {children && <div className="text-base text-ink-soft">{children}</div>}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-md bg-paper-alt p-8">
      <h3 className="text-heading m-0">{title}</h3>
      {children && <div className="text-base text-ink-soft">{children}</div>}
      {action}
    </div>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 p-8 text-base text-ink-muted">
      <span aria-hidden className="size-4 animate-pulse rounded-full bg-mark" />
      {label}…
    </div>
  );
}

/** Pass the `error` from `$api.useQuery`; the message comes from `apiErrorMessage`. */
export function ErrorState({
  error,
  onRetry,
  title = "We couldn't load this",
}: {
  error: unknown;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-md border-2 border-alert bg-card p-6">
      <h3 className="text-heading m-0">{title}</h3>
      <p className="m-0 text-base text-ink-soft">{apiErrorMessage(error)}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}

/** Native <dialog> opened with showModal(): focus trap, Escape and backdrop come from the browser. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  children?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault(); // the parent owns `open`
        onCancel();
      }}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-md border border-line-soft bg-card p-6 text-ink shadow-card backdrop:bg-black/40"
    >
      <div className="flex flex-col gap-4">
        <h2 id={titleId} className="text-heading m-0">
          {title}
        </h2>
        {children && <div className="text-base text-ink-soft">{children}</div>}
        <div className="flex justify-end gap-3">
          <Button onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant="primary" onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}

export type TableColumn<Row> = {
  key: string;
  header: string;
  /** Right-align with tabular numbers (money, hours). */
  numeric?: boolean;
  /** Secondary text color. */
  muted?: boolean;
  cell: (row: Row) => ReactNode;
};

/** Header style from Admin-Approve (`.tbl`). `total` is the heavier bottom row, keyed by column key. */
export function Table<Row>({
  caption,
  columns,
  rows,
  rowKey,
  total,
}: {
  caption: string;
  columns: Array<TableColumn<Row>>;
  rows: Row[];
  rowKey: (row: Row) => string;
  total?: Record<string, ReactNode>;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={cx(
                  "border-b-2 border-ink px-3 pb-3 text-left text-xs font-normal uppercase tracking-[0.12em] text-ink-muted",
                  c.numeric && "text-right",
                )}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cx(
                    "border-b border-line px-3 py-4 align-top text-base",
                    c.numeric && "num text-right",
                    c.muted ? "text-ink-soft" : "text-ink",
                  )}
                >
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {total && (
          <tfoot>
            <tr>
              {columns.map((c, i) => (
                <td
                  key={c.key}
                  className={cx(
                    "text-total border-t-2 border-ink px-3 py-4 text-left",
                    i === 0 && "font-semibold",
                    c.numeric && "num text-right",
                  )}
                >
                  {total[c.key]}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
