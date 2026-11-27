"use client";
/**
 * Form fields (W-01). Every field has a visible label, optional hint, and optional error. Hint and
 * error ids are wired to the control through `aria-describedby`; errors also set `aria-invalid`.
 * Inputs are 48 px tall (design: `.field`). MoneyField and HoursField take a string and report the
 * parsed integer (cents / minutes) so pages never touch floats.
 */
import { useId, useState } from "react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

import { parseDollarsToCents, parseHoursToMinutes } from "@/lib/money";

import { cx } from "./cx";

const CONTROL =
  "block h-12 w-full box-border rounded-sm border bg-card px-4 text-base text-ink placeholder:text-ink-muted " +
  "disabled:cursor-not-allowed disabled:bg-track disabled:text-ink-muted";

type FieldShellProps = {
  label: string;
  hint?: string;
  error?: string;
  className?: string;
};

function describedBy(id: string, hint?: string, error?: string) {
  const ids = [error && `${id}-error`, hint && `${id}-hint`].filter(Boolean).join(" ");
  return ids || undefined;
}

function Messages({ id, hint, error }: { id: string; hint?: string; error?: string }) {
  return (
    <>
      {hint && (
        <p id={`${id}-hint`} className="text-note m-0">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${id}-error`} className="m-0 text-sm font-semibold text-alert">
          {error}
        </p>
      )}
    </>
  );
}

function Shell({
  id,
  label,
  hint,
  error,
  className,
  children,
}: FieldShellProps & { id: string; children: ReactNode }) {
  return (
    <div className={cx("flex flex-col gap-2", className)}>
      <label htmlFor={id} className="text-base font-semibold text-ink">
        {label}
      </label>
      {children}
      <Messages id={id} hint={hint} error={error} />
    </div>
  );
}

function borderFor(error?: string) {
  return error ? "border-2 border-alert" : "border-line";
}

export type TextFieldProps = FieldShellProps & Omit<InputHTMLAttributes<HTMLInputElement>, "className">;

export function TextField({ label, hint, error, className, id: idProp, ...rest }: TextFieldProps) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <Shell id={id} label={label} hint={hint} error={error} className={className}>
      <input
        id={id}
        type="text"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        className={cx(CONTROL, borderFor(error))}
        {...rest}
      />
    </Shell>
  );
}

export type SelectOption = { value: string; label: string };

export type SelectProps = FieldShellProps &
  Omit<SelectHTMLAttributes<HTMLSelectElement>, "className" | "children"> & {
    options: SelectOption[];
    placeholder?: string;
  };

export function Select({ label, hint, error, className, id: idProp, options, placeholder, ...rest }: SelectProps) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <Shell id={id} label={label} hint={hint} error={error} className={className}>
      <select
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        className={cx(CONTROL, borderFor(error))}
        {...rest}
      >
        {placeholder !== undefined && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Shell>
  );
}

export type RadioGroupProps = {
  legend: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<SelectOption & { hint?: string }>;
  hint?: string;
  error?: string;
  className?: string;
};

export function RadioGroup({ legend, name, value, onChange, options, hint, error, className }: RadioGroupProps) {
  const id = useId();
  return (
    <fieldset
      aria-describedby={describedBy(id, hint, error)}
      aria-invalid={error ? true : undefined}
      className={cx("m-0 flex min-w-0 flex-col gap-3 border-0 p-0", className)}
    >
      <legend className="mb-2 p-0 text-base font-semibold text-ink">{legend}</legend>
      {options.map((o) => (
        <label
          key={o.value}
          className={cx(
            "flex min-h-12 cursor-pointer items-start gap-3 rounded-sm border bg-card px-4 py-3",
            value === o.value ? "border-2 border-ink" : borderFor(error),
          )}
        >
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
            className="mt-1 size-5 accent-ink"
          />
          <span className="flex flex-col">
            <span className="text-base text-ink">{o.label}</span>
            {o.hint && <span className="text-note">{o.hint}</span>}
          </span>
        </label>
      ))}
      <Messages id={id} hint={hint} error={error} />
    </fieldset>
  );
}

/** Date as "YYYY-MM-DD" (the native date input's value, which is what the API takes). */
export type DateFieldProps = FieldShellProps &
  Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "type" | "value" | "onChange"> & {
    value: string;
    onChange: (value: string) => void;
  };

export function DateField({ label, hint, error, className, id: idProp, onChange, ...rest }: DateFieldProps) {
  const auto = useId();
  const id = idProp ?? auto;
  return (
    <Shell id={id} label={label} hint={hint} error={error} className={className}>
      <input
        id={id}
        type="date"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        className={cx(CONTROL, borderFor(error))}
        onChange={(e) => onChange(e.target.value)}
        {...rest}
      />
    </Shell>
  );
}

type ParsedFieldProps = FieldShellProps &
  Omit<InputHTMLAttributes<HTMLInputElement>, "className" | "type" | "value" | "onChange"> & {
    /** What the user typed. Keep it as a string in your form state. */
    value: string;
    /** Called on every change with the raw text and the parsed integer (null when empty or invalid). */
    onChange: (value: string, parsed: number | null) => void;
  };

function ParsedField({
  parse,
  invalidMessage,
  prefix,
  inputMode,
  label,
  hint,
  error,
  className,
  id: idProp,
  value,
  onChange,
  onBlur,
  ...rest
}: ParsedFieldProps & {
  parse: (s: string) => number | null;
  invalidMessage: string;
  prefix?: string;
  inputMode: "decimal" | "text";
}) {
  const auto = useId();
  const id = idProp ?? auto;
  const [touched, setTouched] = useState(false);
  const invalid = touched && value.trim() !== "" && parse(value) === null;
  const shownError = error ?? (invalid ? invalidMessage : undefined);
  return (
    <Shell id={id} label={label} hint={hint} error={shownError} className={className}>
      <div className="relative">
        {prefix && (
          <span aria-hidden className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-ink-muted">
            {prefix}
          </span>
        )}
        <input
          id={id}
          type="text"
          inputMode={inputMode}
          autoComplete="off"
          value={value}
          aria-invalid={shownError ? true : undefined}
          aria-describedby={describedBy(id, hint, shownError)}
          className={cx(CONTROL, "num", prefix && "pl-8", borderFor(shownError))}
          onChange={(e) => onChange(e.target.value, parse(e.target.value))}
          onBlur={(e) => {
            setTouched(true);
            onBlur?.(e);
          }}
          {...rest}
        />
      </div>
    </Shell>
  );
}

/** Dollars typed as text in, integer cents out (`parseDollarsToCents`). */
export function MoneyField(props: ParsedFieldProps) {
  return (
    <ParsedField
      {...props}
      parse={parseDollarsToCents}
      invalidMessage="Enter an amount like 1,234.50."
      prefix="$"
      inputMode="decimal"
    />
  );
}

/** Hours typed as "7.5" or "7:30" in, integer minutes out (`parseHoursToMinutes`). */
export function HoursField(props: ParsedFieldProps) {
  return (
    <ParsedField
      {...props}
      parse={parseHoursToMinutes}
      invalidMessage="Enter hours like 7.5 or 7:30."
      inputMode="text"
    />
  );
}
