import { useMemo } from "react";
import { Button, Section } from "../components/Controls";
import { Icon, ModeIcon } from "../components/Icons";
import { bigDuration, clock, money } from "../lib/format";
import type { Journey, SearchResponse } from "../lib/types";

interface Row {
  key: string;
  label: string;
  mode: string;
  journey: Journey;
}

/**
 * One comparison, end to end.
 *
 * A results list ranks whole journeys; this screen answers the narrower
 * question that follows every search — "what would each *way* of doing this
 * cost me?" — which is how people actually argue with themselves on a platform.
 */
export function CompareScreen({
  result,
  fromLabel,
  toLabel,
  onBack,
  onOpenJourney,
}: {
  result: SearchResponse | null;
  fromLabel: string;
  toLabel: string;
  onBack: () => void;
  onOpenJourney: (journey: Journey) => void;
}) {
  const rows = useMemo<Row[]>(() => {
    const journeys = result?.journeys ?? [];
    const best = new Map<string, Journey>();
    for (const journey of journeys) {
      const key = journeySignature(journey);
      const current = best.get(key);
      if (!current || journey.price < current.price) best.set(key, journey);
    }
    return [...best.entries()]
      .map(([key, journey]) => ({
        key,
        label: journey.mode_label,
        mode: firstMode(journey),
        journey,
      }))
      .sort((a, b) => a.journey.price - b.journey.price);
  }, [result]);

  const cheapest = rows[0];
  const fastest = rows.reduce<Row | null>(
    (best, row) =>
      !best || row.journey.duration_s < best.journey.duration_s ? row : best,
    null,
  );
  const saving =
    cheapest && fastest
      ? Math.max(0, fastest.journey.price - cheapest.journey.price)
      : 0;

  return (
    <div className="screen screen--compare">
      <header className="detail__head">
        <button
          type="button"
          className="icon-btn"
          onClick={onBack}
          aria-label="Back"
        >
          <Icon name="back" size={20} />
        </button>
        <span className="detail__route">
          {fromLabel} → {toLabel}
        </span>
        <span className="detail__spacer" />
      </header>

      <Section title="What each way costs">
        <div className="card compare">
          <div className="compare__head">
            <span>Option</span>
            <span>Price</span>
            <span>Leaves</span>
            <span>Arrives</span>
            <span>Journey</span>
          </div>
          {rows.map((row) => {
            const isCheapest = cheapest?.key === row.key;
            const isFastest = fastest?.key === row.key;
            return (
              <button
                key={row.key}
                type="button"
                className={`compare__row${isCheapest ? " compare__row--best" : ""}`}
                onClick={() => onOpenJourney(row.journey)}
              >
                <span className="compare__option">
                  <span className="compare__mode">
                    <ModeIcon mode={row.mode} size={18} />
                  </span>
                  <span className="compare__label">
                    {row.label}
                    {isCheapest && <em className="compare__tag">Best price</em>}
                    {isFastest && !isCheapest && (
                      <em className="compare__tag">Fastest</em>
                    )}
                  </span>
                </span>
                <strong>{money(row.journey.price)}</strong>
                <span className="compare__clock">
                  {clock(row.journey.departure_time)}
                </span>
                <span className="compare__clock">
                  {clock(row.journey.arrival_time)}
                  {row.journey.arrival_day_offset > 0 && (
                    <sup className="compare__day">
                      +{row.journey.arrival_day_offset}
                    </sup>
                  )}
                </span>
                <span className="compare__time">
                  {bigDuration(row.journey.duration_s)}
                </span>
              </button>
            );
          })}
          {rows.length === 0 && (
            <p className="muted small">Run a search first.</p>
          )}
        </div>
      </Section>

      {saving > 1 && cheapest && fastest && (
        <div className="card compare__saving">
          <Icon name="wallet" size={20} />
          <div>
            <strong>You could save {money(saving)}</strong>
            <p className="muted small">
              The {cheapest.label.toLowerCase()} costs{" "}
              {money(cheapest.journey.price)} and takes{" "}
              {bigDuration(cheapest.journey.duration_s)}; the fastest option
              costs {money(fastest.journey.price)} and saves you{" "}
              {bigDuration(
                fastest.journey.duration_s - cheapest.journey.duration_s,
              )}
              .
            </p>
          </div>
        </div>
      )}

      <div className="muted tiny compare__note">
        Prices are for one adult, computed from the fares MoveIn can see for
        each operator. Tap a row for the full itinerary.
      </div>

      <Button variant="quiet" full icon="back" onClick={onBack}>
        Back to results
      </Button>
    </div>
  );
}

function journeySignature(journey: Journey): string {
  const modes = journey.legs
    .filter((leg) => leg.kind !== "walk")
    .map((leg) => (leg.kind === "transit" ? leg.mode : leg.mode))
    .join("+");
  return modes || "walk";
}

function firstMode(journey: Journey): string {
  return (
    journey.legs.find((leg) => leg.kind !== "walk")?.mode ??
    journey.legs[0]?.mode ??
    "bus"
  );
}
