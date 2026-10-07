import type { Leg, Mode } from "./types";

/** The colour a mode is drawn in — used by the map, the timeline and badges. */
export const MODE_COLOUR: Record<string, string> = {
  walk: "#8A94A6",
  cycle: "#0E9F6E",
  bus: "#F97316",
  coach: "#7C3AED",
  rail: "#2563EB",
  tram: "#059669",
  metro: "#E11D48",
  ferry: "#0891B2",
  taxi: "#B45309",
  ridehail: "#475569",
  air: "#334155",
};

export function modeColour(mode: string): string {
  return MODE_COLOUR[mode] ?? "#64748B";
}

export function modeLabel(mode: string): string {
  const labels: Record<string, string> = {
    rail: "Train",
    bus: "Bus",
    coach: "Coach",
    tram: "Tram",
    metro: "Metro",
    ferry: "Ferry",
    taxi: "Taxi",
    ridehail: "Ride-hailing",
    walk: "Walk",
    cycle: "Cycle",
    air: "Flight",
  };
  return labels[mode] ?? mode.charAt(0).toUpperCase() + mode.slice(1);
}

/** "1h 42m" from seconds — the number the traveller actually reads. */
export function duration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds / 60));
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (!hours) return `${minutes}m`;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

export function bigDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds / 60));
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (!hours) return `${minutes} min`;
  return `${hours}h ${String(minutes).padStart(2, "0")}m`;
}

export function money(value: number): string {
  return `£${value.toFixed(2)}`;
}

export function metres(value: number): string {
  return value < 1000
    ? `${Math.round(value)} m`
    : `${(value / 1000).toFixed(1)} km`;
}

export function co2(grams: number): string {
  return grams < 1000
    ? `${Math.round(grams)} g`
    : `${(grams / 1000).toFixed(2)} kg`;
}

/** "12:38" — the clock face, in the timetable's own local time. */
/**
 * Clock times, in one place.
 *
 * The API is deliberately mixed about these: a journey carries full timestamps
 * (`journey.departure`), but every time *on* the journey — the legs, the
 * departure and arrival a card shows — is a wall-clock time on the service day
 * ("14:37"), because that is what a timetable prints and what a traveller reads.
 * Code that assumes one shape silently produces empty strings for the other, so
 * everything goes through these three functions.
 */

/** "14:37", or an empty string where a time should be. */
const TIME_ONLY = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/;
/** A time inside a timestamp or a local datetime: the first "HH:MM" after a T or space. */
const TIME_IN_STAMP = /[T ](\d{2}):(\d{2})(?::(\d{2}))?/;

