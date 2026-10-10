import streamlit as st
from datetime import datetime, timedelta
from ai_helper import ask_ai
import csv
import os
from pathlib import Path

# Page configuration
st.set_page_config(page_title="Airport Departure Planner", layout="wide")
st.title("✈️ Airport Departure Planner")

# Load airport data
@st.cache_data
def load_airport_data():
    """Load airport popularity data from CSV files"""
    data_dir = Path(__file__).parent / "인천국제공항공사_환승승객현황 정보_20260701"
    airport_data = {}

    if data_dir.exists():
        # Load departure data
        csv_file = data_dir / "환승승객현황 정보_2026년 상반기_출발.csv"
        if csv_file.exists():
            with open(csv_file, encoding='cp949') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    airport_code = row.get('공항코드', '').strip()
                    time = row.get('계획시간', '').strip()
                    passengers = int(row.get('환승승객', 0))

                    if airport_code and time:
                        key = f"{airport_code}_{time}"
                        if key not in airport_data:
                            airport_data[key] = 0
                        airport_data[key] += passengers

    return airport_data

# Load bus schedule data
@st.cache_data
def load_bus_schedules():
    """Load bus schedule data from CSV files"""
    bus_dir = Path(__file__).parent / "성남 공항버스 시간표(2026"
    bus_schedules = {}

    if bus_dir.exists():
        for csv_file in bus_dir.glob("*.csv"):
            bus_name = csv_file.stem.replace("-Table 1", "")
            try:
                with open(csv_file, encoding='utf-8') as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    # Skip header rows, find airport arrival times
                    bus_times = []
                    for row in rows[4:]:  # Skip first 4 header rows
                        if len(row) > 10 and row[0].strip().isdigit():
                            airport_t1 = row[10].strip()  # T1 arrival
                            airport_t2 = row[11].strip()  # T2 arrival
                            if airport_t1:
                                bus_times.append({"time": airport_t1, "terminal": "T1"})
                            if airport_t2:
                                bus_times.append({"time": airport_t2, "terminal": "T2"})
                    if bus_times:
                        bus_schedules[bus_name] = bus_times
            except Exception as e:
                pass

    return bus_schedules

airport_data = load_airport_data()
bus_schedules = load_bus_schedules()

# Sidebar for inputs
st.sidebar.header("Flight Details")

# Flight destination
destination = st.sidebar.text_input("Destination Airport Code", placeholder="e.g., SFO, LAX", value="SFO").upper()

# Flight departure time
flight_time = st.sidebar.time_input("Flight Departure Time", value=datetime.strptime("06:30", "%H:%M").time())

# Airport activity
activity = st.sidebar.selectbox(
    "What do you want to do at the airport?",
    ["Shopping", "Lounge Rest", "Dining", "Relaxing", "Work"]
)

# Duration of activity
activity_duration = st.sidebar.number_input(
    "How long do you want to spend? (hours)",
    min_value=0.5,
    max_value=4.0,
    value=2.0,
    step=0.5
)

# Travel time to airport (adjustable)
st.sidebar.markdown("---")
st.sidebar.subheader("Travel Settings")
travel_time_minutes = st.sidebar.slider(
    "Travel time from home to airport (minutes)",
    min_value=15,
    max_value=120,
    value=40,
    step=5
)

# Airport arrival buffer
airport_buffer_minutes = st.sidebar.slider(
    "Airport arrival buffer (minutes)",
    min_value=90,
    max_value=240,
    value=150,
    step=15,
    help="Time to park, check-in, security, and reach gate"
)

# Generate recommendations
st.header("Your Departure Plan")

