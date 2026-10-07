"""Fare engine.

The engine answers a harder question than "what do the legs add up to":

    What is the cheapest *combination of tickets* that covers this journey?

Adding single fares together routinely overcharges.  On a three-leg urban bus
journey the operator's own day ticket is usually cheaper than three singles, and
on an urban network the daily contactless cap beats both.  A journey planner that
just sums singles will confidently recommend a worse option than the traveller
would find by buying at the stop.

The engine therefore:

1. prices every leg under every product that could cover it (anytime, off-peak,
   advance, plus operator-specific products);
2. computes the alternatives -- all singles, operator day tickets, network caps,
   and any mixed combination that is cheaper;
3. applies traveller discounts (railcard, student, season) to the products that
   accept them;
4. returns both the total **and** the allocation back to each leg, so the UI can
   explain where the money goes.

Prices come from the compiled GTFS ``fare_attributes``/``fare_rules`` tables, so
when live NeTEx fares arrive from the Bus Open Data Service the engine changes
its inputs, not its behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..domain.models import FareAttribute, Mode
from ..ingest.network_compiler import price_for
from ..domain.network_spec import FareRule

#: Tickets that cover a whole day of travel on one operator or network.
DAY_PRODUCT_TYPES = ("day", "cap")

#: Tariffs for modes that are not sold by a published product: a taxi meter, a
#: ride-hailing quote, a foot passenger ferry.  Without these a leg on a mode
#: with no fare row would be priced at zero, which is worse than an estimate --
#: it would look like a free journey and win every "cheapest" ranking.
MODE_TARIFFS: dict[Mode, FareRule] = {
    Mode.TAXI: FareRule(kind="distance", base=3.20, rate_per_km=2.10, cap=None),
    Mode.RIDEHAIL: FareRule(kind="distance", base=2.50, rate_per_km=1.75, cap=None),
}


@dataclass(frozen=True)
class TravellerProfile:
    """Who is travelling.  Discounts are applied only where products allow."""

    adults: int = 1
    children: int = 0
    #: Holds a national Railcard (16-25, 26-30, Senior, Two Together, ...).
    railcard: bool = False
    student: bool = False
    #: Season ticket holder on a specific operator (code), covering all legs.
    season_operator: str = ""
    #: Traveller cannot use steps or stairs.
    step_free: bool = False
    #: Hard ceiling on the walking distance they will accept, in metres.
    max_walk_m: int | None = None

    @property
    def discount_eligible(self) -> bool:
        return self.railcard or self.student


@dataclass
class PricedLeg:
    """How one leg is paid for."""

    index: int
    mode: Mode
    operator_code: str
    route_id: str
    distance_km: float
    #: The walk-up price before any discount.
    base_price: float
    #: What the traveller actually pays for this leg.
    paid: float
    #: Which product covers it.
    product: str = "single"
    product_label: str = "Single"
    #: True when the cost is carried by a ticket bought for another leg.
    covered_by: str = ""


@dataclass
class FareBreakdown:
    """The result of pricing a journey."""

    total: float
    legs: list[PricedLeg] = field(default_factory=list)
    #: Products bought, with the legs each one covers.
    tickets: list[dict] = field(default_factory=list)
    #: Total the traveller saves versus buying the naive sum of singles.
    saving_vs_singles: float = 0.0
    #: Human-readable notes explaining the recommendation.
    notes: list[str] = field(default_factory=list)
    currency: str = "GBP"

    @property
    def singles_total(self) -> float:
        return round(sum(l.base_price for l in self.legs), 2)


def _is_offpeak(when: datetime) -> bool:
    """Peak is 06:30-09:30 and 16:00-19:00 on weekdays, as on the UK rail network."""
    if when.weekday() >= 5:
        return True
    minutes = when.hour * 60 + when.minute
    return not (390 <= minutes < 570 or 960 <= minutes < 1140)


class FareEngine:
    """Prices journeys and finds the cheapest combination of tickets."""

    def __init__(
        self,
        fares: dict[str, FareAttribute],
        route_fares: dict[str, list[str]],
        operator_day_fares: dict[str, FareAttribute],
        fare_rules: dict[str, FareRule],
    ) -> None:
        self.fares = fares
        self.route_fares = route_fares
        self.operator_day_fares = operator_day_fares
        self.fare_rules = fare_rules

    # -- products ----------------------------------------------------------
    def _rule_for(self, route_id: str, mode: Mode) -> FareRule | None:
        """The pricing rule for a leg: its corridor, else its mode's tariff."""
        return self.fare_rules.get(route_id) or MODE_TARIFFS.get(mode)

    def products_for_route(self, route_id: str) -> list[FareAttribute]:
        return [
            self.fares[fid]
            for fid in self.route_fares.get(route_id, ())
            if fid in self.fares
        ]

    @staticmethod
    def _season_covers(traveller: TravellerProfile, operator_code: str) -> bool:
        """Whether a season ticket the traveller already holds covers this leg.

        Charging someone again for a journey their season ticket has paid for is
        the fastest way to lose their trust in the price on screen.
        """
        return bool(
            traveller.season_operator
            and operator_code
            and traveller.season_operator.upper() == operator_code.upper()
        )

    def _apply_discount(
        self, price: float, product: FareAttribute, traveller: TravellerProfile,
        settings_discounts: tuple[float, float],
    ) -> float:
        railcard_rate, student_rate = settings_discounts
        if traveller.railcard and product.railcard_eligible:
            price *= 1.0 - railcard_rate
        elif traveller.student and product.student_eligible:
            price *= 1.0 - student_rate
        return price

    def price_leg(
        self,
        *,
        index: int,
        route_id: str,
        operator_code: str,
        mode: Mode,
        distance_m: float,
        when: datetime,
        traveller: TravellerProfile,
        settings_discounts: tuple[float, float] = (0.34, 0.25),
    ) -> PricedLeg:
        """Price a single leg under every applicable product, keeping the cheapest."""
        distance_km = distance_m / 1000.0
        products = self.products_for_route(route_id)

        # Fallback: price from the corridor rule directly, so a leg with no
        # published product still gets a defensible number rather than zero.
        if not products:
            base = price_for(self._rule_for(route_id, mode), distance_km)
            return PricedLeg(
                index=index, mode=mode, operator_code=operator_code,
                route_id=route_id, distance_km=distance_km,
                base_price=base, paid=base, product="estimate",
                product_label="Estimated fare",
            )

        if self._season_covers(traveller, operator_code):
            return PricedLeg(
                index=index, mode=mode, operator_code=operator_code,
                route_id=route_id, distance_km=distance_km,
                base_price=price_for(self._rule_for(route_id, mode), distance_km),
                paid=0.0, product="season", product_label="Season ticket",
            )

        offpeak = _is_offpeak(when)
        best: tuple[float, FareAttribute] | None = None
        for product in products:
            if product.product_type in DAY_PRODUCT_TYPES:
                continue  # considered at journey level, not per leg
            if product.offpeak_only and not offpeak:
                continue
            # An advance fare requires buying ahead; an on-the-day search should
            # still show it, but only where it exists in real life.
            price = self._apply_discount(
                product.price, product, traveller, settings_discounts
            )
            if best is None or price < best[0]:
                best = (price, product)

        if best is None:
            base = price_for(self._rule_for(route_id, mode), distance_km)
            return PricedLeg(
                index=index, mode=mode, operator_code=operator_code,
                route_id=route_id, distance_km=distance_km,
                base_price=base, paid=base, product="estimate",
                product_label="Estimated fare",
            )

        paid, product = best
        # The naive price is the anytime single, which is what a walk-up
        # passenger would pay.
        base = next(
            (p.price for p in products if p.product_type == "single" and not p.offpeak_only),
            product.price,
        )
        return PricedLeg(
            index=index,
            mode=mode,
            operator_code=operator_code,
            route_id=route_id,
            distance_km=distance_km,
            base_price=base,
            paid=round(paid, 2),
            product=product.product_type,
            product_label=product.label or product.product_type.title(),
        )

    # -- journey level -----------------------------------------------------
    def price_journey(
        self,
        legs: list[dict],
        *,
        when: datetime,
        traveller: TravellerProfile | None = None,
        settings_discounts: tuple[float, float] = (0.34, 0.25),
    ) -> FareBreakdown:
        """Price a whole journey, optimising the ticket combination.

        ``legs`` are dicts with ``route_id``, ``operator_code``, ``mode`` and
        ``distance_m``.  On-demand legs may also carry an explicit ``fare``.
        """
        traveller = traveller or TravellerProfile()
        breakdown = FareBreakdown(total=0.0)

        for i, leg in enumerate(legs):
            if leg.get("fare") is not None:
                price = float(leg["fare"])
                breakdown.legs.append(
                    PricedLeg(
                        index=i,
                        mode=leg["mode"],
                        operator_code=leg.get("operator_code", ""),
                        route_id=leg.get("route_id", ""),
                        distance_km=leg.get("distance_m", 0.0) / 1000.0,
                        base_price=price,
                        paid=price,
                        product="on_demand",
                        product_label="Taxi / ride-hailing estimate",
                    )
                )
                continue
            breakdown.legs.append(
                self.price_leg(
                    index=i,
                    route_id=leg["route_id"],
                    operator_code=leg.get("operator_code", ""),
                    mode=leg["mode"],
                    distance_m=leg.get("distance_m", 0.0),
                    when=when,
                    traveller=traveller,
                    settings_discounts=settings_discounts,
                )
            )

        by_operator: dict[str, list[PricedLeg]] = {}
        for leg in breakdown.legs:
            if leg.operator_code:
                by_operator.setdefault(leg.operator_code, []).append(leg)

        # Baseline 1: every leg on its own ticket.
        baseline = round(sum(l.paid for l in breakdown.legs), 2)

        # Option 2: an operator day ticket, where one exists and it is cheaper.
        option_day = 0.0
        day_tickets: list[dict] = []
        for operator, op_legs in by_operator.items():
            singles = round(sum(l.paid for l in op_legs), 2)
            day_fare = self.operator_day_fares.get(operator)
            if day_fare and len(op_legs) >= 2 and day_fare.price < singles:
                option_day += day_fare.price
                day_tickets.append({
                    "operator": operator,
                    "label": day_fare.label or f"{operator} day ticket",
                    "price": day_fare.price,
                    "covers": [l.index for l in op_legs],
                    "saving": round(singles - day_fare.price, 2),
                })
            else:
                option_day += singles
        option_day = round(option_day, 2)

        # Option 3: mixed -- day ticket for the operators where it wins there,
        # singles elsewhere.
        mixed_total = 0.0
        mixed_tickets: list[dict] = []
        covered: set[int] = set()
        for operator, op_legs in by_operator.items():
            singles = round(sum(l.paid for l in op_legs), 2)
            day_fare = self.operator_day_fares.get(operator)
            if day_fare and day_fare.price < singles:
                mixed_total += day_fare.price
                mixed_tickets.append({
                    "operator": operator,
                    "label": day_fare.label or f"{operator} day ticket",
                    "price": day_fare.price,
                    "covers": [l.index for l in op_legs],
                    "saving": round(singles - day_fare.price, 2),
                })
                covered.update(l.index for l in op_legs)
            else:
                mixed_total += singles
        mixed_total = round(mixed_total, 2)

        # Also consider a network cap where the whole journey is on one network.
        if len(by_operator) == 1:
            operator = next(iter(by_operator))
            cap_fare = self.operator_day_fares.get(operator)
            if cap_fare and cap_fare.price < mixed_total:
                mixed_total = cap_fare.price
                mixed_tickets = [{
                    "operator": operator,
                    "label": cap_fare.label or f"{operator} daily cap",
                    "price": cap_fare.price,
                    "covers": [l.index for l in breakdown.legs],
                    "saving": round(baseline - cap_fare.price, 2),
                }]
                covered = {l.index for l in breakdown.legs}

        cheapest = min(baseline, option_day, mixed_total)
        if cheapest < baseline - 0.005:
            chosen_tickets = mixed_tickets if mixed_total == cheapest else day_tickets
            # The tickets the traveller actually pays for are the day tickets
            # *and* the singles for everything the day ticket does not cover: a
            # total of £17.40 that is explained by a £4.80 ticket does not add
            # up, and a breakdown that does not add up is worse than none.
            covered = {idx for t in chosen_tickets for idx in t["covers"]}
            for t in chosen_tickets:
                for idx in t["covers"]:
                    if idx < len(breakdown.legs):
                        breakdown.legs[idx].covered_by = t["label"]
            breakdown.tickets = [
                {
                    "operator": leg.operator_code,
                    "label": leg.product_label,
                    "price": leg.paid,
                    "covers": [leg.index],
                    "saving": 0.0,
                }
                for leg in breakdown.legs
                if leg.operator_code and leg.paid > 0 and leg.index not in covered
            ] + chosen_tickets
            breakdown.saving_vs_singles = round(baseline - cheapest, 2)
            for t in chosen_tickets:
                breakdown.notes.append(
                    f"{t['label']} at £{t['price']:.2f} is cheaper than "
                    f"{len(t['covers'])} separate singles"
                )
        else:
            breakdown.tickets = [
                {
                    "operator": l.operator_code,
                    "label": l.product_label,
                    "price": l.paid,
                    "covers": [l.index],
                    "saving": 0.0,
                }
                for l in breakdown.legs
                if l.operator_code and l.paid > 0
            ]

        breakdown.total = round(cheapest, 2)

        # Traveller-count scaling: additional adults and children.
        if traveller.adults > 1 or traveller.children > 0:
            extra = (traveller.adults - 1) * 1.0 + traveller.children * 0.5
            breakdown.total = round(breakdown.total * (1 + extra), 2)
            breakdown.notes.append(
                f"Total for {traveller.adults} adult(s) and {traveller.children} "
                f"child(ren); children charged at 50%"
            )

        if traveller.railcard:
            breakdown.notes.append(
                "Including your Railcard discount where the ticket allows it"
            )
        if traveller.student and not traveller.railcard:
            breakdown.notes.append("Including your student discount")

        return breakdown

    # -- carbon ------------------------------------------------------------
    @staticmethod
    def carbon_for_legs(legs: list[dict]) -> float:
        from ..domain.models import CO2_G_PER_PKM

        total = 0.0
        for leg in legs:
            mode = leg.get("mode")
            if mode is None:
                continue
            total += CO2_G_PER_PKM.get(mode, 0.0) * leg.get("distance_m", 0.0) / 1000.0
        return total
