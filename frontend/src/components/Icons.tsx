import type { ReactNode } from 'react'

/**
 * One icon set, drawn as line work.
 *
 * The app shows a lot of modes side by side, and mixing emoji with icons is
 * what makes a transport app look like a spreadsheet.  Everything here is a
 * 24x24 stroke drawing on `currentColor`, so an icon inherits the colour of
 * whatever it sits in — including the per-mode accents on the map.
 */
const PATHS: Record<string, ReactNode> = {
  // -- modes ---------------------------------------------------------------
  walk: (
    <>
      <circle cx="13" cy="4.2" r="1.9" />
      <path d="M11.2 21l1.6-5.4-2.6-2.4.9-4.5 3.1 2.1 2.4 1.1" />
      <path d="M9.4 12.6L7.2 21M15 12.9l1.9 3.2-1.2 4.9" />
    </>
  ),
  cycle: (
    <>
      <circle cx="6" cy="17" r="3.4" />
      <circle cx="18" cy="17" r="3.4" />
      <path d="M6 17l4.2-7h4.3L18 17M9.6 17h5.2M12.4 10l-1.2-2.6h-2" />
    </>
  ),
  bus: (
    <>
      <rect x="4" y="4.5" width="16" height="13" rx="3" />
      <path d="M4 11h16M8 17.5v1.8M16 17.5v1.8" />
      <path d="M7.6 14.2h1.4M15 14.2h1.4" />
    </>
  ),
  coach: (
    <>
      <rect x="3.6" y="3.6" width="16.8" height="14.4" rx="3" />
      <path d="M3.6 9.4h16.8M8 18v2M16 18v2M6.6 12.8h2M13.4 12.8h4" />
    </>
  ),
  rail: (
    <>
      <rect x="5" y="3.6" width="14" height="13.4" rx="3.4" />
      <path d="M5 10.4h14M9.6 7h4.8" />
      <path d="M9 17l-2.4 3.4M15 17l2.4 3.4M7.6 19.8h8.8" />
    </>
  ),
  tram: (
    <>
      <rect x="5.4" y="5.6" width="13.2" height="12.6" rx="3" />
      <path d="M5.4 11.6h13.2M9.4 8.6h5.2M12 5.6V2.6M9 5.6l-1.4-2M15 5.6l1.4-2" />
      <path d="M9.4 18.2l-1.2 2.4M14.6 18.2l1.2 2.4" />
    </>
  ),
  metro: (
    <>
      <path d="M4 20V12a8 8 0 0116 0v8" />
      <path d="M2.6 20h18.8M3.6 10.4h16.8" />
      <circle cx="12" cy="10.4" r="2.1" />
    </>
  ),
  ferry: (
    <>
      <path d="M3.4 16.4h17.2l-1.8 3.4H5.2z" />
      <path d="M5.6 16.4V10h12.8v6.4M12 10V6.4M9 6.4h6" />
      <path d="M2.6 21.4c1.4 0 2.2-.8 3.4-.8s2 .8 3.4.8 2.4-.8 3.4-.8 2 .8 3.4.8" />
    </>
  ),
  taxi: (
    <>
      <path d="M4 15.6h16v-2.8l-1.8-3.4H5.8L4 12.8z" />
      <path d="M4 15.6v2h2.6v-2M17.4 15.6v2H20v-2" />
      <path d="M9.6 9.4l1.2-2h2.4l1.2 2" />
    </>
  ),
  ridehail: (
    <>
      <path d="M4 15.2h16V12l-1.9-3.6H5.9L4 12z" />
      <path d="M4 15.2v2.4h2.8v-2.4M17.2 15.2v2.4H20v-2.4" />
      <path d="M7.4 12.6h2M14.6 12.6h2" />
    </>
  ),
  air: (
    <>
      <path d="M12 3.4c.9 0 1.5 1 1.5 2.3v3.2l6.4 3.6v2l-6.4-1.9v3.8l2 1.6v1.6l-3.5-1-3.5 1v-1.6l2-1.6v-3.8L4.1 14.5v-2l6.4-3.6V5.7c0-1.3.6-2.3 1.5-2.3z" />
    </>
  ),
  // -- interface -----------------------------------------------------------
  search: (
    <>
      <circle cx="11" cy="11" r="6.4" />
      <path d="M15.8 15.8L20.5 20.5" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21c4-4.4 6-7.6 6-10.4A6 6 0 006 10.6C6 13.4 8 16.6 12 21z" />
      <circle cx="12" cy="10.4" r="2.2" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="7.2" />
      <circle cx="12" cy="12" r="2.4" />
      <path d="M12 1.8v3.4M12 18.8v3.4M1.8 12h3.4M18.8 12h3.4" />
    </>
  ),
  swap: (
    <>
      <path d="M7.4 4.6L4 8l3.4 3.4M4 8h12.4a3.2 3.2 0 013.2 3.2v.6" />
      <path d="M16.6 19.4L20 16l-3.4-3.4M20 16H7.6a3.2 3.2 0 01-3.2-3.2v-.6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 7.4V12l3.2 2" />
    </>
  ),
  star: (
    <>
      <path d="M12 3.6l2.6 5.4 5.9.8-4.3 4.1 1 5.9-5.2-2.9-5.2 2.9 1-5.9L3.5 9.8l5.9-.8z" />
    </>
  ),
  bolt: (
    <>
      <path d="M13.4 2.6L5.6 13.4h5.1l-.9 8 7.8-10.8h-5.1z" />
    </>
  ),
  coin: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M14.6 9.2c-.6-.8-1.6-1.2-2.6-1.2-1.5 0-2.6.9-2.6 2.1 0 2.7 5.4 1.3 5.4 3.9 0 1.3-1.2 2.2-2.8 2.2-1.2 0-2.2-.5-2.8-1.4M12 6.2v1.8M12 16.2V18" />
    </>
  ),
  leaf: (
    <>
      <path d="M20 4.4c0 8.2-4.4 12.6-11 12.6H6.6C6.6 9.6 11 4.4 20 4.4z" />
      <path d="M4.6 20c1.6-3.4 4.2-6.2 7.6-8.2" />
    </>
  ),
  changes: (
    <>
      <path d="M4.6 8.4h9.2a4.6 4.6 0 010 9.2H8.4" />
      <path d="M7.4 5.6L4.6 8.4l2.8 2.8M11 14.8l-2.6 2.8L11 20.4" />
    </>
  ),
  wheelchair: (
    <>
      <circle cx="12" cy="4.4" r="1.9" />
      <path d="M11 8.2v5.2h4l2.4 6M11 13.4a5.2 5.2 0 105 5.2" />
    </>
  ),
  bell: (
    <>
      <path d="M6.6 16.4V11a5.4 5.4 0 1110.8 0v5.4l1.4 2.2H5.2z" />
      <path d="M10.2 20.4a2.2 2.2 0 003.6 0" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.4" r="3.6" />
      <path d="M4.8 20.4c.9-3.7 3.7-5.8 7.2-5.8s6.3 2.1 7.2 5.8" />
    </>
  ),
  map: (
    <>
      <path d="M3.6 6.6l5.4-2 6 2 5.4-2v12.8l-5.4 2-6-2-5.4 2z" />
      <path d="M9 4.6v12.8M15 6.6v12.8" />
    </>
  ),
  home: (
    <>
      <path d="M4.2 10.6L12 4l7.8 6.6V20a.8.8 0 01-.8.8h-4.2v-6h-5.6v6H5a.8.8 0 01-.8-.8z" />
    </>
  ),
  work: (
    <>
      <rect x="3.4" y="7.4" width="17.2" height="12.4" rx="2.4" />
      <path d="M9 7.4V5.6a1.6 1.6 0 011.6-1.6h2.8A1.6 1.6 0 0115 5.6v1.8M3.4 12.6h17.2" />
    </>
  ),
  study: (
    <>
      <path d="M2.8 8.6L12 4.4l9.2 4.2L12 12.8z" />
      <path d="M6.4 10.8v5.4c0 1.6 2.6 3 5.6 3s5.6-1.4 5.6-3v-5.4" />
    </>
  ),
  heart: (
    <>
      <path d="M12 20.4S3.6 15.6 3.6 9.9A4.4 4.4 0 0112 7.4a4.4 4.4 0 018.4 2.5c0 5.7-8.4 10.5-8.4 10.5z" />
    </>
  ),
  alert: (
    <>
      <path d="M12 3.6l8.6 15.4H3.4z" />
      <path d="M12 9.4v4.2M12 16.6v.6" />
    </>
  ),
  check: (
    <>
      <path d="M4.8 12.6l4.8 4.8L19.2 6.8" />
    </>
  ),
  close: (
    <>
      <path d="M6.4 6.4l11.2 11.2M17.6 6.4L6.4 17.6" />
    </>
  ),
  chevron: (
    <>
      <path d="M9.4 5.6l6.4 6.4-6.4 6.4" />
    </>
  ),
  chevronDown: (
    <>
      <path d="M5.6 9.4l6.4 6.4 6.4-6.4" />
    </>
  ),
  back: (
    <>
      <path d="M14.6 5.6L8.2 12l6.4 6.4" />
    </>
  ),
  filter: (
    <>
      <path d="M4 6.4h16M6.8 12h10.4M10 17.6h4" />
    </>
  ),
  plus: (
    <>
      <path d="M12 5.6v12.8M5.6 12h12.8" />
    </>
  ),
  edit: (
    <>
      <path d="M4.6 19.4h3.2L19.2 8a1.8 1.8 0 000-2.5l-.7-.7a1.8 1.8 0 00-2.5 0L4.6 16.2z" />
      <path d="M15.4 6.4l2.2 2.2" />
    </>
  ),
  trash: (
    <>
      <path d="M4.8 7.4h14.4M9.4 7.4V5.6h5.2v1.8M6.6 7.4l.9 12.2h9l.9-12.2" />
    </>
  ),
  share: (
    <>
      <path d="M12 15.6V4.2M8.4 7.8L12 4.2l3.6 3.6" />
      <path d="M5.4 13.6v5.6a1.2 1.2 0 001.2 1.2h10.8a1.2 1.2 0 001.2-1.2v-5.6" />
    </>
  ),
  wallet: (
    <>
      <rect x="3.4" y="6.4" width="17.2" height="12.2" rx="2.6" />
      <path d="M3.4 10.6h17.2M15.4 14.6h2.2" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 11v5M12 7.8v.6" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3.6l8.4 4.4-8.4 4.4-8.4-4.4z" />
      <path d="M3.6 12.4L12 16.8l8.4-4.4M3.6 16.4L12 20.8l8.4-4.4" />
    </>
  ),
  sparkle: (
    <>
      <path d="M12 3.4l1.8 5 5 1.8-5 1.8-1.8 5-1.8-5-5-1.8 5-1.8z" />
      <path d="M18.6 16.4l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" />
    </>
  ),
}

export type IconName = keyof typeof PATHS

export function Icon({
  name,
  size = 20,
  className,
  strokeWidth = 1.7,
  filled = false,
}: {
  name: IconName | string
  size?: number
  className?: string
  strokeWidth?: number
  filled?: boolean
}) {
  const path = PATHS[name] ?? PATHS.info
  return (
    <svg
      className={className ? `icon ${className}` : 'icon'}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={filled ? 0 : strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {path}
    </svg>
  )
}

/** The icon for a transit mode, in one place so every screen agrees. */
export function ModeIcon({ mode, size = 20 }: { mode: string; size?: number }) {
  const key = (
    {
      rail: 'rail',
      train: 'rail',
      bus: 'bus',
      coach: 'coach',
      tram: 'tram',
      metro: 'metro',
      underground: 'metro',
      tube: 'metro',
      ferry: 'ferry',
      taxi: 'taxi',
      ridehail: 'ridehail',
      car: 'ridehail',
      walk: 'walk',
      cycle: 'cycle',
      air: 'air',
    } as Record<string, string>
  )[mode]
  return <Icon name={key ?? 'bus'} size={size} />
}