if st.sidebar.button("Calculate Departure Time", type="primary"):
    # Convert flight time to datetime object
    flight_datetime = datetime.combine(datetime.now().date(), flight_time)

    # Calculate gate arrival time (flight time minus buffer)
    gate_arrival_time = flight_datetime - timedelta(minutes=airport_buffer_minutes)

    # Calculate home departure time
    home_departure_time = gate_arrival_time - timedelta(minutes=travel_time_minutes)

    # Get airport popularity data
    flight_time_str = flight_time.strftime('%H:%M')
    popularity_key = f"{destination}_{flight_time_str}"
    passenger_count = airport_data.get(popularity_key, 0)

    # Estimate gate distance and lounge time
    import random
    gate_distance_feet = random.randint(800, 2500)
    gate_distance_minutes = max(5, gate_distance_feet // 250)

    # Calculate lounge time (activity duration minus gate distance buffer)
    lounge_buffer = max(10, gate_distance_minutes)
    actual_lounge_time = activity_duration - (lounge_buffer / 60)
    actual_lounge_time = max(0.5, actual_lounge_time)

    # Find best bus option - ALWAYS find and recommend a bus
    recommended_bus = None
    if bus_schedules:
        all_buses = []
        for bus_name, times in bus_schedules.items():
            for bus_time_info in times:
                bus_time_str = bus_time_info["time"]
                try:
                    bus_arrival = datetime.strptime(bus_time_str, "%H:%M").time()
                    bus_arrival_datetime = datetime.combine(datetime.now().date(), bus_arrival)

                    # Calculate time difference (negative = bus arrives after flight departure, won't work)
                    time_diff = (gate_arrival_time - bus_arrival_datetime).total_seconds() / 60

                    # Only consider buses that arrive before gate arrival time
                    if time_diff >= 0:
                        all_buses.append({
                            "bus": bus_name,
                            "time": bus_time_str,
                            "terminal": bus_time_info["terminal"],
                            "buffer": int(time_diff),
                            "score": abs(time_diff - 60)  # Score: how close to ideal 60 min buffer
                        })
                except:
                    pass

        if all_buses:
            # Sort by score (closest to ideal 60 min buffer), then by buffer time
            all_buses.sort(key=lambda x: (x["score"], -x["buffer"]))
            recommended_bus = all_buses[0]  # Get best bus

    # Use AI to analyze popularity and bus recommendation
    bus_info = ""
    if recommended_bus:
        bus_info = f"\n- Recommended bus: {recommended_bus['bus']} arriving at {recommended_bus['time']} ({recommended_bus['buffer']} min buffer)"

    ai_prompt = f"""
    Airport departure analysis for {destination} at {flight_time_str}:
    - Passenger count at this time: {passenger_count} transfer passengers
    - Passenger activity: {activity.lower()} for {activity_duration} hours
    - Gate distance: ~{gate_distance_feet} feet ({gate_distance_minutes} min walk)
    - Home departure time: {home_departure_time.strftime('%H:%M')}{bus_info}

    Based on the data, provide:
    1. Popularity assessment (low/medium/high traffic at this time)
    2. Whether they have enough time for their activity
    3. If a bus is recommended, briefly confirm it's a good choice

    Keep it friendly and concise (2-3 sentences).
    """

    ai_recommendation = ask_ai(ai_prompt, max_tokens=150)

    # Display results in columns
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🚌 Bus Recommendation")
        st.success(f"""
        **{recommended_bus['bus']}**
        - **Arrival Time:** {recommended_bus['time']} (Terminal {recommended_bus['terminal']})
        - **Buffer Time:** {recommended_bus['buffer']} minutes
        """)

        st.subheader("📍 Airport Timeline")
        arrival_time = home_departure_time + timedelta(minutes=travel_time_minutes)
        try:
            bus_time = datetime.strptime(recommended_bus["time"], "%H:%M").time()
            bus_datetime = datetime.combine(datetime.now().date(), bus_time)
            st.write(f"**Take Bus at:** {recommended_bus['time']}")
        except:
            pass
        st.write(f"**Arrive at Airport:** {arrival_time.strftime('%H:%M')}")
        st.write(f"**Reach Gate:** {gate_arrival_time.strftime('%H:%M')}")
        st.write(f"**Flight Departs:** {flight_time.strftime('%H:%M')}")

    with col2:
        st.subheader("🎯 Activity Time")
        st.metric(
            f"{activity} Duration",
            f"{actual_lounge_time:.1f} hours",
            delta=f"{lounge_buffer} min buffer for {gate_distance_minutes} min gate walk"
        )

        st.subheader("📊 Airport Popularity")
        if passenger_count > 0:
            st.metric("Transfer Passengers", passenger_count)
            if passenger_count > 100:
                popularity = "🔴 High Traffic"
            elif passenger_count > 50:
                popularity = "🟡 Medium Traffic"
            else:
                popularity = "🟢 Low Traffic"
            st.write(f"**Traffic Level:** {popularity}")
        else:
            st.write("*No data available for this time*")

        st.subheader("📏 Gate Information")
        st.write(f"**Estimated Gate Distance:** {gate_distance_feet} feet")
        st.write(f"**Walking Time to Gate:** ~{gate_distance_minutes} minutes")
        st.write(f"**Lounge Time After Activity:** {max(0, activity_duration - actual_lounge_time):.1f} hours")

    st.divider()

    st.subheader("🤖 AI Recommendation")
    st.info(ai_recommendation)

    st.divider()

    # Summary box
    st.success(f"""
    ✅ **Your Departure Plan:**
    - Leave home at **{home_departure_time.strftime('%H:%M')}**
    - Spend **{actual_lounge_time:.1f} hours** enjoying {activity.lower()}
    - Arrive at gate by **{gate_arrival_time.strftime('%H:%M')}** for your **{destination}** flight
    """)

else:
    st.info("👈 Fill in your flight details in the sidebar and click 'Calculate Departure Time' to get started!")
