"""The MoveIn Phase 1 transport network, expressed as real service corridors.

Every stop named in this file is a **real** UK public transport location.  Rail
stations are referenced by their CRS code and resolved against
``data/raw/rail_stations.csv`` (Network Rail TIPLOCs); bus, tram and coach
interchanges are referenced by name and resolved against the real NaPTAN
named-stop inventory in ``data/raw/naptan_named_stops.csv``.

What is *real* here
-------------------
* the geography -- every stop's coordinates, and therefore every distance and
  every running time that follows from them
* the operators -- real UK operators with their real NOC / ATOC codes
* the corridors -- these are the actual rail lines, tram systems and coach
  routes that serve these places

What is *compiled*
------------------
* the departure times.  Real timetables live in the DfT Bus Open Data Service
  and the RDG CIF feed, neither of which is reachable from the environment this
  prototype was built in.  ``app.ingest.network_compiler`` therefore compiles a
  deterministic, seeded timetable onto the real geography at the service
  frequencies documented below.  ``docs/DATA_SOURCES.md`` explains how the
  BODS/GTFS adapters replace it with live data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Service patterns
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ServicePattern:
    """How often a corridor runs and how fast it is."""

    first_departure: str = "05:30"
    last_departure: str = "23:00"
    #: Peak headway (07:00-09:30 and 16:00-18:30), in minutes.
    peak_headway: int = 20
    #: Off-peak headway in minutes.
    offpeak_headway: int = 30
    #: Commercial running speed in km/h.  Real point-to-point averages for the
    #: mode, excluding station dwell.
    speed_kph: float = 32.0
    #: Station/stop dwell time in seconds.
    dwell_s: int = 25
    #: Extra dwell at an interchange-scale stop, in seconds.
    major_dwell_s: int = 120
    #: Days of the week the service operates (Mon=0 .. Sun=6).
    days: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
    #: True for services that do not run on public holidays.
    except_holidays: bool = True
    #: Optional fixed off-peak frequency discount for promotional services.
    night_headway: int | None = None


@dataclass(frozen=True)
class FareRule:
    """Pricing rule for a corridor.

    ``kind`` selects how the base price is computed:

    * ``flat``     -- a single price regardless of distance (urban bus/tram)
    * ``distance`` -- price = base + rate * km, capped
    * ``tapered``  -- distance pricing with a reducing marginal rate, which is
      how UK rail fares actually behave over longer distances
    """

    kind: str = "distance"
    base: float = 0.60
    rate_per_km: float = 0.145
    cap: float | None = None
    #: Multiplier applied to advance/off-peak tickets.
    offpeak_multiplier: float = 0.72
    #: Multiplier for an anytime/on-the-day ticket.
    anytime_multiplier: float = 1.0
    #: Multiplier for an advance purchase (limited quota) fare.
    advance_multiplier: float = 0.55
    #: Fare zone / contactless cap for the whole network, per day.
    day_cap: float | None = None
    #: Price of an operator day ticket (unlimited travel on that operator).
    day_ticket: float | None = None
    #: Round-trip price as a multiple of a single.
    return_multiplier: float = 1.9
    #: Whether a return ticket is offered at all.
    offers_returns: bool = True
    #: Chained journeys on the same operator within this window are free.
    transfer_window_min: int = 0


# --------------------------------------------------------------------------
# Corridors
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Corridor:
    """One service running over a fixed sequence of real stops."""

    code: str
    #: Key into :mod:`app.ingest.registry`.
    operator: str
    mode: str
    #: Real stop references, in travel order.  ``R:`` prefixes a CRS code,
    #: ``N:`` prefixes a NaPTAN stop name.
    stops: tuple[str, ...]
    pattern: ServicePattern = field(default_factory=ServicePattern)
    fare: FareRule = field(default_factory=FareRule)
    #: Marketing name shown in the UI.
    name: str = ""
    #: Modelled regions this corridor runs through.  Used to disambiguate stop
    #: names that exist in more than one city, and to reject fuzzy matches that
    #: land at the wrong end of the country.
    regions: tuple[str, ...] = ()
    #: True when the service carries a high volume of commuters.
    commuter: bool = False
    #: Relative weight when sampling which services to run in a thin slice.
    weight: float = 1.0

    def resolved_stops(self) -> tuple[str, ...]:
        return self.stops


# ==========================================================================
# RAIL -- real lines, real stations, real operators
# ==========================================================================

_RAIL_PATTERN = ServicePattern(
    first_departure="05:15",
    last_departure="23:15",
    peak_headway=30,
    offpeak_headway=60,
    speed_kph=118.0,
    dwell_s=60,
    major_dwell_s=180,
)

_LOCAL_RAIL_PATTERN = ServicePattern(
    first_departure="05:45",
    last_departure="23:00",
    peak_headway=30,
    offpeak_headway=60,
    speed_kph=72.0,
    dwell_s=45,
    major_dwell_s=120,
)

_RAIL_FARE = FareRule(
    kind="tapered",
    base=1.60,
    rate_per_km=0.205,
    cap=189.00,
    offpeak_multiplier=0.78,
    anytime_multiplier=1.0,
    advance_multiplier=0.52,
    day_cap=None,
    return_multiplier=1.92,
)

RAIL_CORRIDORS: tuple[Corridor, ...] = (
    # --- Midland Main Line: London - Leicester - Derby - Sheffield ----------
    Corridor(
        code="MML-1",
        operator="EM",
        mode="rail",
        name="Midland Main Line",
        stops=(
            "R:STP", "R:LUT", "R:BDM", "R:WEL", "R:KET", "R:MHR", "R:LEI",
            "R:LBO", "R:EMD", "R:LGE", "R:DBY", "R:CHD", "R:SHF",
        ),
        pattern=_RAIL_PATTERN,
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.4,
    ),
    # --- CrossCountry: Nottingham - Derby - Birmingham ----------------------
    Corridor(
        code="XC-1",
        operator="XC",
        mode="rail",
        name="Nottingham - Birmingham",
        stops=(
            "R:NOT", "R:BEE", "R:LGE", "R:DBY", "R:WIL", "R:BUT", "R:TAM",
            "R:WNE", "R:BHM",
        ),
        pattern=ServicePattern(
            first_departure="05:40",
            last_departure="22:45",
            peak_headway=30,
            offpeak_headway=60,
            speed_kph=104.0,
            dwell_s=60,
            major_dwell_s=240,
        ),
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.5,
    ),
    # --- West Coast Main Line: Euston - Birmingham - Manchester -------------
    Corridor(
        code="WCML-1",
        operator="VT",
        mode="rail",
        name="West Coast Main Line",
        stops=(
            "R:EUS", "R:WFJ", "R:MKC", "R:RUG", "R:COV", "R:BHI", "R:BHM",
            "R:WVH", "R:CRE", "R:SPT", "R:MAN",
        ),
        pattern=ServicePattern(
            first_departure="05:00",
            last_departure="23:30",
            peak_headway=20,
            offpeak_headway=40,
            speed_kph=142.0,
            dwell_s=90,
            major_dwell_s=300,
        ),
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.6,
    ),
    # --- Birmingham - London via Coventry fast ------------------------------
    Corridor(
        code="WCML-2",
        operator="LM",
        mode="rail",
        name="Birmingham - London (via Coventry)",
        stops=("R:BHM", "R:BHI", "R:COV", "R:RUG", "R:MKC", "R:EUS"),
        pattern=ServicePattern(
            first_departure="05:20",
            last_departure="23:00",
            peak_headway=30,
            offpeak_headway=60,
            speed_kph=126.0,
            dwell_s=75,
            major_dwell_s=240,
        ),
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.3,
    ),
    # --- CrossCountry: Manchester - Birmingham - Reading - Bournemouth -----
    Corridor(
        code="XC-2",
        operator="XC",
        mode="rail",
        name="Manchester - Birmingham - South Coast",
        stops=(
            "R:MAN", "R:SPT", "R:MAC", "R:SOT", "R:STA", "R:WVH", "R:BHM",
            "R:OXF", "R:RDG", "R:SOU", "R:BMH",
        ),
        pattern=ServicePattern(
            first_departure="05:30",
            last_departure="22:30",
            peak_headway=60,
            offpeak_headway=60,
            speed_kph=112.0,
            dwell_s=75,
            major_dwell_s=300,
        ),
        fare=_RAIL_FARE,
        weight=1.1,
    ),
    # --- CrossCountry: Birmingham - Leicester -------------------------------
    Corridor(
        code="XC-3",
        operator="XC",
        mode="rail",
        name="Birmingham - Leicester",
        stops=("R:BHM", "R:CEH", "R:NUN", "R:HNK", "R:LEI"),
        pattern=ServicePattern(
            first_departure="06:00",
            last_departure="22:30",
            peak_headway=60,
            offpeak_headway=60,
            speed_kph=92.0,
            dwell_s=60,
        ),
        fare=_RAIL_FARE,
        weight=1.0,
    ),
    # --- East Midlands Railway: Nottingham - Derby - Leicester -------------
    Corridor(
        code="EMR-2",
        operator="EM",
        mode="rail",
        name="Nottingham - Derby - Leicester",
        stops=("R:NOT", "R:BEE", "R:DBY", "R:LEI"),
        pattern=_LOCAL_RAIL_PATTERN,
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.2,
    ),
    # --- East Midlands: Nottingham - Grantham - Peterborough - Norwich -----
    Corridor(
        code="EMR-3",
        operator="EM",
        mode="rail",
        name="Nottingham - Peterborough",
        stops=("R:NOT", "R:BIN", "R:GRA", "R:PBO"),
        pattern=ServicePattern(
            first_departure="06:15",
            last_departure="22:15",
            peak_headway=60,
            offpeak_headway=60,
            speed_kph=106.0,
            dwell_s=60,
        ),
        fare=_RAIL_FARE,
        weight=0.9,
    ),
    # --- EMR: Nottingham - Mansfield - Worksop (Robin Hood Line) -----------
    Corridor(
        code="EMR-4",
        operator="EM",
        mode="rail",
        name="Robin Hood Line",
        stops=(
            "R:NOT", "R:BLW", "R:HKN", "R:KKB", "R:MSW", "R:WRK",
        ),
        pattern=ServicePattern(
            first_departure="06:00",
            last_departure="22:00",
            peak_headway=60,
            offpeak_headway=60,
            speed_kph=64.0,
            dwell_s=45,
        ),
        fare=_RAIL_FARE,
        weight=0.8,
    ),
    # --- EMR: Nottingham - Derby - Ilkeston - Chesterfield ------------------
    Corridor(
        code="EMR-5",
        operator="EM",
        mode="rail",
        name="Nottingham - Chesterfield",
        stops=("R:NOT", "R:ILN", "R:DBY", "R:DFI", "R:CHD"),
        pattern=_LOCAL_RAIL_PATTERN,
        fare=_RAIL_FARE,
        weight=0.9,
    ),
    # --- West Midlands Trains: Birmingham - Wolverhampton - Crewe ----------
    Corridor(
        code="WMT-1",
        operator="LM",
        mode="rail",
        name="Birmingham - Crewe",
        stops=("R:BHM", "R:WVH", "R:CRE"),
        pattern=_LOCAL_RAIL_PATTERN,
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.1,
    ),
    # --- West Midlands Railway: Birmingham - Worcester ---------------------
    Corridor(
        code="WMT-2",
        operator="LM",
        mode="rail",
        name="Birmingham - Worcester",
        stops=("R:BHM", "R:UNI", "R:BMV", "R:WOF"),
        pattern=_LOCAL_RAIL_PATTERN,
        fare=_RAIL_FARE,
        weight=0.8,
    ),
    # --- Chiltern: Birmingham Moor Street - Solihull - Stratford -----------
    Corridor(
        code="CH-1",
        operator="CH",
        mode="rail",
        name="Birmingham - Stratford-upon-Avon",
        stops=("R:BMO", "R:SOL", "R:DDG", "R:SAV"),
        pattern=ServicePattern(
            first_departure="06:20",
            last_departure="22:20",
            peak_headway=60,
            offpeak_headway=60,
            speed_kph=68.0,
            dwell_s=45,
        ),
        fare=_RAIL_FARE,
        weight=0.7,
    ),
    # --- Northern: Sheffield - Leeds - York --------------------------------
    Corridor(
        code="NT-1",
        operator="NT",
        mode="rail",
        name="Sheffield - Leeds - York",
        stops=("R:SHF", "R:MHS", "R:BNY", "R:WKK", "R:LDS", "R:YRK"),
        pattern=_LOCAL_RAIL_PATTERN,
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.2,
    ),
    # --- TransPennine Express: Leeds - Huddersfield - Manchester -----------
    Corridor(
        code="TP-1",
        operator="TP",
        mode="rail",
        name="Leeds - Manchester",
        stops=("R:LDS", "R:HUD", "R:SYB", "R:MAN"),
        pattern=ServicePattern(
            first_departure="05:35",
            last_departure="23:05",
            peak_headway=30,
            offpeak_headway=60,
            speed_kph=96.0,
            dwell_s=60,
            major_dwell_s=180,
        ),
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.3,
    ),
    # --- Northern: Leeds - Bradford ----------------------------------------
    Corridor(
        code="NT-2",
        operator="NT",
        mode="rail",
        name="Leeds - Bradford",
        stops=("R:LDS", "R:BDI"),
        pattern=ServicePattern(
            first_departure="06:00",
            last_departure="23:00",
            peak_headway=20,
            offpeak_headway=30,
            speed_kph=56.0,
            dwell_s=45,
        ),
        fare=_RAIL_FARE,
        commuter=True,
        weight=1.0,
    ),
    # --- Northern: Manchester - Wigan - Southport --------------------------
    Corridor(
        code="NT-3",
        operator="NT",
        mode="rail",
        name="Manchester - Southport",
        stops=("R:MAN", "R:WGW", "R:SOP"),
        pattern=_LOCAL_RAIL_PATTERN,
        fare=_RAIL_FARE,
        weight=0.8,
    ),
    # --- LNER: Leeds - York - Newcastle ------------------------------------
    Corridor(
        code="GR-1",
        operator="GR",
        mode="rail",
        name="Leeds - Newcastle",
        stops=("R:LDS", "R:YRK", "R:NTR", "R:DAR", "R:DHM", "R:NCL"),
        pattern=ServicePattern(
            first_departure="06:00",
            last_departure="22:00",
            peak_headway=60,
            offpeak_headway=60,
            speed_kph=150.0,
            dwell_s=90,
            major_dwell_s=240,
        ),
        fare=_RAIL_FARE,
        weight=0.9,
    ),
    # --- East Midlands: Nottingham - Newark - Lincoln ----------------------
    Corridor(
        code="EMR-6",
        operator="EM",
        mode="rail",
        name="Nottingham - Lincoln",
        stops=("R:NOT", "R:NCT", "R:LCN"),
        pattern=ServicePattern(
            first_departure="06:30",
            last_departure="22:00",
            peak_headway=60,
            offpeak_headway=60,
            speed_kph=80.0,
            dwell_s=60,
        ),
        fare=_RAIL_FARE,
        weight=0.7,
    ),
)


# ==========================================================================
# TRAM / METRO -- real light-rail systems
# ==========================================================================

_TRAM_PATTERN = ServicePattern(
    first_departure="05:30",
    last_departure="23:30",
    peak_headway=7,
    offpeak_headway=12,
    speed_kph=26.0,
    dwell_s=30,
    major_dwell_s=60,
    days=(0, 1, 2, 3, 4, 5, 6),
)

_TRAM_FARE = FareRule(
    kind="flat",
    base=2.70,
    rate_per_km=0.0,
    offpeak_multiplier=1.0,
    anytime_multiplier=1.0,
    advance_multiplier=1.0,
    day_cap=5.40,
    day_ticket=5.40,
    offers_returns=True,
    return_multiplier=1.6,
)

TRAM_CORRIDORS: tuple[Corridor, ...] = (
    # --- Nottingham Express Transit (NET) ----------------------------------
    # Real NET stops, in the real running order of Line 1 (Hucknall - Toton
    # Lane) through the city centre.
    Corridor(
        code="NET-1",
        operator="NET",
        mode="tram",
        name="NET Line 1: Hucknall - Toton Lane",
        regions=("nottingham", "beeston"),
        stops=(
            "N:Hucknall Tram","N:Moor Bridge","N:Bulwell Forest",
            "N:Highbury Vale","N:Wilkinson Street","N:Royal Centre",
            "N:Old Market Square","N:Lace Market","N:Nottingham Station",
            "N:Wilford Lane","N:Compton Acres","N:Ruddington Lane",
            "N:Cator Lane",
        ),
        pattern=_TRAM_PATTERN,
        fare=_TRAM_FARE,
        commuter=True,
        weight=1.1,
    ),
    Corridor(
        code="NET-2",
        operator="NET",
        mode="tram",
        name="NET Line 2: Phoenix Park - Clifton",
        regions=("nottingham",),
        stops=(
            "N:Phoenix Park","N:Cinderhill","N:Highbury Vale",
            "N:Royal Centre","N:Old Market Square",
            "N:Lace Market","N:Nottingham Station","N:Wilford Lane",
        ),
        pattern=_TRAM_PATTERN,
        fare=_TRAM_FARE,
        weight=1.0,
    ),
    # ------------------------------------------------------------------
    # NOT COMPILED YET: West Midlands Metro and Sheffield Supertram.
    #
    # Both systems' stop names are absent from the NaPTAN named-stop extract
    # that ships with this prototype -- a grep of the bundled inventory returns
    # zero hits for Wednesbury, Priestfield, Bilston, Winson Green, Jewellery
    # Quarter, Brindleyplace, Malin Bridge and Woodbourn Road.  Their nodes do
    # exist in the full NaPTAN register under 940-series ATCO codes, but that
    # extract carries no names.
    #
    # Rather than invent stop names, both corridors are held back until the
    # full NaPTAN names feed is wired in (see docs/DATA_SOURCES.md, "Adding a
    # light-rail system").  Metrolink and the Underground *are* compiled, below,
    # because their real stop names are present.
    # ------------------------------------------------------------------
    # --- Manchester Metrolink ----------------------------------------------
    Corridor(
        code="ML-1",
        operator="ML",
        mode="tram",
        name="Metrolink Bury - Piccadilly",
        stops=(
            "N:Bury (Manchester Metrolink)","N:Whitefield (Manchester Metrolink)",
            "N:Prestwich (Manchester Metrolink)","N:Heaton Park (Manchester Metrolink)",
            "N:Bowker Vale (Manchester Metrolink)","N:Crumpsall (Manchester Metrolink)",
            "N:Abraham Moss (Manchester Metrolink)","N:Queens Road (Manchester Metrolink)",
            "N:Victoria (Manchester Metrolink)","N:Shudehill (Manchester Metrolink)",
            "N:Market Street (Manchester Metrolink)","N:Piccadilly (Manchester Metrolink)",
        ),
        pattern=ServicePattern(
            first_departure="05:00", last_departure="23:45",
            peak_headway=6, offpeak_headway=12, speed_kph=30.0,
            dwell_s=25, days=(0, 1, 2, 3, 4, 5, 6),
        ),
        fare=_TRAM_FARE,
        commuter=True,
        weight=1.2,
    ),
    Corridor(
        code="ML-2",
        operator="ML",
        mode="tram",
        name="Metrolink East Didsbury - Rochdale",
        stops=(
            "N:East Didsbury (Manchester Metrolink)",
            "N:West Didsbury (Manchester Metrolink)",
            "N:Withington (Manchester Metrolink)",
            "N:St Werburgh's Road (Manchester Metrolink)",
            "N:Firswood Station (Manchester Metrolink)",
            "N:Trafford Bar (Manchester Metrolink)",
            "N:Cornbrook (Manchester Metrolink)",
            "N:Deansgate-Castlefield (Manchester Metrolink)",
            "N:St Peter's Square (Manchester Metrolink)",
            "N:Exchange Square (Manchester Metrolink)",
            "N:Monsall (Manchester Metrolink)",
            "N:Newton Heath & Moston (Manchester Metrolink)",
            "N:Oldham Central (Manchester Metrolink)",
            "N:Oldham Mumps (Manchester Metrolink)",
            "N:Rochdale Railway Station (Manchester Metrolink)",
        ),
        pattern=ServicePattern(
            first_departure="05:00", last_departure="23:45",
            peak_headway=6, offpeak_headway=12, speed_kph=30.0,
            dwell_s=25, days=(0, 1, 2, 3, 4, 5, 6),
        ),
        fare=_TRAM_FARE,
        weight=1.1,
    ),
    # Sheffield Supertram: see note above -- held back pending real stop names.
)


# ==========================================================================
# LONDON -- Underground and Overground
# ==========================================================================

_TUBE_PATTERN = ServicePattern(
    first_departure="05:15",
    last_departure="00:15",
    peak_headway=4,
    offpeak_headway=8,
    speed_kph=33.0,
    dwell_s=25,
    major_dwell_s=60,
    days=(0, 1, 2, 3, 4, 5, 6),
)

#: TfL fares are zone-based, not distance-based; the compiler applies a
#: zone model for these corridors (see ``fare_engine``).
TUBE_FARE = FareRule(
    kind="flat",
    base=2.80,
    rate_per_km=0.0,
    offpeak_multiplier=1.0,
    anytime_multiplier=1.0,
    advance_multiplier=1.0,
    day_cap=8.90,
    day_ticket=8.90,
    offers_returns=False,
    return_multiplier=2.0,
)

LONDON_CORRIDORS: tuple[Corridor, ...] = (
    Corridor(
        code="TFL-PIC",
        operator="TFL",
        mode="metro",
        name="Piccadilly line",
        stops=(
            "N:Heathrow Terminals 2 & 3","N:Hatton Cross","N:Hounslow West",
            "N:Acton Town","N:Hammersmith","N:Earl's Court","N:Gloucester Road",
            "N:South Kensington","N:Knightsbridge","N:Hyde Park Corner",
            "N:Green Park","N:Piccadilly Circus","N:Leicester Square",
            "N:Covent Garden","N:Holborn","N:Russell Square",
            "N:Kings Cross St Pancras","N:Caledonian Road","N:Finsbury Park",
            "N:Manor House","N:Turnpike Lane","N:Wood Green","N:Bounds Green",
            "N:Arnos Grove","N:Cockfosters",
        ),
        pattern=_TUBE_PATTERN,
        fare=TUBE_FARE,
        commuter=True,
        weight=1.5,
    ),
    Corridor(
        code="TFL-NOR",
        operator="TFL",
        mode="metro",
        name="Northern line",
        stops=(
            "N:Morden","N:South Wimbledon","N:Colliers Wood","N:Tooting Bec",
            "N:Balham","N:Clapham South","N:Clapham Common","N:Clapham North",
            "N:Stockwell","N:Oval","N:Kennington","N:Elephant & Castle",
            "N:Borough","N:London Bridge","N:Bank","N:Moorgate",
            "N:Old Street","N:Angel","N:Kings Cross St Pancras",
            "N:Euston","N:Warren Street","N:Goodge Street",
            "N:Tottenham Court Road","N:Leicester Square","N:Charing Cross",
            "N:Embankment","N:Waterloo","N:Camden Town","N:Edgware",
        ),
        pattern=_TUBE_PATTERN,
        fare=TUBE_FARE,
        commuter=True,
        weight=1.4,
    ),
    Corridor(
        code="TFL-CEN",
        operator="TFL",
        mode="metro",
        name="Central line",
        stops=(
            "N:West Ruislip","N:Northolt","N:Greenford","N:Perivale",
            "N:Hanger Lane","N:North Acton","N:White City",
            "N:Shepherd's Bush","N:Holland Park","N:Notting Hill Gate",
            "N:Queensway","N:Lancaster Gate","N:Marble Arch","N:Bond Street",
            "N:Oxford Circus","N:Tottenham Court Road","N:Holborn",
            "N:Chancery Lane","N:St Paul's","N:Bank","N:Liverpool Street",
            "N:Bethnal Green","N:Mile End","N:Stratford","N:Leyton",
        ),
        pattern=_TUBE_PATTERN,
        fare=TUBE_FARE,
        commuter=True,
        weight=1.4,
    ),
    Corridor(
        code="TFL-VIC",
        operator="TFL",
        mode="metro",
        name="Victoria line",
        stops=(
            "N:Brixton","N:Stockwell","N:Vauxhall","N:Pimlico",
            "N:Victoria","N:Green Park","N:Oxford Circus",
            "N:Warren Street","N:Euston","N:Kings Cross St Pancras",
            "N:Highbury & Islington","N:Finsbury Park","N:Seven Sisters",
            "N:Tottenham Hale","N:Blackhorse Road","N:Walthamstow Central",
        ),
        pattern=_TUBE_PATTERN,
        fare=TUBE_FARE,
        commuter=True,
        weight=1.4,
    ),
    Corridor(
        code="TFL-JUB",
        operator="TFL",
        mode="metro",
        name="Jubilee line",
        stops=(
            "N:Stanmore","N:Canons Park","N:Queensbury","N:Kingsbury",
            "N:Neasden","N:Willesden Green","N:Finchley Road",
            "N:Swiss Cottage","N:St John's Wood","N:Baker Street",
            "N:Bond Street","N:Green Park","N:Westminster",
            "N:Waterloo","N:Southwark","N:London Bridge",
            "N:Bermondsey","N:Canada Water","N:Canary Wharf",
            "N:North Greenwich","N:Canning Town","N:Stratford",
        ),
        pattern=_TUBE_PATTERN,
        fare=TUBE_FARE,
        commuter=True,
        weight=1.3,
    ),
    Corridor(
        code="TFL-ELZ",
        operator="TFL",
        mode="metro",
        name="Elizabeth line",
        stops=(
            "N:Heathrow Airport Central","N:Southall","N:Hanwell",
            "N:Ealing Broadway","N:Paddington","N:Bond Street",
            "N:Tottenham Court Road","N:Farringdon","N:Liverpool Street",
            "N:Whitechapel","N:Canary Wharf","N:Custom House",
            "N:Woolwich","N:Abbey Wood",
        ),
        pattern=ServicePattern(
            first_departure="05:15", last_departure="23:45",
            peak_headway=5, offpeak_headway=10, speed_kph=60.0,
            dwell_s=45, major_dwell_s=120, days=(0, 1, 2, 3, 4, 5, 6),
        ),
        fare=TUBE_FARE,
        commuter=True,
        weight=1.3,
    ),
)


# ==========================================================================
# COACH -- real National Express / Megabus / FlixBus corridors
# ==========================================================================

_COACH_PATTERN = ServicePattern(
    first_departure="05:00",
    last_departure="23:00",
    peak_headway=60,
    offpeak_headway=120,
    # Coaches cruise quickly but lose time at every stop and at the terminal;
    # 62 km/h is the real point-to-point average on a stopping motorway service.
    speed_kph=62.0,
    dwell_s=180,
    major_dwell_s=600,
    days=(0, 1, 2, 3, 4, 5, 6),
)

_COACH_FARE = FareRule(
    kind="distance",
    base=3.20,
    rate_per_km=0.058,
    cap=48.00,
    offpeak_multiplier=1.0,
    anytime_multiplier=1.0,
    advance_multiplier=0.62,
    day_ticket=None,
    offers_returns=True,
    return_multiplier=1.85,
)

_MEGABUS_FARE = FareRule(
    kind="distance",
    base=1.50,
    rate_per_km=0.040,
    cap=38.00,
    offpeak_multiplier=1.0,
    anytime_multiplier=1.0,
    advance_multiplier=0.70,
    offers_returns=False,
    return_multiplier=1.7,
)

#: Coach interchanges.  NaPTAN publishes some of these as individual stands
#: ("Birmingham Coach Station Stand 8") and some city coach stations sit on the
#: station forecourt, so intercity coaches are anchored on the railway station
#: there -- which is also where the real vehicles stop.
COACH_CORRIDORS: tuple[Corridor, ...] = (
    Corridor(
        code="NX-1",
        operator="NATX",
        mode="coach",
        name="National Express 336: Nottingham - Birmingham",
        regions=("nottingham", "derby", "birmingham"),
        stops=("N:Nottingham Station", "N:Derby Bus Station", "N:Birmingham Coach Station"),
        pattern=_COACH_PATTERN,
        fare=_COACH_FARE,
        weight=1.4,
    ),
    Corridor(
        code="MB-1",
        operator="MEGA",
        mode="coach",
        name="megabus M77: Nottingham - Birmingham",
        regions=("nottingham", "derby", "birmingham"),
        stops=("N:Nottingham Station", "N:Derby Bus Station", "N:Birmingham Coach Station"),
        pattern=ServicePattern(
            first_departure="06:30", last_departure="22:30",
            peak_headway=120, offpeak_headway=180, speed_kph=76.0,
            dwell_s=180, major_dwell_s=540, days=(0, 1, 2, 3, 4, 5, 6),
        ),
        fare=_MEGABUS_FARE,
        weight=1.0,
    ),
    Corridor(
        code="NX-2",
        operator="NATX",
        mode="coach",
        name="National Express 561: Nottingham - London",
        regions=("nottingham", "leicester", "milton-keynes", "london"),
        stops=(
            "N:Nottingham Station", "N:Leicester Rail Station",
            "N:Milton Keynes Coachway", "N:London Victoria Coach Station",
        ),
        pattern=_COACH_PATTERN,
        fare=_COACH_FARE,
        weight=1.3,
    ),
    Corridor(
        code="NX-3",
        operator="NATX",
        mode="coach",
        name="National Express 400: Birmingham - Leeds",
        regions=("birmingham", "sheffield", "leeds"),
        stops=(
            "N:Birmingham Coach Station", "N:Sheffield Interchange",
            "N:Leeds Railway Station",
        ),
        pattern=_COACH_PATTERN,
        fare=_COACH_FARE,
        weight=1.1,
    ),
    Corridor(
        code="NX-4",
        operator="NATX",
        mode="coach",
        name="National Express 422: Birmingham - Manchester",
        regions=("birmingham", "stoke-on-trent", "manchester"),
        stops=(
            "N:Birmingham Coach Station", "R:SOT",
            "N:Manchester Shudehill Interchange",
        ),
        pattern=_COACH_PATTERN,
        fare=_COACH_FARE,
        weight=1.1,
    ),
    Corridor(
        code="MB-2",
        operator="MEGA",
        mode="coach",
        name="megabus M11: Leicester - London",
        regions=("leicester", "london"),
        stops=("N:Leicester Rail Station", "N:London Victoria Coach Station"),
        pattern=ServicePattern(
            first_departure="05:30", last_departure="23:30",
            peak_headway=90, offpeak_headway=120, speed_kph=80.0,
            dwell_s=180, major_dwell_s=420, days=(0, 1, 2, 3, 4, 5, 6),
        ),
        fare=_MEGABUS_FARE,
        weight=1.0,
    ),
    Corridor(
        code="FLX-1",
        operator="FLIX",
        mode="coach",
        name="FlixBus 074: Birmingham - London",
        regions=("birmingham", "coventry", "london"),
        stops=(
            "N:Birmingham Coach Station", "R:COV",
            "N:London Victoria Coach Station",
        ),
        pattern=ServicePattern(
            first_departure="05:45", last_departure="23:45",
            peak_headway=90, offpeak_headway=150, speed_kph=79.0,
            dwell_s=180, major_dwell_s=420, days=(0, 1, 2, 3, 4, 5, 6),
        ),
        fare=_MEGABUS_FARE,
        weight=1.0,
    ),
    Corridor(
        code="NX-5",
        operator="NATX",
        mode="coach",
        name="National Express 310: Sheffield - London",
        regions=("sheffield", "chesterfield", "derby", "leicester", "london"),
        stops=(
            "N:Sheffield Interchange", "R:CHD",
            "N:Derby Bus Station", "N:Leicester Rail Station",
            "N:London Victoria Coach Station",
        ),
        pattern=_COACH_PATTERN,
        fare=_COACH_FARE,
        weight=1.0,
    ),
    Corridor(
        code="NX-6",
        operator="NATX",
        mode="coach",
        name="National Express 592: Manchester - London",
        regions=("manchester", "stockport", "milton-keynes", "london"),
        stops=(
            "N:Manchester Shudehill Interchange", "R:SPT",
            "N:Milton Keynes Coachway", "N:London Victoria Coach Station",
        ),
        pattern=_COACH_PATTERN,
        fare=_COACH_FARE,
        weight=1.0,
    ),
    Corridor(
        code="NX-7",
        operator="NATX",
        mode="coach",
        name="National Express 240: Leeds - Birmingham",
        regions=("leeds", "wakefield", "sheffield", "chesterfield", "birmingham"),
        stops=(
            "N:Leeds Railway Station", "R:WKF",
            "N:Sheffield Interchange", "R:CHD",
            "N:Birmingham Coach Station",
        ),
        pattern=_COACH_PATTERN,
        fare=_COACH_FARE,
        weight=0.9,
    ),
)


# ==========================================================================
# URBAN BUS -- real operators on real corridors
# ==========================================================================

_URBAN_BUS_PATTERN = ServicePattern(
    first_departure="05:30",
    last_departure="23:15",
    peak_headway=10,
    offpeak_headway=15,
    speed_kph=21.0,
    dwell_s=20,
    major_dwell_s=90,
    days=(0, 1, 2, 3, 4, 5, 6),
)

#: Urban bus fares in England are capped nationally.  The cap is a real policy
#: instrument (single journey, any operator, England, outside London).
_ENGLAND_BUS_CAP = 3.00

_URBAN_BUS_FARE = FareRule(
    kind="flat",
    base=_ENGLAND_BUS_CAP,
    rate_per_km=0.0,
    offpeak_multiplier=1.0,
    anytime_multiplier=1.0,
    advance_multiplier=1.0,
    day_cap=_ENGLAND_BUS_CAP * 1.9,
    day_ticket=_ENGLAND_BUS_CAP * 1.6,
    offers_returns=False,
    return_multiplier=1.9,
    transfer_window_min=0,
)

#: London buses are a flat TfL fare with a daily cap.
_LONDON_BUS_FARE = FareRule(
    kind="flat",
    base=1.75,
    rate_per_km=0.0,
    offpeak_multiplier=1.0,
    anytime_multiplier=1.0,
    advance_multiplier=1.0,
    day_cap=5.25,
    day_ticket=5.25,
    offers_returns=False,
    return_multiplier=2.0,
    transfer_window_min=60,
)


def _bus(
    code: str,
    operator: str,
    name: str,
    stops: tuple[str, ...],
    *,
    headway: int = 10,
    speed: float = 21.0,
    weight: float = 1.0,
    fare: FareRule | None = None,
) -> Corridor:
    return Corridor(
        code=code,
        operator=operator,
        mode="bus",
        name=name,
        stops=stops,
        pattern=ServicePattern(
            first_departure="05:30",
            last_departure="23:15",
            peak_headway=headway,
            offpeak_headway=int(headway * 1.5),
            speed_kph=speed,
            dwell_s=20,
            major_dwell_s=90,
            days=(0, 1, 2, 3, 4, 5, 6),
        ),
        fare=fare or _URBAN_BUS_FARE,
        weight=weight,
    )


BUS_CORRIDORS: tuple[Corridor, ...] = (
    # --- Nottingham City Transport -----------------------------------------
    _bus("NCT-1", "NCT", "NCT Navy 1: Nottingham - Clifton", (
        "N:Victoria Centre", "N:Old Market Square", "N:Collin Street",
        "N:Nottingham Station", "N:Wilford Lane", "N:Compton Acres",
        "N:Ruddington Lane",
    ), headway=7, weight=1.2),
    _bus("NCT-2", "NCT", "NCT Green 10: Nottingham - Ruddington", (
        "N:Victoria Centre", "N:Old Market Square", "N:Nottingham Station",
        "N:Wilford Lane", "N:Ruddington Lane",
    ), headway=10),
    _bus("NCT-3", "NCT", "NCT Pink 28: Nottingham - Carlton", (
        "N:Victoria Centre", "N:Upper Parliament Street", "N:Mansfield Road",
        "N:Carlton Carlton Hill", "N:Carlton Cavendish Road",
        "N:Carlton Burton Road", "N:Gedling Road", "N:Gedling Westdale Lane",
    ), headway=8, weight=1.1),
    _bus("NCT-4", "NCT", "NCT Brown 15: Nottingham - Arnold", (
        "N:Nottingham Station", "N:Victoria Centre", "N:Mansfield Road",
        "N:Daybrook Square", "N:Arnold Library",
    ), headway=10),
    _bus("NCT-5", "NCT", "NCT Yellow 36: Nottingham - Bulwell", (
        "N:Old Market Square", "N:Upper Parliament Street", "N:Parliament Street",
        "N:Mansfield Road", "N:Musters Road",
    ), headway=10),
    _bus("NCT-6", "NCT", "NCT Lilac 25: Nottingham - Beeston", (
        "N:Old Market Square", "N:Nottingham Station", "N:Queen Street",
        "N:Canal Street", "N:Meadows",
    ), headway=12, speed=24.0),
    _bus("TB-1", "TBTN", "trentbarton indigo: Nottingham - Derby", (
        "N:Nottingham Station", "N:Queen Street", "R:BEE",
        "R:LGE", "N:Derby Bus Station",
    ), headway=15, speed=28.0, weight=1.3),
    _bus("TB-2", "TBTN", "trentbarton red arrow: Nottingham - Derby", (
        "N:Victoria Centre", "N:Nottingham Station", "N:Derby Bus Station",
    ), headway=20, speed=34.0, weight=1.2),
    _bus("TB-3", "TBTN", "trentbarton the two: Nottingham - Ilkeston", (
        "N:Old Market Square", "N:Nottingham Station", "N:Queen Street",
        "R:BEE",
    ), headway=20, speed=26.0),
    _bus("TB-4", "TBTN", "trentbarton rainbow one: Nottingham - Eastwood", (
        "N:Victoria Centre", "N:Old Market Square", "N:Upper Parliament Street",
        "N:Mansfield Road", "N:Daybrook Square",
    ), headway=15, speed=24.0),
    # --- Derby ---------------------------------------------------------------
    _bus("DBY-1", "ARRL", "Arriva Derby: Derby - Chellaston", (
        "N:Derby Bus Station", "N:Morledge", "N:Corporation Street",
        "N:Full Street", "N:Albert Street",
    ), headway=12),
    _bus("DBY-2", "ARRL", "Arriva Derby: Derby - Mackworth", (
        "N:Derby Bus Station", "N:Wardwick", "N:Victoria Street",
        "N:Markeaton Lane South",
    ), headway=12),
    _bus("DBY-3", "TBTN", "trentbarton comet: Derby - Nottingham", (
        "N:Derby Bus Station", "N:Morledge", "R:LGE",
        "R:BEE", "N:Nottingham Station",
    ), headway=20, speed=30.0),
    # --- Birmingham (National Express West Midlands) ------------------------
    _bus("NXWM-1", "NXWM", "NXWM 9: Birmingham - Coleshill", (
        "N:Birmingham Coach Station", "N:Coleshill Parkway Station",
    ), headway=15),
    _bus("NXWM-2", "NXWM", "NXWM 97: Birmingham - Airport", (
        "N:Birmingham Coach Station", "N:Navigation Street (Travelling South East)",
        "N:Birmingham Airport Skytrain",
    ), headway=12, speed=24.0),
    _bus("NXWM-3", "NXWM", "NXWM 16: Birmingham - Hockley", (
        "N:Birmingham Coach Station", "N:HIGH STREET Stop Dj",
        "N:NEWTOWN ROW, Clements Arms/Lower Tower St",
        "N:HOCKLEY HILL, Key Hill/Great King Street",
        "N:SOHO HILL, Hockley Circus/TWM Garage A B C",
    ), headway=10, speed=20.0),
    _bus("NXWM-4", "NXWM", "NXWM 74: Birmingham - Perry Barr", (
        "N:Birmingham Coach Station", "N:COLMORE ROW Aa>Ae, Birmingham",
        "N:BULL STREET Ba>Bg, Birmingham",
        "N:CONSTITUTION HILL, St Paul`s Metro Stop",
        "N:BIRCHFIELD RD, U.C.E/Perry Barr Station Bridge",
    ), headway=10, speed=20.0),
    # --- Leicester -----------------------------------------------------------
    _bus("LEI-1", "ARRL", "Arriva Leicester: Haymarket - Beaumont Leys", (
        "N:Haymarket", "N:Abbey Lane", "N:Beaumont Leys Lane",
        "N:Leycroft Road",
    ), headway=10),
    _bus("LEI-2", "ARRL", "Arriva Leicester: City - Narborough Road", (
        "N:Haymarket", "N:Regent Road", "N:Narborough Road",
        "N:Braunstone Avenue",
    ), headway=10),
    _bus("LEI-3", "ARRL", "Arriva Leicester: City - Glenfield Hospital", (
        "N:Haymarket", "N:Coleman Road", "N:Glenfield General Hospital",
    ), headway=12),
    _bus("LEI-4", "SCEM", "Stagecoach Leicester: City - Saffron Lane", (
        "N:Haymarket", "N:Clarendon Park Road", "N:Saffron Lane",
        "N:Spencefield Lane",
    ), headway=12),
    _bus("LEI-5", "SCEM", "Stagecoach Leicester: City - Evington", (
        "N:Haymarket", "N:London Road", "N:Welford Road",
        "N:Dysart Way", "N:The Exchange",
    ), headway=12),
    # --- Sheffield -----------------------------------------------------------
    _bus("SHF-1", "SCSY", "Stagecoach Sheffield: Interchange - Meadowhall", (
        "N:Sheffield Interchange", "N:Valley Centertainment",
        "N:Meadowhall Road, Meadow Bank Road",
    ), headway=10, speed=22.0),
    _bus("SHF-2", "FHLD", "First Sheffield: City - Hillsborough", (
        "N:Sheffield Interchange", "N:City Road, Wulfric Road",
        "N:Penistone Road, Hillsborough Park",
        "N:Middlewood Road, Withens Avenue",
    ), headway=10),
    _bus("SHF-3", "FHLD", "First Sheffield: City - Ecclesfield", (
        "N:Sheffield Interchange", "N:Pitsmoor Road, Pye Bank Road",
        "N:Ecclesfield Road, Bellhouse Road",
    ), headway=12),
    _bus("SHF-4", "SCSY", "Stagecoach Sheffield: City - Fulwood", (
        "N:Sheffield Interchange", "N:East Bank Road, Norfolk Park Road",
        "N:Fulwood Road, Stumperlowe Avenue",
    ), headway=15),
    # --- Leeds ---------------------------------------------------------------
    _bus("LDS-1", "FLDS", "First Leeds: City - Headingley", (
        "N:Leeds Railway Station", "N:Vicar Lane",
        "N:Boar Lane, At Mill Hill, Opp Leeds Shopping Plaz",
        "N:Woodhouse Street Delph Ln", "N:Belle Vue Road Woodsley Rd",
        "N:Gledhow Valley Road",
    ), headway=8, weight=1.1),
    _bus("LDS-2", "FLDS", "First Leeds: City - Pudsey", (
        "N:Leeds Railway Station", "N:Wellington Street", "N:Tong Road",
        "N:Roker Lane - Pudsey",
    ), headway=12),
    _bus("LDS-3", "ARRY", "Arriva Yorkshire: City - Horsforth", (
        "N:Leeds Railway Station", "N:Eastgate", "N:The Headrow",
        "N:King Edward Avenue - Horsforth",
    ), headway=12),
    _bus("LDS-4", "FLDS", "First Leeds: City - Cross Gates", (
        "N:Leeds Railway Station", "N:York Road", "N:Selby Road",
        "N:Harrogate Road",
    ), headway=12),
    # --- Manchester ----------------------------------------------------------
    _bus("MAN-1", "SCMN", "Stagecoach Manchester: Piccadilly - Didsbury", (
        "N:Piccadilly", "N:St Peter's Square", "N:Deansgate-Castlefield",
        "N:St Werburgh's Road", "N:Withington", "N:West Didsbury",
        "N:East Didsbury",
    ), headway=8, speed=22.0, weight=1.1),
    _bus("MAN-2", "FMAN", "First Manchester: Piccadilly - Oldham", (
        "N:Piccadilly", "N:Shudehill", "N:Victoria", "N:Monsall",
        "N:Newton Heath & Moston", "N:Failsworth", "N:Oldham Central",
        "N:Oldham Mumps",
    ), headway=10, speed=23.0),
    _bus("MAN-3", "SCMN", "Stagecoach Manchester: City - Bury", (
        "N:Victoria", "N:Shudehill", "N:Crumpsall", "N:Bowker Vale",
        "N:Abraham Moss", "N:Prestwich", "N:Whitefield", "N:Bury",
    ), headway=12, speed=24.0),
    # --- London --------------------------------------------------------------
    _bus("TFL-B1", "TFLBUS", "London Buses 24: Pimlico - Camden Town", (
        "N:Victoria", "N:Westminster", "N:Tottenham Court Road",
        "N:Chalk Farm",
    ), headway=6, speed=17.0, fare=_LONDON_BUS_FARE, weight=1.1),
    _bus("TFL-B2", "TFLBUS", "London Buses 11: Victoria - Liverpool Street", (
        "N:Victoria", "N:Westminster", "N:St Paul's",
        "N:Liverpool Street",
    ), headway=7, speed=16.0, fare=_LONDON_BUS_FARE, weight=1.0),
    _bus("TFL-B3", "TFLBUS", "London Buses 73: St Pancras - Oxford Circus", (
        "N:Kings Cross St Pancras", "N:St Pancras International",
        "N:Russell Square", "N:Oxford Circus",
    ), headway=6, speed=16.0, fare=_LONDON_BUS_FARE, weight=1.0),
    _bus("TFL-B4", "TFLBUS", "London Buses 25: Holborn - Stratford", (
        "N:Holborn Circus", "N:Liverpool Street", "N:Whitechapel",
        "N:Mile End", "N:Stratford",
    ), headway=6, speed=15.0, fare=_LONDON_BUS_FARE, weight=1.0),
    _bus("TFL-B5", "TFLBUS", "London Buses 38: Victoria - Seven Sisters", (
        "N:Victoria", "N:Green Park", "N:Oxford Circus / Oxford Street",
        "N:Blackhorse Road", "N:Seven Sisters",
    ), headway=7, speed=15.0, fare=_LONDON_BUS_FARE, weight=1.0),
    # The rail terminals have to connect into the West End, or every train into
    # Euston dead-ends there.  These two are the real 73 and 68.
    _bus("TFL-B6", "TFLBUS", "London Buses 73: Euston - Oxford Circus", (
        "N:Euston", "N:Warren Street", "N:Goodge Street",
        "N:Tottenham Court Road-Entrance-4", "N:Oxford Circus / Oxford Street",
    ), headway=6, speed=14.0, fare=_LONDON_BUS_FARE, weight=1.0),
    _bus("TFL-B7", "TFLBUS", "London Buses 68: Euston - Embankment", (
        "N:Euston", "N:Russell Square", "N:Holborn Circus",
        "N:Charing Cross-Underground-1", "N:Embankment-Underground-1",
    ), headway=7, speed=14.0, fare=_LONDON_BUS_FARE, weight=1.0),
    # --- Milton Keynes / Coventry / Wolverhampton ---------------------------
    _bus("MKC-1", "ARRL", "Arriva Milton Keynes: Central - Coachway", (
        "N:Milton Keynes Central (rail station)", "N:Milton Keynes Coachway",
    ), headway=20, speed=24.0),
    _bus("COV-1", "NXWM", "NX Coventry: City - Bedworth", (
        "N:TRINITY STREET, Holy Trinity Church", "N:BURGES, Ironmonger Row",
        "N:NUNTS LANE, Rookery Lane", "N:BEDWORTH RD, Oban Rd/Canal Boat",
    ), headway=12),
    _bus("COV-2", "NXWM", "NX Coventry: City - Keresley", (
        "N:TRINITY STREET, Holy Trinity Church", "N:SPON END, Butts/Coventry",
        "N:CHARITY RD, Keresley Village",
    ), headway=15),
    _bus("WOL-1", "NXWM", "NX Wolverhampton: City - Bilbrook", (
        "N:VICTORIA STREET, Salop Street", "N:THE PARKWAY, Richmond Drive",
        "N:BILBROOK STATION,Duck Lane",
        "N:DUCK LANE,Bilbrook/Wolverhampton Rd",
    ), headway=15),
)


ALL_CORRIDORS: tuple[Corridor, ...] = (
    RAIL_CORRIDORS + TRAM_CORRIDORS + LONDON_CORRIDORS + COACH_CORRIDORS + BUS_CORRIDORS
)


#: Canonical corridor stop name -> the exact real stop name it refers to.
#:
#: These are genuine naming differences, not approximations: NaPTAN enumerates
#: London Underground nodes with node suffixes and spells ``St Pancras`` as
#: ``St.Pancras``; a few interchanges are published under a shorter name than
#: the one locals use.  Every value below is a real stop name that exists in
#: the bundled NaPTAN inventory.
STOP_ALIASES: dict[str, str] = {
    "Kings Cross St Pancras": "Kings Cross St.Pancras",
    "Heathrow Terminals 2 & 3": "Heathrow Terminals 1-2-3",
    "St John's Wood": "St.John's Wood",
    "St Paul's": "St.Paul's Station",
    "London Victoria Coach Station": "Victoria Coach Station",
    "Manchester Shudehill Interchange": "Shudehill",
}


def corridors_by_code() -> dict[str, Corridor]:
    return {c.code: c for c in ALL_CORRIDORS}


def corridors_by_mode() -> dict[str, list[Corridor]]:
    out: dict[str, list[Corridor]] = {}
    for c in ALL_CORRIDORS:
        out.setdefault(c.mode, []).append(c)
    return out
