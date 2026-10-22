# Regional Crossdock Network Design - Data Audit and Decision Readiness

## Executive decision

**Do not convert or close any Crossdock Hub on the evidence currently supplied.**
The files support a reproducible demand profile and a preliminary list of 12
candidate locations, but they do not support a constraint-feasible facility,
vehicle-route, or schedule optimization. A reduced-hub design, final hub count,
vehicle plan, and total-cost optimum would therefore be speculative.

The prudent interim action is to preserve the current operating topology until
the missing role, location, compatibility, service-window, handling, lane-time,
and facility-cost inputs are confirmed. The 12 sites below are inferred from
Milkrun connection origins; the data does not independently confirm that all
12 are active Crossdock Hubs or distinguish them from fixed terminals.

## What the supplied data establishes

| Measure | Result |
|---|---:|
| B2C Landing history | 354,398 records, 2026-07-01 through 2026-07-31 |
| Distinct destination names in the demand sheet | 282 |
| Distinct current parent names | 16 |
| Mean daily physical-weight field | 33,339.53 (source unit not specified) |
| Mean daily volume-weight field | 29,566.34 (source unit not specified) |
| Mean daily shipment count | 58,603.42 |
| Candidate sites inferred from Milkrun connection origins | 12 |
| Candidate sites with coordinates | 12/12 |
| Demand destinations with coordinates | 170/282 (60.3%) |
| Vehicle types with cost/capacity/distance fields | 21 |
| Demand destinations with a nonblank vehicle compatibility entry | 2/282 |
| Dispatch cut-offs parseable as clock times | 13/14 |
| Existing schedule legs with both ETD and ETA | 345/348 |

Demand scenarios should use the same historical window for each network
alternative. The included extract has only one month, so it is not evidence of
seasonality or annual peaks. The station profile reports mean, P90, and P95
daily demand by the `phyweight`, `volweight`, and `shipment_count` fields. A
missing station/date row is treated as zero for those daily statistics; confirm
that the extract is complete before using the zero-filled percentiles for
capacity planning. Units for the two weight fields are not specified in the
provided workbook.

The six largest current parent groups (Ambala, Ludhiana, Delhi_LM, Chandigarh,
Panipat, and Jammu) account for about 98.3% of the observed mean daily physical
weight. The parent values are descriptive source fields, not a validated
future assignment. One destination name has no parent value; no destination
has multiple parent values in the extract.

## Candidate Crossdock locations

The current candidate list is inferred by taking the distinct `Source Hub Name`
values for `Milkrun` rows in `AllConnections.xlsx`. These are not independently
validated facility roles.

| Inferred candidate site | Milkrun connection rows | Coordinate |
|---|---:|---|
| Ambala | 8 | Present |
| Amritsar | 3 | Present |
| Bathinda | 5 | Present |
| Bilaspur | 2 | Present |
| Chandigarh | 6 | Present |
| Jalandhar | 4 | Present |
| Jammu | 3 | Present |
| Ludhiana | 3 | Present |
| Panipat | 1 | Present |
| Pathankot | 3 | Present |
| Srinagar | 4 | Present |
| Totu_LM | 4 | Present |

These counts describe connection records, not facility throughput or site
capacity. The demand sheet has 16 current parent names, including names not in
this inferred candidate set. In addition, a few inferred candidate sites also
occur as demand destinations. Business owners must confirm the role and
conversion semantics for each such location before the model can decide whether
it remains a Crossdock Hub or becomes a Delivery Station.

## Validation findings and blockers

1. **Facility roles and fixed terminals are not labelled.** The only candidate
   classification available is the Milkrun-source inference above. Terminal
   Hubs, fixed upstream connections, Crossdock Hubs, and Delivery Stations need
   an authoritative facility master and fixed-route designation.
2. **112/282 destinations lack coordinates.** The route geometry cannot cover
   every demand location. Candidate coordinates are available, but this alone
   does not enable route distances for all destinations.
3. **Vehicle compatibility is almost entirely blank.** `Vehicle Node Map`
   contains 191 nodes but only two nonblank vehicle-type mappings. The existing
   schedule vehicle labels also do not consistently match the 21 vehicle
   master labels.
4. **No Delivery Station service windows are present.** SLA adherence and
   arrival feasibility cannot be tested.
5. **No lane-speed or travel-time matrix for new lanes is present.** Although
   345 existing schedule legs have ETD and ETA, those individual scheduled legs
   do not provide travel times for arbitrary candidate routes.
6. **No loading, unloading, reloading, or cooling durations are present.**
   Therefore schedule propagation, dispatch feasibility, and the 16-hour
   vehicle workday cannot be verified.
7. **Facility operating costs are absent.** Vehicle fixed and per-kilometre
   costs are present, but hub-versus-station facility costs are not. Any result
   that assigns zero facility cost would not establish a complete operating
   cost optimum.
8. **One of 14 dispatch cut-offs is not a clock time.** `Landing+1 hr` needs an
   explicit operational interpretation.

The detailed machine-readable evidence is in
[`network_design_outputs/readiness_findings.csv`](./network_design_outputs/readiness_findings.csv)
and [`network_design_outputs/analysis_summary.json`](./network_design_outputs/analysis_summary.json).

## Recommended mathematical formulation

This is the model to implement after the missing inputs are supplied. It is a
facility-location model linked to a vehicle-routing-and-scheduling model; the
current deliverables do **not** claim to solve it.

### Sets and variables

- `H`: validated candidate Crossdock locations; `S`: Delivery Stations,
  including sites converted from Crossdocks; `T`: fixed Terminal Hubs;
  `V`: compatible vehicle types; `K`: available vehicle/trip slots.
- `x_h = 1` if candidate `h` remains a Crossdock Hub; `c_h = 1` if converted
  into a Delivery Station.
