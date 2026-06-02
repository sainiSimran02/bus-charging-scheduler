import json
import heapq
from abc import ABC, abstractmethod
from collections import defaultdict

# ----------------------------------------------------------------------
#  Data classes
# ----------------------------------------------------------------------
class Bus:
    def __init__(self, bus_id, operator, direction, departure_time):
        self.id = bus_id
        self.operator = operator
        self.direction = direction            # "B->K" or "K->B"
        self.departure_time = departure_time
        self.timeline = []                   # list of per‑station dicts
        self.state = "at_origin"             # at_origin, traveling, waiting, charging, arrived
        self.remaining_range = 0
        self.next_stop_index = 1
        self.wait_start = None
        self.arrival_time = None

class Charger:
    def __init__(self, station_name):
        self.station = station_name
        self.bus_charging = None
        self.queue = []                      # list of bus IDs
        self.charge_end_time = 0

# ----------------------------------------------------------------------
#  Rule interface
# ----------------------------------------------------------------------
class Rule(ABC):
    """Abstract base class for all scheduling rules."""
    @abstractmethod
    def evaluate(self, action, bus, world_state, context):
        """Return a cost (float). Lower is better."""
        pass

# ----------------------------------------------------------------------
#  Concrete rules
# ----------------------------------------------------------------------
class IndividualWaitRule(Rule):
    """Penalises actions that increase an individual bus's waiting time."""
    def evaluate(self, action, bus, world_state, context):
        wait = 0
        if bus.wait_start is not None:
            wait += world_state.current_time - bus.wait_start
        if action["type"] == "charge_now":
            charger = world_state.chargers[action["station"]]
            if charger.bus_charging is not None:
                extra = max(0, charger.charge_end_time - world_state.current_time)
                wait += extra
        return wait

class OperatorBalanceRule(Rule):
    """Penalises if an operator's fleet already has higher average waiting time than others."""
    def evaluate(self, action, bus, world_state, context):
        op_wait_sum = defaultdict(float)
        op_wait_cnt = defaultdict(int)
        for b in world_state.buses.values():
            if b.wait_start is not None:
                w = world_state.current_time - b.wait_start
                op_wait_sum[b.operator] += w
                op_wait_cnt[b.operator] += 1
        if not op_wait_cnt:
            return 0
        avg_waits = {op: op_wait_sum[op] / op_wait_cnt[op] for op in op_wait_sum}
        overall_avg = sum(op_wait_sum.values()) / sum(op_wait_cnt.values())
        bus_op_avg = avg_waits.get(bus.operator, 0)
        return max(0, bus_op_avg - overall_avg)

class TotalNetworkTimeRule(Rule):
    """Placeholder for overall network time minimisation. Currently neutral."""
    def evaluate(self, action, bus, world_state, context):
        return 0   # can be enhanced later

