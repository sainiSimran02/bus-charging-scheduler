import streamlit as st
import json
import os
import pandas as pd
from scheduler import Scheduler

st.set_page_config(page_title="Bus Charging Scheduler", layout="wide")
st.title("🚌 Bus Charging Scheduler")

# Load configuration
config = json.load(open("config.json"))

# Discover scenarios
scenario_files = [f for f in os.listdir("scenarios") if f.endswith(".json")]
scenarios = []
for f in scenario_files:
    data = json.load(open(f"scenarios/{f}"))
    scenarios.append((data["scenario_name"], f))
scenario_map = dict(scenarios)

selected_name = st.selectbox("Select Scenario", list(scenario_map.keys()))
selected_file = scenario_map[selected_name]

# Load scenario data
scenario = json.load(open(f"scenarios/{selected_file}"))

st.header("📋 Scenario Input")
# Show raw input
with st.expander("Show raw scenario data"):
    st.json(scenario)

# Run the scheduler
if st.button("⚡ Run Scheduler"):
    scheduler = Scheduler(config, scenario)
    result = scheduler.run()

    st.header("🚏 Per‑Bus Timetable")
    for bus_data in result["buses"]:
        st.subheader(f"{bus_data['id']} ({bus_data['operator']}) — {bus_data['direction']}")
        st.write(f"Departure: {bus_data['departure']} min | Arrival: {bus_data['arrival']} min | "
                 f"Duration: {bus_data['trip_duration']:.1f} min")
        if bus_data["timeline"]:
            df = pd.DataFrame(bus_data["timeline"])
            st.dataframe(df)
        else:
            st.write("No charging stops.")

    st.header("🔌 Per‑Station Usage")
    # Build station logs from bus timelines
    station_logs = {s: [] for s in config["stations"]}
    for bus_data in result["buses"]:
        for entry in bus_data["timeline"]:
            if entry["charge_start"] is not None:
                station_logs[entry["station"]].append({
                    "bus_id": bus_data["id"],
                    "operator": bus_data["operator"],
                    "arrival": entry["arrival"],
                    "wait_start": entry["wait_start"],
                    "charge_start": entry["charge_start"],
                    "charge_end": entry["charge_end"]
                })
    for sname, logs in station_logs.items():
        st.subheader(f"Station {sname}")
        if logs:
            st.dataframe(pd.DataFrame(logs).sort_values("charge_start"))
        else:
            st.write("No charging activity.")