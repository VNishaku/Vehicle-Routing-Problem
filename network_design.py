"""Reproducible data audit for the regional crossdock network-design exercise.

This script deliberately does not emit an optimized network when required
operational inputs are missing. It produces validated demand/network extracts
and a readiness report so that a solver cannot silently invent constraints.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Iterator

from openpyxl import load_workbook


FILES = {
    "connections": "AllConnections.xlsx",
    "demand": "OD_Demand_Data.xlsx",
    "regional": "Regional_Data.xlsx",
    "vehicles": "Vehicle_Data.xlsx",
    "coordinates": "lat_long.csv",
}


def iter_sheet(path: Path, sheet_name: str) -> Iterator[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook[sheet_name]
        rows = worksheet.iter_rows(values_only=True)
        header_row = next(rows)
        headers = [
            str(value).strip() if value is not None else f"unnamed_{index}"
            for index, value in enumerate(header_row)
        ]
        for row in rows:
            if not row or not any(value is not None for value in row):
                continue
            yield {
                headers[index]: row[index] if index < len(row) else None
                for index in range(len(headers))
            }
    finally:
        workbook.close()


def number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    return str(value).strip()


def quantile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (
        position - lower
    )


def parse_clock(value: Any) -> bool:
    if isinstance(value, time):
        return True
    text = as_text(value)
    if not text:
        return False
    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            datetime.strptime(text, pattern)
            return True
        except ValueError:
            pass
    return False


def read_coordinates(path: Path) -> tuple[dict[str, tuple[float, float]], int]:
    coordinates: dict[str, tuple[float, float]] = {}
    duplicates = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            name = (row.get("hubname") or "").strip()
            try:
                latitude = float(row.get("latitude2", ""))
                longitude = float(row.get("longitude2", ""))
            except (TypeError, ValueError):
                continue
            if not name or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                continue
            if name in coordinates:
                duplicates += 1
            coordinates[name] = (latitude, longitude)
    return coordinates, duplicates


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_map(
    path: Path,
    coordinates: dict[str, tuple[float, float]],
    candidates: set[str],
    assignments: list[dict[str, Any]],
) -> None:
    station_names = {
        row["delivery_station"]
        for row in assignments
        if row["delivery_station"] in coordinates
    }
    parent_names = {
        row["current_parent"]
        for row in assignments
        if row["current_parent"] in coordinates
    }
    names = station_names | parent_names | (candidates & coordinates.keys())
    if not names:
        path.write_text("<!doctype html><title>No coordinates</title>", encoding="utf-8")
        return

    width, height, padding = 1000, 660, 45
    latitudes = [coordinates[name][0] for name in names]
    longitudes = [coordinates[name][1] for name in names]
    min_lat, max_lat = min(latitudes), max(latitudes)
    min_lon, max_lon = min(longitudes), max(longitudes)
    lat_span = max(max_lat - min_lat, 0.01)
    lon_span = max(max_lon - min_lon, 0.01)
    def point(name: str) -> tuple[float, float]:
        latitude, longitude = coordinates[name]
        x = padding + (longitude - min_lon) / lon_span * (width - 2 * padding)
        y = height - padding - (latitude - min_lat) / lat_span * (height - 2 * padding)
        return x, y

    lines: list[str] = []
    for row in assignments:
        station = row["delivery_station"]
        parent = row["current_parent"]
        if station in coordinates and parent in coordinates:
            x1, y1 = point(parent)
            x2, y2 = point(station)
            lines.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                f'y2="{y2:.1f}" stroke="#a8b3c2" stroke-width="0.65" '
                f'opacity="0.45"><title>{html.escape(parent)} to '
                f'{html.escape(station)}</title></line>'
            )

    circles: list[str] = []
    for name in sorted(names):
        x, y = point(name)
        if name in candidates:
            circles.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#174ea6" '
                f'stroke="white" stroke-width="1.5"><title>Candidate crossdock: '
                f'{html.escape(name)}</title></circle>'
            )
            circles.append(
                f'<text x="{x + 8:.1f}" y="{y - 7:.1f}" class="label">'
                f'{html.escape(name)}</text>'
            )
        elif name in parent_names:
            circles.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="#188038" '
                f'stroke="white" stroke-width="1"><title>Current parent: '
                f'{html.escape(name)}</title></circle>'
            )
        else:
            circles.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.7" fill="#e37400" '
                f'opacity="0.8"><title>Delivery station: '
                f'{html.escape(name)}</title></circle>'
            )
    html_text = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>Current network — coordinate coverage</title>
<style>
body{{font:14px Segoe UI,Arial,sans-serif;margin:20px;color:#202124}}
svg{{width:min(100%,1100px);height:auto;border:1px solid #dadce0;background:#f8f9fa}}
.label{{font-size:10px;fill:#174ea6}} .legend{{margin:8px 0;color:#5f6368}}
</style>
<h1>Current network — geocoded nodes only</h1>
<p class="legend">Blue: candidate crossdock origins · Green: other current parents ·
Orange: geocoded delivery stations ·
Grey lines: current parent-to-station links where both ends have coordinates.
This is a longitude/latitude plot, not a road map or proposed design.</p>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Coordinate plot">
{"".join(lines)}{"".join(circles)}
</svg>
<p>Shows {len(station_names)} of {len(assignments)} delivery stations with coordinates.
Unlocated stations and any route/schedule feasibility are not represented.</p>
</html>"""
    path.write_text(html_text, encoding="utf-8")