/** A timetable time: "14:37" from anything that has one, "—" when it does not. */
export function clock(value: string | null | undefined): string {
  if (!value) return "--:--";
  const text = value.trim();
  const bare = TIME_ONLY.exec(text);
  if (bare) return `${bare[1].padStart(2, "0")}:${bare[2]}`;
  const stamp = TIME_IN_STAMP.exec(text);
  if (stamp) return `${stamp[1]}:${stamp[2]}`;
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return "--:--";
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

/** Seconds since midnight, or null.  The unit every comparison here works in. */
export function secondsOfDay(value: string | null | undefined): number | null {
  if (!value) return null;
  const text = value.trim();
  const bare = TIME_ONLY.exec(text);
  if (bare) {
    return Number(bare[1]) * 3600 + Number(bare[2]) * 60 + Number(bare[3] ?? 0);
  }
  const stamp = TIME_IN_STAMP.exec(text);
  if (stamp) {
    return (
      Number(stamp[1]) * 3600 + Number(stamp[2]) * 60 + Number(stamp[3] ?? 0)
    );
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return null;
  return date.getHours() * 3600 + date.getMinutes() * 60 + date.getSeconds();
}

/**
 * Minutes from one timetable time to another, or null.
 *
 * A journey that crosses midnight arrives *before* it departs on the clock, so
 * a large negative gap means the next day rather than a mistake.
 */
export function minutesBetween(
  from: string | null | undefined,
  to: string | null | undefined,
): number | null {
  const start = secondsOfDay(from);
  const end = secondsOfDay(to);
  if (start === null || end === null) return null;
  let delta = end - start;
  if (delta < -12 * 3600) delta += 86_400;
  return Math.round(delta / 60);
}

/** "Today · Depart 12:30", the subtitle of the results sheet. */
export function whenLabel(iso: string | null | undefined): string {
  if (!iso) return "Leave now";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Leave now";
  const todays = new Date();
  const sameDay =
    date.getFullYear() === todays.getFullYear() &&
    date.getMonth() === todays.getMonth() &&
    date.getDate() === todays.getDate();
  const clockFace = clock(iso);
  if (sameDay) return `Today · Depart ${clockFace}`;
  const tomorrow = new Date(todays.getTime() + 86_400_000);
  const isTomorrow =
    date.getFullYear() === tomorrow.getFullYear() &&
    date.getMonth() === tomorrow.getMonth() &&
    date.getDate() === tomorrow.getDate();
  const day = date.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  return `${isTomorrow ? "Tomorrow" : day} · Depart ${clockFace}`;
}

export function toLocalIso(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:00`
  );
}

export function datetimeLocalValue(date: Date): string {
  return toLocalIso(date).slice(0, 16);
}

export function relativeTime(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  return `${Math.round(hours / 24)} d ago`;
}

/** How long a journey takes door to door, as a walk of N minutes reads. */
export function walkLabel(seconds: number): string {
  if (!seconds) return "no walking";
  return `${Math.max(1, Math.ceil(seconds / 60))} min walk`;
}

/** The badge a card wears: the trade-off that makes it worth showing. */
export const ARCHETYPES: Record<
  string,
  { label: string; icon: string; tone: string }
> = {
  cheapest: { label: "Cheapest", icon: "coin", tone: "green" },
  fastest: { label: "Fastest", icon: "bolt", tone: "violet" },
  best_value: { label: "Best value", icon: "star", tone: "accent" },
  fewest_changes: { label: "Fewest changes", icon: "changes", tone: "blue" },
  least_walking: { label: "Least walking", icon: "walk", tone: "blue" },
  lowest_emissions: { label: "Lowest emissions", icon: "leaf", tone: "green" },
  accessible: { label: "Step-free", icon: "wheelchair", tone: "blue" },
};

export function archetypeMeta(key: string) {
  return ARCHETYPES[key] ?? { label: key, icon: "sparkle", tone: "accent" };
}

/** The one-line "how do I get there" summary: Bus → Train → Walk. */
export function modeChain(
  legs: Leg[],
): { mode: Mode | string; label: string }[] {
  const chain: { mode: Mode | string; label: string }[] = [];
  for (const leg of legs) {
    if (leg.kind === "walk" && legs.length > 1 && legs.indexOf(leg) === 0) {
      // The first-mile walk is a stage of the journey, not a mode to compare.
      continue;
    }
    const label =
      leg.kind === "transit"
        ? leg.route_name || modeLabel(leg.mode)
        : leg.kind === "on_demand"
          ? modeLabel(leg.mode)
          : modeLabel(leg.mode);
    const last = chain[chain.length - 1];
    if (last && last.mode === leg.mode && last.label === label) continue;
    chain.push({ mode: leg.mode, label });
  }
  return chain;
}

export function titleCase(value: string): string {
  return value.replace(/(^|\s|-)\w/g, (c) => c.toUpperCase());
}

/** "£12 coach, 3h 30m" vs "£17 train, 1h 40m" — the sentence Best value earns. */
export function explainBestValue(
  journey: { price: number; duration_s: number },
  cheapest?: { price: number; duration_s: number } | null,
): string | null {
  if (!cheapest || cheapest.price >= journey.price) return null;
  const more = journey.price - cheapest.price;
  const saved = cheapest.duration_s - journey.duration_s;
  if (saved <= 60) return null;
  return `You pay £${more.toFixed(2)} more but save ${duration(saved)}`;
}
