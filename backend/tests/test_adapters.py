"""Tests for the live-feed adapters.

These are the parts of MoveIn that talk to services this environment cannot
reach.  The network calls are untestable here, so the tests are written against
the parts that would silently corrupt the product if they broke: the parsers.
Every fixture below is a cut-down copy of a real published payload.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.domain.models import Mode
from backend.app.ingest.bods import (
    BodsClient,
    mode_for_vehicle,
    parse_siri_vm,
    parse_transxchange_routes,
)
from backend.app.ingest.nptg import (
    parse_adjacent_localities,
    parse_admin_areas,
    parse_localities,
)
from backend.app.ingest.osm import detour_factor, overpass_query, parse_overpass
from backend.app.ingest.tfl import (
    parse_line_status,
    parse_route_sequence,
    parse_stop_point,
)
from backend.app.services.realtime import from_siri_vm

# --- BODS: SIRI-VM ---------------------------------------------------------

SIRI_VM = """<?xml version="1.0" encoding="UTF-8"?>
<Siri xmlns="http://www.siri.org.uk/siri" version="2.0">
 <ServiceDelivery>
  <ResponseTimestamp>2026-10-07T09:15:00Z</ResponseTimestamp>
  <VehicleMonitoringDelivery>
   <ResponseTimestamp>2026-10-07T09:15:00Z</ResponseTimestamp>
   <VehicleActivity>
    <RecordedAtTime>2026-10-07T09:14:32+01:00</RecordedAtTime>
    <ValidUntilTime>2026-10-07T09:16:00Z</ValidUntilTime>
    <MonitoredVehicleJourney>
     <LineRef>NCT-34</LineRef>
     <PublishedLineName>34</PublishedLineName>
     <DirectionRef>outbound</DirectionRef>
     <OperatorRef>NCTR</OperatorRef>
     <DestinationRef>naptan:nottingham:bulwell</DestinationRef>
     <DestinationName>Bulwell</DestinationName>
     <FramedVehicleJourneyRef>
      <DataFrameRef>2026-10-07</DataFrameRef>
      <DatedVehicleJourneyRef>NCT-34:2026-10-07:0940</DatedVehicleJourneyRef>
     </FramedVehicleJourneyRef>
     <VehicleLocation>
      <Longitude>-1.15063</Longitude>
      <Latitude>52.95360</Latitude>
     </VehicleLocation>
     <Bearing>312.0</Bearing>
     <Velocity>8.33</Velocity>
     <Occupancy>seatedAvailable</Occupancy>
     <Delay>PT2M30S</Delay>
     <Monitored>true</Monitored>
     <MonitoredCall>
      <StopPointRef>naptan:nottingham:old-market</StopPointRef>
      <StopPointName>Old Market Square</StopPointName>
      <ExpectedDepartureTime>2026-10-07T09:16:00+01:00</ExpectedDepartureTime>
     </MonitoredCall>
    </MonitoredVehicleJourney>
    <VehicleRef>NCT-8812</VehicleRef>
   </VehicleActivity>
   <VehicleActivity>
    <RecordedAtTime>2026-10-07T09:14:40Z</RecordedAtTime>
    <MonitoredVehicleJourney>
     <LineRef>MB-1</LineRef>
     <PublishedLineName>M1</PublishedLineName>
     <OperatorRef>MEGA</OperatorRef>
     <FramedVehicleJourneyRef>
      <DatedVehicleJourneyRef>MB-1:2026-10-07:0900</DatedVehicleJourneyRef>
     </FramedVehicleJourneyRef>
     <VehicleLocation>
      <Longitude>-1.2</Longitude>
      <Latitude>52.9</Latitude>
     </VehicleLocation>
     <Delay>-PT45S</Delay>
     <Monitored>true</Monitored>
    </MonitoredVehicleJourney>
    <VehicleRef>MG-4477</VehicleRef>
   </VehicleActivity>
   <VehicleActivity>
    <RecordedAtTime>2026-10-07T09:14:44Z</RecordedAtTime>
    <MonitoredVehicleJourney>
     <LineRef>NX-7</LineRef>
     <VehicleRef>NX-0001</VehicleRef>
     <VehicleLocation>
      <Longitude>NaN</Longitude>
      <Latitude>NaN</Latitude>
     </VehicleLocation>
    </MonitoredVehicleJourney>
   </VehicleActivity>
  </VehicleMonitoringDelivery>
 </ServiceDelivery>
