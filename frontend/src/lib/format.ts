import type { Mode } from './types'

export const MODE_ICON: Record<string, string> = {
  walk: '🚶',
  cycle: '🚲',
  bus: '🚌',
  coach: '🚍',
  rail: '🚆',
  tram: '🚊',
  metro: '🚇',
  ferry: '⛴️',
  taxi: '🚕',
  ridehail: '🚗',
  air: '✈️',
}

export const MODE_COLOUR: Record<string, string> = {
  walk: '#6b7280',
  cycle: '#0f766e',
  bus: '#c2410c',
  coach: '#7c3aed',
  rail: '#1d4ed8',
  tram: '#15803d',
  metro: '#b91c1c',
  ferry: '#0369a1',
  taxi: '#a16207',
  ridehail: '#4b5563',
  air: '#334155',
}

export function modeIcon(mode: string): string {
  return MODE_ICON[mode] ?? '🚏'
}

export function modeColour(mode: string): string {
  return MODE_COLOUR[mode] ?? '#4b5563'
}

export function modeLabel(mode: string): string {
  return mode === 'rail' ? 'Train' : mode.charAt(0).toUpperCase() + mode.slice(1)
}

export function minutes(seconds: number): string {
  const m = Math.round(seconds / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `${h} hr ${rest} min` : `${h} hr`
}

export function metres(m: number): string {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`
}

export function co2(grams: number): string {
  return grams < 1000 ? `${Math.round(grams)} g` : `${(grams / 1000).toFixed(2)} kg`
}

export function money(value: number): string {
  return `£${value.toFixed(2)}`
}

export function clockFromIso(iso: string): string {
  const date = new Date(iso)
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

/** ISO local datetime, which is what the API's `departure` field expects. */
export function toLocalIso(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:00`
  )
}

export function datetimeLocalValue(date: Date): string {
  return toLocalIso(date).slice(0, 16)
}

export function relativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  const diff = Date.now() - then
  const mins = Math.round(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} hr ago`
  return `${Math.round(hours / 24)} d ago`
}

export function archetypeIcon(key: string): string {
  return (
    {
      cheapest: '£',
      fastest: '⏱',
      best_value: '★',
      fewest_changes: '⇄',
      least_walking: '🚶',
      lowest_emissions: '🌱',
      accessible: '♿',
    }[key] ?? '•'
  )
}

export function occupancyLabel(value: string): string {
  return (
    {
      empty: 'Seats available',
      many_seats: 'Many seats',
      few_seats: 'Few seats',
      standing: 'Standing room only',
      full: 'Full',
      unknown: 'Unknown',
    }[value] ?? value
  )
}

export function titleCase(value: string): string {
  return value.replace(/(^|\s|-)\w/g, (c) => c.toUpperCase())
}

export function isMode(value: string): value is Mode {
  return value in MODE_ICON
}
