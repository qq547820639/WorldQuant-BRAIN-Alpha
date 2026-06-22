/** Reusable form field components for ConfigPanel. */

import type { ReactNode } from "react";
import { normalizeSelectOptions, parseNumber, type SelectOption } from "./utils";

const inputClass = "form-input";

export function ConfigSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <fieldset className="panel min-w-0">
      <legend className="px-1 text-base font-semibold text-text-primary">{title}</legend>
      {description ? <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">{description}</p> : null}
      <div className="mt-4 grid grid-cols-1 gap-x-5 gap-y-4 md:grid-cols-2">{children}</div>
    </fieldset>
  );
}

export function TextField({
  label,
  value,
  maxLength,
  autoComplete,
  inputMode,
  onChange,
}: {
  label: string;
  value: string;
  maxLength?: number;
  autoComplete?: string;
  inputMode?: "email" | "text";
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-label">
      <span className="block mb-1">{label}</span>
      <input
        type="text"
        value={value}
        maxLength={maxLength}
        autoComplete={autoComplete}
        inputMode={inputMode}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      />
    </label>
  );
}

export function PasswordField({
  label,
  value,
  maxLength,
  autoComplete = "new-password",
  onChange,
}: {
  label: string;
  value: string;
  maxLength?: number;
  autoComplete?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="form-label">
      <span className="mb-1 block">{label}</span>
      <input
        type="password"
        value={value}
        maxLength={maxLength}
        autoComplete={autoComplete}
        onChange={(event) => onChange(event.currentTarget.value)}
        className={inputClass}
      />
    </label>
  );
}

export function NumberField({
  label,
  value,
  min,
  max,
  step,
  help,
  onChange,
}: {
  label: string;
  value: number;
  min?: number;
  max?: number;
  step?: number;
  help?: ReactNode;
  onChange: (value: number) => void;
}) {
  return (
    <label className="form-label">
      <span className="block mb-1">{label}{help}</span>
      <input
        type="number"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(parseNumber(event.currentTarget.value))}
        className={inputClass}
      />
    </label>
  );
}

export function SelectField({
  label,
  value,
  options,
  placeholder,
  help,
  onChange,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  placeholder?: string;
  help?: ReactNode;
  onChange: (value: string) => void;
}) {
  const choices = normalizeSelectOptions(options);
  return (
    <label className="form-label">
      <span className="block mb-1">{label}{help}</span>
      <select value={value} onChange={(event) => onChange(event.currentTarget.value)} className={inputClass}>
        {placeholder ? <option value="">{placeholder}</option> : null}
        {choices.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

export function CheckboxField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label
      className="flex items-center justify-between gap-3 py-2 text-sm font-medium text-text-secondary"
      style={{ borderBottom: '1px solid', borderBottomColor: 'var(--color-border-default)' }}
    >
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.currentTarget.checked)}
        className="h-4 w-4"
        style={{ accentColor: 'var(--color-status-active-text)' }}
      />
    </label>
  );
}

export function ConfigValue({ label, value }: { label: string; value: unknown }) {
  return (
    <div
      className="flex min-w-0 flex-wrap justify-between gap-x-3 gap-y-1 py-1.5 text-sm"
      style={{ borderBottom: '1px solid', borderBottomColor: 'var(--color-border-default)' }}
    >
      <span className="text-text-secondary">{label}</span>
      <span className="min-w-0 break-all font-mono-value text-text-primary">{String(value ?? "-")}</span>
    </div>
  );
}
