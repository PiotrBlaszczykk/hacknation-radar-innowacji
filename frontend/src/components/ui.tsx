import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react'

// Wspólne klocki interfejsu. Nowe strony składają się z nich, żeby wygląd był spójny.

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(' ')
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx('rounded-xl border border-slate-200 bg-surface', className)} {...props} />
}

const tones = {
  slate: 'bg-slate-100 text-slate-700',
  brand: 'bg-brand-50 text-brand-700',
  green: 'bg-emerald-50 text-emerald-700',
  amber: 'bg-amber-50 text-amber-800',
  violet: 'bg-violet-50 text-violet-700',
  red: 'bg-rose-50 text-rose-700',
}

export type Tone = keyof typeof tones

export function Badge({ tone = 'slate', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-semibold leading-relaxed', tones[tone])}>
      {children}
    </span>
  )
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' }

export function Button({ variant = 'primary', className, ...props }: ButtonProps) {
  const variants = {
    primary: 'bg-brand-600 text-ink hover:bg-brand-700 active:bg-brand-500',
    secondary: 'border border-control bg-surface text-slate-900 hover:border-slate-500 hover:bg-slate-50',
    ghost: 'text-slate-700 hover:bg-slate-100 hover:text-slate-900',
  }
  return (
    <button
      className={cx(
        'inline-flex items-center min-h-10 justify-center gap-2 rounded-sm px-4 py-2 text-sm font-semibold transition-colors',
        'disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500',
        variants[variant],
        className,
      )}
      {...props}
    />
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-800">{label}</span>
      {hint && <span className="mt-0.5 block text-xs text-slate-500">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  )
}

export const inputClass =
  'min-h-11 w-full rounded-sm border border-control bg-canvas px-3 py-2 text-base text-slate-900 focus:border-brand-500'

export function ChipSelect({
  options,
  value,
  onChange,
}: {
  options: { key: string; label: string }[]
  value: string[]
  onChange: (next: string[]) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const active = value.includes(option.key)
        return (
          <button
            key={option.key}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(active ? value.filter((k) => k !== option.key) : [...value, option.key])}
            className={cx(
              'min-h-9 rounded-sm border px-3 py-1 text-sm transition-colors',
              active
                ? 'border-brand-500 bg-brand-50 text-brand-700'
                : 'border-control bg-surface text-slate-700 hover:bg-slate-50',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export function Loading({ label = 'Ładowanie…' }: { label?: string }) {
  return <p role="status" className="border-y border-slate-200 px-4 py-6 text-sm text-slate-600">{label}</p>
}

export function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof TypeError
    ? 'Nie udało się połączyć z serwerem. Spróbuj ponownie.'
    : error instanceof Error ? error.message : 'Wystąpił błąd. Spróbuj ponownie.'
  return <p role="alert" className="wrap-anywhere rounded-sm border border-rose-700/35 bg-rose-50 px-4 py-3 text-sm text-rose-700">{message}</p>
}
