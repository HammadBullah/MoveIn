"""Provider discovery.

What public data can and cannot tell us, in one place:

  * Water and sewerage: regional, so the postcode usually determines the
    company. The two can be different companies at the same address.
  * Council tax: the billing authority follows from the property location.
    The band is public; the account, balance and instalments are not.
  * Electricity and gas: **not derivable from an address**. The resident needs
    the official supplier lookup (or their network operator) or an old bill.

The table below is SAMPLE DATA for development, deliberately keyed by outward
code and labelled as demo. Replace it with a properly licensed dataset or a
maintained reference table, and keep the confidence level honest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..provenance import Field, missing, suggested

SOURCE_POSTCODE = "postcodeLookup"
SOURCE_OFFICIAL = "officialLookup"

# Lookup keys consumed by the Flutter client's official-lookup table.
LOOKUP_LINKS = {
    "electricity_supplier": {
        "title": "Find your electricity supplier",
        "operator": "Energy Networks Association",
        "url": "https://www.energynetworks.org/operating-the-networks/whos-my-network-operator",
    },
    "gas_supplier": {
        "title": "Find your gas supplier",
        "operator": "Gas supplier database",
        "url": "https://www.gassupplierdatabase.co.uk/",
    },
    "water_provider": {
        "title": "Find your water and sewerage company",
        "operator": "Water UK",
        "url": "https://www.water.org.uk/customers/find-your-supplier/",
    },
    "council_tax": {
        "title": "Check your council tax band",
        "operator": "GOV.UK",
        "url": "https://www.gov.uk/council-tax-bands",
    },
    "find_council": {
        "title": "Find your local council",
        "operator": "GOV.UK",
        "url": "https://www.gov.uk/find-local-council",
    },
    "tv_licence": {
        "title": "TV Licence",
        "operator": "TV Licensing",
        "url": "https://www.tvlicensing.co.uk/",
    },
}

# SAMPLE ONLY. Not an authoritative mapping of water companies to postcodes.
SAMPLE_WATER_BY_OUTWARD = {
    "BS": "Wessex Water (sample)",
    "CF": "Dŵr Cymru Welsh Water (sample)",
    "LS": "Yorkshire Water (sample)",
    "M": "United Utilities (sample)",
    "SW": "Thames Water (sample)",
}

SAMPLE_COUNCIL_BY_OUTWARD = {
    "BS": "Bristol City Council (sample)",
    "CF": "Cardiff Council (sample)",
    "LS": "Leeds City Council (sample)",
    "M": "Manchester City Council (sample)",
    "SW": "London Borough of Wandsworth (sample)",
}


@dataclass(frozen=True)
class Suggestion:
    kind: str
    provider: Field
    confidence: str  # areaCertain | areaOnly | unknown
    lookup_keys: list[str]
    explanation: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "provider": self.provider.to_dict(),
            "confidence": self.confidence,
            "lookupKeys": self.lookup_keys,
            "explanation": self.explanation,
        }


def outward_code(postcode: str) -> str:
    return postcode.replace(" ", "").upper()[:-3] if postcode else ""


def outward_letters(postcode: str) -> str:
    letters = []
    for char in outward_code(postcode):
        if char.isalpha():
            letters.append(char)
        else:
            break
    return "".join(letters)


def discover(postcode: str) -> list[Suggestion]:
    """Return what can honestly be suggested for this postcode.

    Always includes explicit "unknown" entries for electricity and gas, so the
    client can render them as "provider not found" rather than omitting them.
    """
    prefix = outward_letters(postcode)
    suggestions: list[Suggestion] = []

    water = SAMPLE_WATER_BY_OUTWARD.get(prefix)
    if water:
        suggestions.append(
            Suggestion(
                kind="water",
                provider=suggested(
                    water,
                    SOURCE_POSTCODE,
                    note="Sample regional lookup. Confirm this is the company that bills you.",
                ),
                confidence="areaCertain",
                lookup_keys=["water_provider"],
                explanation="Water supply is regional, so it normally follows from the postcode.",
            )
        )
        # Sewerage may be a different company: same suggestion, lower confidence.
        suggestions.append(
            Suggestion(
                kind="wastewater",
                provider=suggested(
                    water,
                    SOURCE_POSTCODE,
                    note="Often a different company from your water supplier. Confirm separately.",
                ),
                confidence="areaOnly",
                lookup_keys=["water_provider"],
            )
        )

    council = SAMPLE_COUNCIL_BY_OUTWARD.get(prefix)
    if council:
        suggestions.append(
            Suggestion(
                kind="councilTax",
                provider=suggested(
                    council,
                    SOURCE_POSTCODE,
                    note="Billing authority follows from the address. The account and instalments do not.",
                ),
                confidence="areaCertain",
                lookup_keys=["council_tax", "find_council"],
            )
        )

    # Never guessed: an address cannot tell us who supplies energy.
    suggestions.append(
        Suggestion(
            kind="electricity",
            provider=missing(),
            confidence="unknown",
            lookup_keys=["electricity_supplier"],
            explanation="Electricity supplier is per property and per account. Use the official lookup.",
        )
    )
    suggestions.append(
        Suggestion(
            kind="gas",
            provider=missing(),
            confidence="unknown",
            lookup_keys=["gas_supplier"],
            explanation="Gas supplier cannot be derived from an address. Use the official lookup.",
        )
    )
    return suggestions