</Siri>
"""


def test_siri_vm_parses_real_vehicle_activity():
    records = parse_siri_vm(SIRI_VM)
    # The third vehicle has no position fix and is dropped, not placed at 0,0.
    assert len(records) == 2

    nct = records[0]
    assert nct["vehicle_id"] == "NCT-8812"
    assert nct["trip_id"] == "NCT-34:2026-10-07:0940"
    assert nct["route_id"] == "NCT-34"
    assert nct["operator_code"] == "NCTR"
    assert nct["lat"] == pytest.approx(52.95360)
    assert nct["lon"] == pytest.approx(-1.15063)
    assert nct["bearing"] == pytest.approx(312.0)
    assert nct["speed_mps"] == pytest.approx(8.33)
    assert nct["delay_s"] == 150, "PT2M30S is two and a half minutes late"
    assert nct["next_stop_id"] == "naptan:nottingham:old-market"
    assert nct["next_stop_name"] == "Old Market Square"
    assert nct["occupancy"] == "seatedAvailable"
    assert nct["monitored"] is True
    # Timezones are normalised to local time, as the timetable is.
    assert nct["recorded_at"].tzinfo is None
    assert nct["recorded_at"].hour == 9


def test_siri_vm_handles_negative_delays():
    """A bus ahead of schedule is not the same as a bus with no delay data."""
    mega = parse_siri_vm(SIRI_VM)[1]
    assert mega["delay_s"] == -45


def test_siri_vm_speed_is_not_double_converted():
    """Publishers disagree on units; a bus at 8 m/s must not become 2 m/s."""
    nct = parse_siri_vm(SIRI_VM)[0]
    assert 5 < nct["speed_mps"] < 15


def test_siri_vm_records_become_vehicles(planner):
    vehicles = from_siri_vm(parse_siri_vm(SIRI_VM), net=planner.net)
    # NCT-34 is not in the modelled network, so only vehicles MoveIn can place
    # on a line come through.
    assert all(v.trip_id in planner.net.trips or not v.trip_id for v in vehicles)
    for vehicle in vehicles:
        assert vehicle.source == "siri-vm"
        assert -90 <= vehicle.lat <= 90 and -180 <= vehicle.lon <= 180
        assert vehicle.as_dict()["source"] == "siri-vm"


def test_transxchange_route_identity_is_extracted():
    document = """<?xml version="1.0"?>
    <TransXChange xmlns="http://www.transxchange.org.uk/" version="2.4">
      <Operators>
        <Operator id="O1">
          <NationalOperatorCode>NCTR</NationalOperatorCode>
          <OperatorShortName>Nottingham City Transport</OperatorShortName>
        </Operator>
      </Operators>
      <Routes>
        <Route id="R34">
          <Description>Nottingham to Bulwell</Description>
          <LineName>34</LineName>
        </Route>
      </Routes>
    </TransXChange>"""
    routes = parse_transxchange_routes(document)
    assert routes and routes[0]["line_name"] == "34"
    assert routes[0]["route_id"] == "R34"
    assert routes[0]["operator_codes"] == ["NCTR"]


def test_bods_client_carries_the_key_in_a_bearer_header():
    client = BodsClient(api_key="secret")
    assert client._headers() == {"Authorization": "bearer secret"}
    assert BodsClient(api_key="")._headers() == {}


def test_vehicle_mode_is_read_from_the_line():
    assert mode_for_vehicle("NCT-34") is Mode.BUS
    assert mode_for_vehicle("MB-1", "M1") is Mode.BUS
    assert mode_for_vehicle("NX-7", "National Express 7") is Mode.COACH


# --- TfL -------------------------------------------------------------------

TFL_STOP = {
    "id": "940GZZLUPCC",
    "naptanId": "940GZZLUPCC",
    "commonName": "Piccadilly Circus Underground Station",
    "lat": 51.509861,
    "lon": -0.134031,
    "modes": ["tube"],
    "zone": "1",
    "stopType": "CompactStation",
    "additionalProperties": [
        {"key": "StepFreeAccess", "value": "true"},
        {"key": "Towards", "value": "Piccadilly"},
    ],
}


def test_tfl_stop_point_is_read_as_a_stop():
    stop = parse_stop_point(TFL_STOP)
    assert stop["id"] == "940GZZLUPCC"
    assert stop["name"] == "Piccadilly Circus Underground Station"
    assert stop["lat"] == pytest.approx(51.509861)
    assert stop["modes"] == ["metro"]
    assert stop["step_free"] is True
    assert stop["zone"] == "1"


def test_tfl_route_sequence_keeps_order_and_drops_repeats():
    payload = {
        "stopPointSequences": [
            {
                "stopPoint": [
                    {"id": "A"}, {"id": "B"}, {"id": "C"},
                ]
            },
            {
                "stopPoint": [
                    {"id": "B"}, {"id": "C"}, {"id": "D"},
                ]
            },
        ]
    }
    assert parse_route_sequence(payload) == ["A", "B", "C", "D"]


def test_tfl_line_status_severity_is_graded():
    good = parse_line_status(
        {"id": "piccadilly", "name": "Piccadilly", "lineStatuses": [{"statusSeverity": 10}]}
    )
    assert good["severity"] == "info"
    bad = parse_line_status(
        {
            "id": "piccadilly",
            "name": "Piccadilly",
            "lineStatuses": [
                {"statusSeverity": 4, "reason": "Signal failure at Acton Town"}
            ],
        }
    )
    assert bad["severity"] == "severe"
    assert "Signal failure" in bad["reason"]


# --- NPTG ------------------------------------------------------------------

NPTG_LOCALITIES = """LocalityCode,LocalityName,NptgDistrictCode,DistrictName,AdministrativeAreaCode,AdministrativeAreaName,LocalityType,Latitude,Longitude
E00280000,Nottingham,E07000000,Nottingham,E06000018,Nottingham UA,Locality,52.95360,-1.15063
E00290000,Beeston,E07000000,Broxtowe,E06000018,Nottinghamshire,Settlement,52.92580,-1.21520
E00300000,Long Eaton,E07000000,Erewash,E06000008,Derbyshire,Settlement,52.89800,-1.27100
E00300001,Nowhere,E07000000,Erewash,E06000008,Derbyshire,Settlement,NA,NA
"""


def test_nptg_localities_parse_and_skip_missing_coordinates():
    localities = parse_localities(NPTG_LOCALITIES)
    assert set(localities) == {"E00280000", "E00290000", "E00300000"}
    assert localities["E00280000"].name == "Nottingham"
    assert localities["E00300000"].lat == pytest.approx(52.898)
    assert localities["E00300000"].slug == "long-eaton"


def test_nptg_adjacency_and_admin_areas():
    adjacent = parse_adjacent_localities(
        "LocalityCode,AdjacentLocalityCode\nE00300000,E00280000\nE00280000,E00300000\n"
    )
    assert adjacent["E00300000"] == {"E00280000"}
    areas = parse_admin_areas(
        "AdministrativeAreaCode,AdministrativeAreaName\nE06000018,Nottingham UA\n"
    )
    assert areas["E06000018"] == "Nottingham UA"


# --- OSM / Overpass --------------------------------------------------------

OVERPASS_PAYLOAD = {
    "elements": [
        {
            "type": "way",
            "id": 1,
            "geometry": [
                {"lat": 52.9536, "lon": -1.1506},
                {"lat": 52.9539, "lon": -1.1501},
                {"lat": 52.9542, "lon": -1.1496},
            ],
        },
        {"type": "node", "id": 2, "lat": 52.95, "lon": -1.15},
        {"type": "way", "id": 3, "geometry": [{"lat": 52.95, "lon": -1.15}]},
    ]
}


def test_overpass_keeps_walkable_ways_and_drops_stray_nodes():
    network = parse_overpass(OVERPASS_PAYLOAD)
    assert len(network.ways) == 1, "a one-node way is not a walk"
    assert network.segments == 2
    assert 80 < network.length_m() < 120


def test_overpass_query_asks_for_walkable_ways_in_a_radius():
    query = overpass_query(52.95, -1.15, radius_m=800)
    assert "around:800,52.95,-1.15" in query
    assert "out geom" in query
    assert "footway" in query and "path" in query


def test_detour_factor_stays_plausible():
    network = parse_overpass(OVERPASS_PAYLOAD)
    # A degenerate input must not produce an infinite walk.
    assert 1.0 <= detour_factor(network, 0) <= 2.5
    assert 1.0 <= detour_factor(network, 400) <= 2.5