def run(data_dir: Path, output_dir: Path) -> dict[str, Any]:
    for filename in FILES.values():
        if not (data_dir / filename).is_file():
            raise FileNotFoundError(f"Required input file not found: {data_dir / filename}")
    output_dir.mkdir(parents=True, exist_ok=True)

    coordinates, duplicate_coordinates = read_coordinates(data_dir / FILES["coordinates"])

    candidate_routes: Counter[str] = Counter()
    candidate_tiers: dict[str, set[str]] = defaultdict(set)
    for row in iter_sheet(data_dir / FILES["connections"], "connection"):
        source = as_text(row.get("Source Hub Name"))
        tier = as_text(row.get("LZN"))
        if source and tier == "Milkrun":
            candidate_routes[source] += 1
            candidate_tiers[source].add(tier)
    candidates = set(candidate_routes)

    demand_sheet = "B2C Landing"
    daily: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    parents: dict[str, set[str]] = defaultdict(set)
    dates: set[str] = set()
    invalid_demand_rows = 0
    demand_rows = 0
    total_demand = [0.0, 0.0, 0.0]
    for row in iter_sheet(data_dir / FILES["demand"], demand_sheet):
        demand_rows += 1
        station = as_text(row.get("lm_hubname"))
        demand_date = as_text(row.get("raddate"))
        if not station or not demand_date:
            invalid_demand_rows += 1
            continue
        dates.add(demand_date)
        parent = as_text(row.get("lm_parent_hubname"))
        if parent:
            parents[station].add(parent)
        values = [
            number(row.get("phyweight")),
            number(row.get("volweight")),
            number(row.get("shipment_count")),
        ]
        totals = daily[(station, demand_date)]
        for index, value in enumerate(values):
            totals[index] += value
            total_demand[index] += value

    observed_dates = sorted(dates)
    stations = sorted({station for station, _ in daily})
    station_rows: list[dict[str, Any]] = []
    assignment_rows: list[dict[str, Any]] = []
    for station in stations:
        station_days = [
            daily.get((station, day), [0.0, 0.0, 0.0])
            for day in observed_dates
        ]
        means = [
            statistics.mean(day_values[index] for day_values in station_days)
            if station_days
            else 0.0
            for index in range(3)
        ]
        p90 = [quantile([day[index] for day in station_days], 0.90) for index in range(3)]
        p95 = [quantile([day[index] for day in station_days], 0.95) for index in range(3)]
        station_parents = sorted(parents.get(station, set()))
        parent = station_parents[0] if len(station_parents) == 1 else ""
        station_rows.append(
            {
                "delivery_station": station,
                "current_parent": parent,
                "parent_count": len(station_parents),
                "active_days": sum(
                    1 for values in station_days if any(value > 0 for value in values)
                ),
                "observed_calendar_days": len(observed_dates),
                "mean_daily_phyweight": round(means[0], 3),
                "p90_daily_phyweight": round(p90[0], 3),
                "p95_daily_phyweight": round(p95[0], 3),
                "mean_daily_volweight": round(means[1], 3),
                "p90_daily_volweight": round(p90[1], 3),
                "p95_daily_volweight": round(p95[1], 3),
                "mean_daily_shipments": round(means[2], 3),
                "p90_daily_shipments": round(p90[2], 3),
                "p95_daily_shipments": round(p95[2], 3),
                "has_coordinates": station in coordinates,
            }
        )
        assignment_rows.append(
            {
                "delivery_station": station,
                "current_parent": parent,
                "parent_count": len(station_parents),
                "parent_values": "|".join(station_parents),
                "has_coordinates": station in coordinates,
                "mean_daily_phyweight": round(means[0], 3),
                "mean_daily_volweight": round(means[1], 3),
                "mean_daily_shipments": round(means[2], 3),
            }
        )

    write_csv(
        output_dir / "station_demand.csv",
        station_rows,
        list(station_rows[0]) if station_rows else ["delivery_station"],
    )
    write_csv(
        output_dir / "current_assignments.csv",
        assignment_rows,
        list(assignment_rows[0]) if assignment_rows else ["delivery_station"],
    )

    cutoff_rows = list(
        iter_sheet(data_dir / FILES["regional"], "Connecting hub_earliest cutoff")
    )
    timed_departure_rows = list(
        iter_sheet(data_dir / FILES["regional"], "Coonection timings")
    )
    vehicle_rows = list(iter_sheet(data_dir / FILES["vehicles"], "Per Day Cost"))
    compatibility_rows = list(iter_sheet(data_dir / FILES["vehicles"], "Vehicle Node Map"))
    nonblank_compatibility = [
        row for row in compatibility_rows if as_text(row.get("vehicle_type"))
    ]
    unique_parents = {
        parent for station_parents in parents.values() for parent in station_parents
    }
    current_parent_counts = Counter(
        parent
        for station_parents in parents.values()
        for parent in station_parents
    )
    stations_with_parent_conflict = sum(
        1 for station in stations if len(parents.get(station, set())) > 1
    )
    stations_without_parent = sum(
        1 for station in stations if not parents.get(station)
    )
    geocoded_stations = sum(station in coordinates for station in stations)
    timed_legs = sum(
        bool(as_text(row.get("etd"))) and bool(as_text(row.get("eta")))
        for row in timed_departure_rows
    )
    exact_cutoffs = sum(
        parse_clock(row.get("Earliest cutoff")) for row in cutoff_rows
    )
    all_headers: dict[str, list[str]] = {}
    for sheet_name in ("Connecting hub_earliest cutoff", "Coonection timings"):
        iterator = iter_sheet(data_dir / FILES["regional"], sheet_name)
        first = next(iterator, {})
        all_headers[sheet_name] = list(first)
    operational_headers = {
        header.lower()
        for headers in all_headers.values()
        for header in headers
    }
    has_speed_field = any("speed" in header for header in operational_headers)
    has_handling_field = any(
        term in header
        for header in operational_headers
        for term in ("load", "unload", "handling", "cooling")
    )
    has_window_field = any(
        term in header
        for header in operational_headers
        for term in ("window", "delivery by", "latest arrival")
    )
    known_types_by_station = {
        as_text(row.get("node")): as_text(row.get("vehicle_type"))
        for row in nonblank_compatibility
    }
    mapped_demand_stations = sum(
        station in known_types_by_station for station in stations
    )
    candidate_rows = []
    for candidate in sorted(candidates):
        candidate_rows.append(
            {
                "candidate_crossdock": candidate,
                "connection_count": candidate_routes[candidate],
                "connection_tiers": "|".join(sorted(candidate_tiers[candidate])),
                "has_coordinates": candidate in coordinates,
                "latitude": coordinates.get(candidate, ("", ""))[0],
                "longitude": coordinates.get(candidate, ("", ""))[1],
                "appears_as_delivery_station": candidate in stations,
                "appears_as_current_parent": candidate in unique_parents,
                "current_parent_station_count": current_parent_counts.get(candidate, 0),
            }
        )
    write_csv(
        output_dir / "candidate_crossdocks.csv",
        candidate_rows,
        list(candidate_rows[0]) if candidate_rows else ["candidate_crossdock"],
    )

    findings = [
        {
            "area": "Historical demand",
            "status": "PASS" if len(observed_dates) >= 14 else "PARTIAL",
            "evidence": (
                f"{demand_rows:,} B2C Landing records; {len(observed_dates)} dates "
                f"({observed_dates[0] if observed_dates else 'n/a'} to "
                f"{observed_dates[-1] if observed_dates else 'n/a'})."
            ),
            "impact": "Demand scenarios can be estimated from observed daily history; one month is not seasonal coverage.",
        },
        {
            "area": "Facility role classification",
            "status": "PARTIAL",
            "evidence": f"{len(candidates)} candidate locations inferred from AllConnections Milkrun source hubs; no authoritative facility-role field.",
            "impact": "Crossdock/terminal/delivery-station role decisions require business confirmation.",
        },
        {
            "area": "Delivery-station coordinates",
            "status": "PASS" if geocoded_stations == len(stations) else "BLOCKER",
            "evidence": f"{geocoded_stations}/{len(stations)} demand stations have coordinates.",
            "impact": "Unlocated destinations cannot be assigned by travel distance or included in route construction.",
        },
        {
            "area": "Vehicle-station compatibility",
            "status": "PASS" if mapped_demand_stations == len(stations) else "BLOCKER",
            "evidence": f"{mapped_demand_stations}/{len(stations)} stations have a nonblank vehicle-type mapping ({len(nonblank_compatibility)} mapped nodes total).",
            "impact": "Vehicle compatibility cannot be safely enforced for most destinations.",
        },
        {
            "area": "Delivery time windows",
            "status": "PASS" if has_window_field else "BLOCKER",
            "evidence": "No time-window field exists in Regional_Data.xlsx." if not has_window_field else "Time-window field exists.",
            "impact": "SLA feasibility and arrival-window adherence cannot be calculated.",
        },
        {
            "area": "Travel times / lane speeds",
            "status": "PASS" if has_speed_field else "BLOCKER",
            "evidence": f"No average-speed field or speed sheet found; {timed_legs}/{len(timed_departure_rows)} scheduled legs have ETD and ETA.",
            "impact": "Existing schedules do not provide travel times for newly designed lanes.",
        },
        {
            "area": "Handling / cooling durations",
            "status": "PASS" if has_handling_field else "BLOCKER",
            "evidence": "No loading, unloading, reloading, or cooling-duration field exists.",
            "impact": "Dispatch, trip sequencing, and 16-hour working-time checks cannot be completed.",
        },
        {
            "area": "Dispatch cut-offs",
            "status": "PASS" if exact_cutoffs == len(cutoff_rows) else "PARTIAL",
            "evidence": f"{exact_cutoffs}/{len(cutoff_rows)} cut-offs parse as clock times.",
            "impact": "Non-clock entries need a business rule before schedule optimization.",
        },
        {
            "area": "Facility operating costs",
            "status": "BLOCKER",
            "evidence": "No Crossdock Hub or Delivery Station operating cost fields are present.",
            "impact": "A total operating-cost optimum and facility-role cost trade-off cannot be claimed.",
        },
        {
            "area": "Historical parent assignment",
            "status": "PASS"
            if stations_with_parent_conflict == 0 and stations_without_parent == 0
            else "PARTIAL",
            "evidence": (
                f"{len(unique_parents)} distinct parents; "
                f"{stations_with_parent_conflict} stations have multiple parent "
                f"values and {stations_without_parent} have no parent."
            ),
            "impact": "Current parent is descriptive only, not a validated future assignment.",
        },
    ]
    write_csv(
        output_dir / "readiness_findings.csv",
        findings,
        ["area", "status", "evidence", "impact"],
    )

    mean_daily = [
        total / len(observed_dates) if observed_dates else 0.0
        for total in total_demand
    ]
    parent_daily_weight = {
        parent: round(sum(
            daily.get((station, day), [0.0, 0.0, 0.0])[0]
            for station in stations
            if parent in parents.get(station, set())
            for day in observed_dates
        ) / len(observed_dates), 3) if observed_dates else 0.0
        for parent in unique_parents
    }
    parent_daily_volume = {
        parent: round(sum(
            daily.get((station, day), [0.0, 0.0, 0.0])[1]
            for station in stations
            if parent in parents.get(station, set())
            for day in observed_dates
        ) / len(observed_dates), 3) if observed_dates else 0.0
        for parent in unique_parents
    }
    top_parents = sorted(
        (
            {
                "parent": parent,
                "mean_daily_phyweight": parent_daily_weight[parent],
                "mean_daily_volweight": parent_daily_volume[parent],
                "station_count": current_parent_counts[parent],
            }
            for parent in unique_parents
        ),
        key=lambda item: item["mean_daily_phyweight"],
        reverse=True,
    )

    summary = {
        "inputs": {key: value for key, value in FILES.items()},
        "demand": {
            "sheet": demand_sheet,
            "records": demand_rows,
            "invalid_station_or_date_records": invalid_demand_rows,
            "observed_dates": observed_dates,
            "delivery_station_count": len(stations),
            "current_parent_count": len(unique_parents),
            "total_phyweight": round(total_demand[0], 3),
            "total_volweight": round(total_demand[1], 3),
            "total_shipments": round(total_demand[2], 3),
            "mean_daily_phyweight": round(mean_daily[0], 3),
            "mean_daily_volweight": round(mean_daily[1], 3),
            "mean_daily_shipments": round(mean_daily[2], 3),
            "zero_filled_missing_station_days": True,
            "top_current_parents_by_daily_phyweight": top_parents,
        },
        "network": {
            "candidate_crossdock_count_inferred_from_milkrun_sources": len(candidates),
            "candidate_crossdocks_with_coordinates": sum(
                candidate in coordinates for candidate in candidates
            ),
            "delivery_stations_with_coordinates": geocoded_stations,
            "delivery_stations_without_coordinates": len(stations) - geocoded_stations,
            "coordinate_rows": len(coordinates),
            "duplicate_coordinate_names": duplicate_coordinates,
            "stations_with_multiple_current_parents": stations_with_parent_conflict,
            "stations_without_current_parent": stations_without_parent,
        },
        "operations": {
            "vehicle_types": len(vehicle_rows),
            "vehicle_node_rows": len(compatibility_rows),
            "vehicle_node_rows_with_vehicle_type": len(nonblank_compatibility),
            "demand_stations_with_vehicle_compatibility": mapped_demand_stations,
            "cutoff_locations": len(cutoff_rows),
            "cutoffs_parsing_as_clock_time": exact_cutoffs,
            "scheduled_leg_rows": len(timed_departure_rows),
            "scheduled_legs_with_etd_and_eta": timed_legs,
            "lane_speed_data_present": has_speed_field,
            "handling_duration_data_present": has_handling_field,
            "delivery_window_data_present": has_window_field,
            "facility_operating_cost_data_present": False,
        },
        "readiness": {
            "optimization_ready": not any(
                item["status"] == "BLOCKER" for item in findings
            ),
            "findings": findings,
        },
    }
    (output_dir / "analysis_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    make_map(output_dir / "current_network_map.html", coordinates, candidates, assignment_rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "network_design_outputs",
    )
    args = parser.parse_args()
    summary = run(args.data_dir.resolve(), args.output_dir.resolve())
    demand = summary["demand"]
    network = summary["network"]
    print(
        f"Audit complete: {demand['delivery_station_count']} stations, "
        f"{network['candidate_crossdock_count_inferred_from_milkrun_sources']} "
        f"inferred candidate crossdocks, "
        f"{network['delivery_stations_with_coordinates']}/"
        f"{demand['delivery_station_count']} stations geocoded."
    )
    print(
        "Optimization ready: "
        + ("yes" if summary["readiness"]["optimization_ready"] else "no")
        + f"; outputs: {args.output_dir}"
    )


if __name__ == "__main__":
    main()
