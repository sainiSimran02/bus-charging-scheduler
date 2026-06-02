Bus Charging Scheduler

A Python + Streamlit scheduler for electric buses on the Bengaluru–Kochi route.
It decides where and when each bus charges, respecting hard range constraints
and optimising tunable soft rules.

## How to run locally

1. Clone the repo
   git clone https://github.com/your-username/bus-charging-scheduler.git
   cd bus-charging-scheduler

2. Install dependencies
   pip install -r requirements.txt

3. Launch the app
   streamlit run app.py
   Open the URL printed in the terminal (usually http://localhost:8501).

4. Use the app
   - Choose a scenario from the dropdown.
   - Click "⚡ Run Scheduler".
   - Inspect the per-bus timetable and per-station usage.

## How to change a weight

Weights are stored in ONE obvious place — the "weights" section of config.json.
They can also be overridden per scenario using config_override (see Scenario 4).

Example: make operator fairness twice as important

// config.json
"weights": {
"individual_wait": 1.0,
"operator_balance": 2.0, // changed from 1.0 to 2.0
"total_network_time": 1.0
}

Re-run the scheduler (reload the Streamlit page). The new weight takes effect
immediately. No code changes needed.

## How to add a new rule

Adding a rule does NOT require touching the engine core. Just follow three steps.

1. Write the rule class
   In scheduler.py, create a subclass of Rule with an evaluate() method.

   Example: penalise charging when the battery is still quite full.

   class UnnecessaryChargePenalty(Rule):
   def evaluate(self, action, bus, world_state, context):
   if action["type"] == "charge_now": # if range > 50 %, add a penalty
   if bus.remaining_range > world_state.constants["battery_range_km"] \* 0.5:
   return 10.0 # cost (higher = worse)
   return 0.0

2. Register the rule
   Inside Scheduler.**init**, add an instance of your rule to the self.rules list:

   self.rules = [
   IndividualWaitRule(),
   OperatorBalanceRule(),
   TotalNetworkTimeRule(),
   UnnecessaryChargePenalty() # new rule
   ]

3. Add a weight in config
   In config.json, add a key under "weights" (use the class name in lowercase
   with underscores):

   "weights": {
   "individual_wait": 1.0,
   "operator_balance": 1.0,
   "total_network_time": 1.0,
   "unnecessary_charge_penalty": 1.0
   }

   Also update the rule_weight_map dictionary inside Scheduler.**init**:

   self.rule_weight_map = {
   "IndividualWaitRule": "individual_wait",
   "OperatorBalanceRule": "operator_balance",
   "TotalNetworkTimeRule": "total_network_time",
   "UnnecessaryChargePenalty": "unnecessary_charge_penalty"
   }

That's it. The scheduler now uses your rule, and you can tune its impact by
changing the weight in config.json.

## Scenario file format (for reference)

{
"scenario_name": "Even spacing",
"config_override": {}, // optional weight overrides
"buses": [
{
"id": "bus-BK-01",
"operator": "kpn",
"direction": "B->K", // B->K = Bengaluru→Kochi, K->B = Kochi→Bengaluru
"departure_time_min": 0 // minutes after 19:00
}
// ...
]
}

To add a new scenario, simply drop a JSON file into the scenarios/ folder —
the app detects it automatically.

## More details

For the full architecture design, extensibility list, and design rationale,
see ARCHITECTURE.md.
