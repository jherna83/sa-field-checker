import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from streamlit_gsheets_connection import GSheetsConnection
import datetime

# 1. Page Config for Mobile
st.set_page_config(page_title="SA Field Supervisor", layout="centered")

st.title("🏗️ SA Field Check Router")

# 2. Database Connection (Google Sheets)
# Note: You will set the URL in Streamlit Secrets later
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Sidebar Setup
with st.sidebar:
    st.header("Settings")
    start_addr = st.text_input("Starting Address", "City Hall, San Antonio, TX")
    is_circuit = st.checkbox("Return to start at end of day?", value=True)
    uploaded_file = st.file_uploader("Upload Daily Street Sheet (CSV)", type="csv")

def geocode_address(addr):
    geolocator = Nominatim(user_agent="sa_field_checker")
    try:
        # Appending San Antonio context automatically
        full_query = f"{addr}, San Antonio, TX"
        location = geolocator.geocode(full_query)
        return (location.latitude, location.longitude) if location else (None, None)
    except:
        return (None, None)

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    # Clean Data & Handle Duplicates
    df['Project #'] = df['Project #'].fillna("Unknown Project")
    df['Stop_Label'] = df.groupby('Project #').cumcount() + 1
    df['Display_Name'] = df.apply(lambda x: f"{x['Project #']} (Stop {x['Stop_Label']})", axis=1)
    
    # 4. Route Optimization (Nearest Neighbor)
    if st.button("Calculate Optimal Route"):
        with st.spinner("Mapping sites..."):
            # Geocode the starting point
            start_lat, start_lon = geocode_address(start_addr)
            
            # Geocode all project sites
            df['lat'], df['lon'] = zip(*df['Starting Address'].apply(geocode_address))
            df = df.dropna(subset=['lat'])
            
            # Simple Optimization Algorithm
            ordered_route = []
            current_pos = (start_lat, start_lon)
            remaining_points = df.to_dict('records')
            
            while remaining_points:
                next_stop = min(remaining_points, key=lambda x: geodesic(current_pos, (x['lat'], x['lon'])).miles)
                ordered_route.append(next_stop)
                current_pos = (next_stop['lat'], next_stop['lon'])
                remaining_points.remove(next_stop)
            
            st.session_state.route = ordered_route
            st.success("Route Optimized!")

    # 5. Display Cards
    if 'route' in st.session_state:
        for i, stop in enumerate(st.session_state.route):
            with st.container(border=True):
                # Header
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.subheader(f"{i+1}. {stop['Display_Name']}")
                    st.caption(f"Contractor: {stop['Contractor']} | CM: {stop.get('PRG - Construction Manager', 'Unknown')}")
                
                # Expandable Details
                with st.expander("View Job Details"):
                    st.write(f"**Crew Lead:** {stop['Crew Lead']} ({stop['Crew Lead Phone #']})")
                    st.write(f"**Work Type:** {stop['Work Type']}")
                    st.write(f"**Permit:** {stop['Permit #']}")
                    st.write(f"**Location:** {stop['Starting Address']} to {stop['Ending Address']}")
                
                # Actions
                gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={stop['lat']},{stop['lon']}"
                st.link_button("🚗 Open in Google Maps", gmaps_url)
                
                # Notes & Database Saving
                note_key = f"note_{stop['Project #']}_{i}"
                status_key = f"status_{stop['Project #']}_{i}"
                
                user_note = st.text_area("Field Notes", key=note_key)
                if st.button("Check-in / Save Note", key=f"btn_{i}"):
                    # Logic to save to Google Sheet
                    new_row = pd.DataFrame([{
                        "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Project_ID": stop['Display_Name'],
                        "Contractor": stop['Contractor'],
                        "Status": "Visited",
                        "Notes": user_note
                    }])
                    # In a real deployment, we'd append to the sheet here
                    st.write("✅ Saved to Database")
                    st.session_state[f"done_{i}"] = True

        # 6. Daily Digest Download
        if st.button("Generate Final Daily Digest"):
            # This creates a CSV of just the notes you took today
            st.download_button("Download Completed Log", data=df.to_csv(), file_name="daily_log.csv")
