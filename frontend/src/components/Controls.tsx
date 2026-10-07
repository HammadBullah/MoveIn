import type { CSSProperties, ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import { Icon } from './Icons'

/** A pill the traveller can tap: filters, preferences, quick answers. */
export function Chip({
  children,
  active = false,
  onClick,
  icon,
  tone = 'default',
  compact = false,
}: {
  children: ReactNode
  active?: boolean
  onClick?: () => void
  icon?: string
  tone?: 'default' | 'green' | 'violet' | 'accent'
  compact?: boolean
}) {
  return (
    <button
      type="button"
      className={[
        'chip',
        active ? 'chip--on' : '',
        tone !== 'default' ? `chip--${tone}` : '',
        compact ? 'chip--compact' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      onClick={onClick}
      aria-pressed={active}
    >
      {icon && <Icon name={icon} size={compact ? 14 : 16} />}
      <span>{children}</span>
    </button>
  )
}

/** The switch used for preferences, alerts and the filter sheet. */
export function Toggle({
  checked,
  onChange,
  label,
  hint,
  icon,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: ReactNode
  hint?: string
  icon?: string
}) {
  return (
    <button
      type="button"
      className="toggle-row"
      onClick={() => onChange(!checked)}
      role="switch"
      aria-checked={checked}
    >
      {icon && (
        <span className="toggle-row__icon">
          <Icon name={icon} size={18} />
        </span>
      )}
      <span className="toggle-row__text">
        <span className="toggle-row__label">{label}</span>
        {hint && <span className="toggle-row__hint">{hint}</span>}
      </span>
      <span className={`switch${checked ? ' switch--on' : ''}`} aria-hidden>
        <span className="switch__knob" />
      </span>
    </button>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (next: T) => void
}) {
  return (
    <div className="segmented" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={option.value === value}
          className={`segmented__item${option.value === value ? ' segmented__item--on' : ''}`}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function Button({
  children,
  onClick,
  variant = 'primary',
  icon,
  iconRight,
  full = false,
  disabled = false,
  type = 'button',
  size = 'md',
}: {
  children: ReactNode
  onClick?: () => void
  variant?: 'primary' | 'ghost' | 'quiet' | 'danger'
  icon?: string
  iconRight?: string
  full?: boolean
  disabled?: boolean
  type?: 'button' | 'submit'
  size?: 'md' | 'sm' | 'lg'
}) {
  return (
    <button
      type={type}
      className={`btn btn--${variant} btn--${size}${full ? ' btn--full' : ''}`}
      onClick={onClick}
      disabled={disabled}
    >
      {icon && <Icon name={icon} size={size === 'sm' ? 16 : 18} />}
      <span>{children}</span>
      {iconRight && <Icon name={iconRight} size={size === 'sm' ? 16 : 18} />}
    </button>
  )
}

export function Field({
  label,
  value,
  onChange,
  placeholder,
  icon,
  onClear,
  inputMode,
  hint,
  autoFocus = false,
}: {
  label: string
  value: string
  onChange: (next: string) => void
  placeholder?: string
  icon?: string
  onClear?: () => void
  inputMode?: 'text' | 'numeric' | 'decimal'
  hint?: string
  autoFocus?: boolean
}) {
  return (
    <label className="field">
      {icon && (
        <span className="field__icon">
          <Icon name={icon} size={18} />
        </span>
      )}
      <span className="field__body">
        <span className="field__label">{label}</span>
        <input
          className="field__input"
          value={value}
          placeholder={placeholder}
          inputMode={inputMode}
          autoFocus={autoFocus}
          onChange={(event) => onChange(event.target.value)}
        />
        {hint && <span className="field__hint">{hint}</span>}
      </span>
      {value && onClear && (
        <button type="button" className="field__clear" onClick={onClear} aria-label="Clear">
          <Icon name="close" size={16} />
        </button>
      )}
    </label>
  )
}

/** A labelled row with a value on the right: "When — Today · 12:30". */
export function Row({
  icon,
  label,
  value,
  onClick,
  right,
  tone = 'default',
}: {
  icon?: string
  label: ReactNode
  value?: ReactNode
  onClick?: () => void
  right?: ReactNode
  tone?: 'default' | 'strong'
}) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      className={`list-row${onClick ? ' list-row--tap' : ''}${tone === 'strong' ? ' list-row--strong' : ''}`}
      onClick={onClick}
      {...(onClick ? { type: 'button' as const } : {})}
    >
      {icon && (
        <span className="list-row__icon">
          <Icon name={icon} size={18} />
        </span>
      )}
      <span className="list-row__label">{label}</span>
      <span className="list-row__value">{value}</span>
      {right}
      {onClick && !right && <Icon name="chevron" size={16} className="list-row__chevron" />}
    </Tag>
  )
}

export function Section({
  title,
  action,
  children,
  tight = false,
}: {
  title?: ReactNode
  action?: ReactNode
  children: ReactNode
  tight?: boolean
}) {
  return (
    <section className={`section${tight ? ' section--tight' : ''}`}>
      {(title || action) && (
        <header className="section__head">
          {title && <h2 className="section__title">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

/**
 * The bottom sheet.
 *
 * It is the shape of the whole app: the map keeps the top of the screen and the
 * sheet holds everything the traveller might want to change.  Dragging is
 * pointer-based so it works with a mouse, a finger and a stylus; the sheet also
 * snaps between half and full height for anyone who would rather tap.
 */
export function Sheet({
  children,
  height = 'half',
  onHeightChange,
  header,
  className = '',
}: {
  children: ReactNode
  height?: 'half' | 'full'
  onHeightChange?: (next: 'half' | 'full') => void
  header?: ReactNode
  className?: string
}) {
  const [drag, setDrag] = useState(0)
  const startRef = useRef<{ y: number; height: 'half' | 'full' } | null>(null)

  const onPointerDown = (event: React.PointerEvent) => {
    startRef.current = { y: event.clientY, height }
    ;(event.target as HTMLElement).setPointerCapture?.(event.pointerId)
  }
  const onPointerMove = (event: React.PointerEvent) => {
    if (!startRef.current) return
    setDrag(event.clientY - startRef.current.y)
  }
  const onPointerUp = () => {
    if (!startRef.current) return
    const moved = drag
    setDrag(0)
    if (Math.abs(moved) > 48) {
      const next = moved < 0 ? 'full' : 'half'
      onHeightChange?.(next)
    }
    startRef.current = null
  }

  return (
    <div
      className={`sheet sheet--${height}${drag ? ' sheet--dragging' : ''} ${className}`}
      style={{ transform: drag ? `translateY(${Math.max(-24, Math.min(120, drag))}px)` : undefined }}
    >
      <button
        type="button"
        className="sheet__grab"
        aria-label={height === 'full' ? 'Collapse' : 'Expand'}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClick={() => onHeightChange?.(height === 'full' ? 'half' : 'full')}
      >
        <span className="sheet__handle" />
      </button>
      {header && <div className="sheet__header">{header}</div>}
      <div className="sheet__body">{children}</div>
    </div>
  )
}

/** A short, animated appearance so list changes never feel like a jump cut. */
export function Fade({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const id = window.setTimeout(() => setShown(true), delay)
    return () => window.clearTimeout(id)
  }, [delay])
  const style: CSSProperties = {
    opacity: shown ? 1 : 0,
    transform: shown ? 'none' : 'translateY(6px)',
    transition: 'opacity .24s ease, transform .24s ease',
  }
  return <div style={style}>{children}</div>
}
