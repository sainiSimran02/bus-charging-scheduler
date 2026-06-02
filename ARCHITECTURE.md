# Architecture & Extensibility

## Data Model

- `config.json` holds all physical constants, the route graph, station details, and tunable weights.
- Each scenario file contains only the bus fleet (ID, operator, direction, departure time) and optional weight overrides.
- The route is defined as a list of stops and segments; distances and travel times are computed from these.
- Stations are defined separately, each with a configurable number of chargers (currently 1).

## Why This Design?

- Separating the world definition from the daily schedule allows a single config to be reused across many scenarios.
- Adding a new station or route does not require any change to the scenario files.
- Weights are stored in one obvious place (`config.json`) and can be overridden per scenario via `config_override`.

## Anticipated Future Changes & How They Are Handled

### 1. More Charging Stations

- Add the station name to `config.json` under `stations` and insert the appropriate stop and segments in the route. The scheduler dynamically reads the route graph, so no code changes are needed.

### 2. Multiple Chargers per Station

- Already supported: the `chargers` field is an integer. The simulation can be extended to manage multiple `Charger` objects per station. Currently only one is instantiated, but the data model permits multiple.

### 3. New Routes (e.g., Loops, Branching)

- Define a new route in `config.json` with its own stops and segments. Buses in a scenario can reference a `route_id` field. The scheduler would then build the distance matrix from the selected route. No engine rewrite.

### 4. Priority Buses (e.g., Medical Emergency)

- Add a `priority` field to the bus object. A new `PriorityRule` class would give preferential treatment. Only the rule class and a weight entry in config are needed.

### 5. Time‑of‑Day Electricity Pricing

- Extend stations with a price schedule (e.g., cost per minute). A new `EnergyCostRule` can prefer charging when electricity is cheap. Again, just a new rule.

### 6. Driver Shift Limits

- Add a `max_driving_time` field to buses (or a separate driver entity). A `DriverShiftRule` would enforce that a bus must stop before the driver’s hours run out. New rule.

### 7. Varying Battery Capacity per Bus Type

- Add a `bus_type` field to the bus, and a lookup table in config for battery range per type. The scheduler already reads `remaining_range` from constants; that can become bus‑specific.

### 8. Multiple Routes Sharing Stations

- Stations are global (keyed by name). Buses from any route can queue at any station. No change needed.

### 9. Real‑Time Traffic

- Replace fixed travel times with a function (e.g., time‑of‑day factor). The travel time lookup would become a method that considers the current simulation time. Minor adjustment, no architectural change.

### 10. Partial Charging (Not Always to Full)

- Parameterise charging time as a function of needed range. The decision action space could include “charge enough to reach next station”. This would require a small extension to the rule evaluation, but the framework remains intact.

## Scheduling Engine Design

- **Event‑driven simulation**: Time advances via a priority queue of events, allowing efficient processing of many buses and stations.
- **Rule‑based decision making**: At every decision point (charge vs. skip, which bus to serve next), all candidate actions are scored by a weighted sum of rule costs. The action with the lowest cost is chosen.
- **Pluggable rules**: New rules are implemented by subclassing `Rule` and adding an entry to the `rule_weight_map`. The scheduler automatically picks them up.
- **Tunable weights**: Stored in `config.json` and overridable per scenario. Changing a weight immediately changes behavior without touching code.
- **No hardcoded station names or counts**: All driven by configuration.

## Code Organisation

- `config.json`: World constants and tunables.
- `scenarios/*.json`: Daily input data.
- `scheduler.py`: Simulation engine, event loop, rule interface, concrete rules.
- `app.py`: Streamlit UI.
- `requirements.txt`: Dependencies.
- `ARCHITECTURE.md`: This document.

This design ensures that the system can grow with minimal refactoring as new operational requirements emerge.