# ----------------------------------------------------------------------
#  Scheduler engine
# ----------------------------------------------------------------------
class Scheduler:
    def __init__(self, config, scenario):
        self.config = config
        self.scenario = scenario
        self.constants = config["constants"]
        self.stations_info = config["stations"]
        self.route_stops = config["route"]["stops"]
        self.segments = config["route"]["segments"]

        # Merge weights (global + scenario override)
        self.weights = dict(config.get("weights", {}))
        overrides = scenario.get("config_override", {}).get("weights", {})
        self.weights.update(overrides)

        # Build distance and travel time lookups
        self.distances = {}
        self.travel_times = {}
        for seg in self.segments:
            f, t, d = seg["from"], seg["to"], seg["distance_km"]
            self.distances[(f, t)] = d
            self.distances[(t, f)] = d
            t_min = (d / self.constants["speed_kmh"]) * 60
            self.travel_times[(f, t)] = t_min
            self.travel_times[(t, f)] = t_min

        self.current_time = 0
        self.buses = {}
        self.chargers = {s: Charger(s) for s in self.stations_info}
        self.event_queue = []      # (time, event_type, bus_id, payload)
        self.finished = 0

        # Create bus objects
        for bdata in scenario["buses"]:
            bus = Bus(bdata["id"], bdata["operator"],
                      bdata["direction"], bdata["departure_time_min"])
            self.buses[bus.id] = bus

        # Register rules (order irrelevant, all are evaluated)
        self.rules = [
            IndividualWaitRule(),
            OperatorBalanceRule(),
            TotalNetworkTimeRule()
        ]
        # Map rule class name -> weight key in config
        self.rule_weight_map = {
            "IndividualWaitRule": "individual_wait",
            "OperatorBalanceRule": "operator_balance",
            "TotalNetworkTimeRule": "total_network_time"
        }

        # Schedule initial departures
        for bus in self.buses.values():
            heapq.heappush(self.event_queue,
                           (bus.departure_time, "depart_origin", bus.id, {}))

    def run(self):
        while self.event_queue and self.finished < len(self.buses):
            time, etype, bus_id, payload = heapq.heappop(self.event_queue)
            self.current_time = time
            if etype == "depart_origin":
                self._depart_origin(bus_id)
            elif etype == "arrive_station":
                self._arrive_station(bus_id, payload["station"])
            elif etype == "start_charge":
                self._start_charge(bus_id, payload["station"])
            elif etype == "end_charge":
                self._end_charge(bus_id, payload["station"])
            elif etype == "arrive_destination":
                self._arrive_destination(bus_id)
        return self._collect_results()

    # ------------------------------------------------------------------
    #  Helper: direction-aware stop list
    # ------------------------------------------------------------------
    def _get_direction_stops(self, bus):
        if bus.direction == "B->K":
            return self.route_stops
        else:
            return list(reversed(self.route_stops))

    # ------------------------------------------------------------------
    #  Event handlers
    # ------------------------------------------------------------------
    def _depart_origin(self, bus_id):
        bus = self.buses[bus_id]
        bus.remaining_range = self.constants["battery_range_km"]
        stops = self._get_direction_stops(bus)
        origin = stops[0]
        first_stop = stops[1]
        travel_time = self.travel_times[(origin, first_stop)]
        bus.state = "traveling"
        bus.next_stop_index = 1
        bus.current_location = (origin, first_stop)
        heapq.heappush(self.event_queue,
                       (self.current_time + travel_time, "arrive_station",
                        bus.id, {"station": first_stop}))

    def _arrive_station(self, bus_id, station):
        bus = self.buses[bus_id]
        bus.state = "at_station"
        bus.current_location = station

        # Add timeline entry for this station visit
        entry = {
            "station": station,
            "arrival": self.current_time,
            "wait_start": None,
            "charge_start": None,
            "charge_end": None,
            "depart": None
        }
        bus.timeline.append(entry)

        stops = self._get_direction_stops(bus)
        idx = stops.index(station)
        next_stop = stops[idx + 1]
        dist_to_next = self.distances[(station, next_stop)]

        # Hard constraint: must charge if range insufficient
        if bus.remaining_range < dist_to_next:
            self._request_charge(bus, station, mandatory=True)
        else:
            # Decision: charge now or skip?
            self._decide_charge(bus, station)

    def _decide_charge(self, bus, station):
        actions = [
            {"type": "charge_now", "station": station},
            {"type": "skip_charge", "station": station}
        ]
        best_action = min(actions, key=lambda a: self._score_action(a, bus))
        if best_action["type"] == "charge_now":
            self._request_charge(bus, station, mandatory=False)
        else:
            self._continue_journey(bus, station)

    def _score_action(self, action, bus):
        total = 0
        for rule in self.rules:
            weight = self.weights.get(
                self.rule_weight_map[rule.__class__.__name__], 0)
            total += weight * rule.evaluate(action, bus, self, {})
        return total

    def _request_charge(self, bus, station, mandatory):
        charger = self.chargers[station]
        bus.state = "waiting"
        bus.wait_start = self.current_time
        bus.timeline[-1]["wait_start"] = self.current_time
        charger.queue.append(bus.id)
        # If charger is free, start charging immediately
        if charger.bus_charging is None:
            self._serve_next(station)

    def _serve_next(self, station):
        charger = self.chargers[station]
        if not charger.queue:
            return
        # Use simple FIFO; a more advanced version could reorder the queue
        # using rule scores when multiple buses are waiting.
        next_bus = charger.queue.pop(0)
        heapq.heappush(self.event_queue,
                       (self.current_time, "start_charge",
                        next_bus, {"station": station}))

    def _start_charge(self, bus_id, station):
        bus = self.buses[bus_id]
        charger = self.chargers[station]
        charger.bus_charging = bus_id
        bus.state = "charging"
        bus.timeline[-1]["charge_start"] = self.current_time
        charge_duration = self.constants["charging_time_min"]
        charger.charge_end_time = self.current_time + charge_duration
        heapq.heappush(self.event_queue,
                       (charger.charge_end_time, "end_charge",
                        bus.id, {"station": station}))

    def _end_charge(self, bus_id, station):
        bus = self.buses[bus_id]
        charger = self.chargers[station]
        charger.bus_charging = None
        bus.remaining_range = self.constants["battery_range_km"]
        bus.timeline[-1]["charge_end"] = self.current_time
        bus.timeline[-1]["depart"] = self.current_time
        self._continue_journey(bus, station)
        # If other buses are waiting, start the next charge
        if charger.queue:
            self._serve_next(station)

    def _continue_journey(self, bus, station):
        stops = self._get_direction_stops(bus)
        idx = stops.index(station)
        next_stop = stops[idx + 1]
        dist = self.distances[(station, next_stop)]
        bus.remaining_range -= dist
        travel = self.travel_times[(station, next_stop)]
        bus.state = "traveling"
        bus.current_location = (station, next_stop)
        if next_stop in self.stations_info:
            heapq.heappush(self.event_queue,
                           (self.current_time + travel, "arrive_station",
                            bus.id, {"station": next_stop}))
        else:
            heapq.heappush(self.event_queue,
                           (self.current_time + travel, "arrive_destination",
                            bus.id, {}))

    def _arrive_destination(self, bus_id):
        bus = self.buses[bus_id]
        bus.state = "arrived"
        bus.arrival_time = self.current_time
        self.finished += 1

    # ------------------------------------------------------------------
    #  Collect results for UI
    # ------------------------------------------------------------------
    def _collect_results(self):
        buses_data = []
        for bus in self.buses.values():
            buses_data.append({
                "id": bus.id,
                "operator": bus.operator,
                "direction": bus.direction,
                "departure": bus.departure_time,
                "arrival": bus.arrival_time,
                "trip_duration": (bus.arrival_time - bus.departure_time)
                                  if bus.arrival_time is not None else None,
                "timeline": bus.timeline
            })
        return {"buses": buses_data}