- `y_sh = 1` if Delivery Station `s` is assigned to retained Crossdock `h`.
- `z_ijkv = 1` if vehicle slot `k` of type `v` traverses arc `i -> j`;
  `u_ikv = 1` if it visits node `i`; `t_ikv` is its service start time.
- `q_ikv` and `r_ikv`: delivered weight and volume load variables.

### Objective and trade-off

For a service-time trade-off coefficient `lambda >= 0`, minimize

`facility_cost + vehicle_fixed_cost + vehicle_km_cost + lambda * delivery_time_cost`.

Facility cost includes the role-specific daily operating cost at every site.
Vehicle costs use the applicable fixed cost and cost per kilometre from the
vehicle master. Delivery-time cost can represent elapsed time or a lateness
penalty, with unserved demand prohibited. Compare solutions across a documented
range of `lambda` values (or use an epsilon constraint on delivery time) to
produce a cost-versus-speed Pareto frontier. Do not set unknown facility costs
to zero and call the result a total-cost optimum.

### Core constraints

- **One role per candidate:** `x_h + c_h = 1` for each candidate location.
- **Fixed upstream network:** retain Terminal Hubs and designated upstream
  connections as fixed inputs; do not create decision variables that redesign
  those links.
- **Exactly one retained serving hub per Delivery Station:**
  `sum_h y_sh = 1` and `y_sh <= x_h`.
- **Conversion semantics:** a converted site is no longer available as an
  intermediate Crossdock Hub; if it is a Delivery Station, it must itself be
  assigned to exactly one other retained Crossdock Hub.
- **Vehicle compatibility:** a visit/assignment is allowed only for vehicle
  types approved for that destination.
- **Capacity:** for each trip, total delivered weight and volume do not exceed
  the selected vehicle's weight and volume capacity.
- **Route continuity:** vehicle flow into and out of each visited station is
  balanced; subtours are excluded; each trip starts and ends at the appropriate
  retained Crossdock.
- **Trip limit:** route distance does not exceed the chosen vehicle type's
  maximum trip distance.
- **Schedule propagation:** departure, travel, loading, unloading, reloading,
  and service times obey the lane times and handling durations; station arrival
  lies within its delivery window; Crossdock dispatch respects its cut-off.
- **Workday:** total duty time for a vehicle is at most 16 hours per day,
  including travel and all applicable handling/wait time.
- **Demand scenarios:** use the same empirical day/scenario set and service
  assumptions for every facility configuration. Test mean and chosen upper
  percentiles (such as P90/P95) derived from the same historical period.

### Practical solution method

Once data is complete, use a staged solve: (1) solve facility role and station
assignment with a mixed-integer location-allocation model; (2) solve a
capacity-constrained multi-trip VRPTW for each retained hub; (3) feed route
feasibility/cost back to the facility model and iterate until stable. Validate
each emitted schedule independently against capacities, compatibility,
distance, cut-offs, service windows, handling durations, and the 16-hour duty
limit. This decomposition is preferable to reporting a single location-only
optimum as a complete network design.

## Current recommendation and scope of results

- **Required retained Crossdock count:** undetermined. Twelve candidate sites
  are inferred, but the active facility set and terminal/crossdock role labels
  are not verified.
- **Sites to retain or convert:** no conversion is recommended from these data.
  No role choice has been optimized.
- **Delivery Station assignments:** the source parent field is exported in
  [`network_design_outputs/current_assignments.csv`](./network_design_outputs/current_assignments.csv)
  as a current-state reference only. It is not the proposed assignment; one
  destination has no parent.
- **Vehicle routes and schedules:** none are proposed. Existing schedule data
  are retained as source facts only; no new schedule can be certified against
  the requested service and work-hour constraints.
- **Scenario comparison:** no cost/distance/service comparison is reported as
  an optimized alternative because key feasibility and facility-cost inputs
  are missing. The model should not manufacture routes, assume unrestricted
  vehicle compatibility, or treat unknown operating costs as zero.
- **Map:** [`network_design_outputs/current_network_map.html`](./network_design_outputs/current_network_map.html)
  plots geocoded candidate sites, delivery stations, and current parent links
  when both endpoints have coordinates. It is a coordinate plot, not a road
  map or a proposed network; 112 unlocated destinations are omitted.

## Reproduction and outputs

From this folder, install the single workbook-reading dependency and run:

```powershell
python -m pip install -r requirements.txt
python .\network_design.py --data-dir . --output-dir .\network_design_outputs
```

The script reads the five supplied inputs and writes:

- `analysis_summary.json` - aggregate demand, coverage, and readiness status.
- `readiness_findings.csv` - evidence and impact of each required input check.
- `candidate_crossdocks.csv` - inferred candidates and source-route counts.
- `station_demand.csv` - per-station mean/P90/P95 daily demand.
- `current_assignments.csv` - historical parent links, not optimized links.
- `current_network_map.html` - coordinate plot of the geocoded current network.

The script deliberately reports `optimization_ready: false` while blocker
inputs remain absent. It does not produce a false-positive feasible route plan.

## Data required to complete the optimization

Provide or confirm: (1) facility master with role, candidate/fixed status, and
conversion eligibility; (2) authoritative station coordinates for all demand
locations; (3) per-station vehicle compatibility; (4) service windows and SLA
definition; (5) lane road distance or calibrated road-distance factor and
travel time/speed; (6) Crossdock loading/unloading/reload durations and cooling
hours; (7) exact cutoff interpretation for every facility; (8) Crossdock and
Delivery Station operating costs; (9) vehicle label crosswalk and confirmation
of weight/volume units; and (10) confirmation that omitted station/date rows
mean zero demand. These additions unblock a feasible route plan and a
defensible comparison of retained versus converted hubs.
