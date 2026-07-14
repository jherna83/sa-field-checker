import streamlit as st
import pandas as pd
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from streamlit_gsheets_connection import GSheetsConnection
import datetime
import time

# 1. Page Configuration
st.set_page_config(page_title="SA Field Supervisor", layout="centered")

st.title("🏗️ SA Field Check Router")
st.markdown("---")

# 2. Database Connection (Google Sheets)
# This uses the URL you placed in the Streamlit Secrets
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. Sidebar Configuration
with st.sidebar:
    st.header("📍 Route Settings")
    start_addr = st.text_input("My Starting Address", "San Antonio, TX")
    
    st.header("📂 Data Upload")
    uploaded_file = st.file_uploader("Upload Daily Street Sheet (CSV)", type="csv")
    
    st.divider()
    st.info("Note: All addresses are assumed to be in San Antonio, TX.")

# 4. Helper Functions
def geocode_address(addr):
    """Converts street address to Lat/Lon with San Antonio context."""
    geolocator = Nominatim(user_agent="sa_supervisor_field_tool_v2")
    try:
        full_query = f"{addr}, San Antonio, TX"
        location = geolocator.geocode(full_query, timeout=10)
        if location:
            return (location.latitude, location.longitude)
        return (None, None)
    except Exception as e:
        return (None, None)

# 5. Main App Logic
if uploaded_file:
    # Read the CSV
    try:
        raw_df = pd.read_csv(uploaded_file)
        
        # Clean Data & Handle Duplicate Project Labels (Stop 1, Stop 2)
        raw_df['Project #'] = raw_df['Project #'].fillna("Unknown Project")
        raw_df['Contractor'] = raw_df['Contractor'].fillna("Unknown Contractor")
        raw_df['PRG - Construction Manager'] = raw_df['PRG - Construction Manager'].fillna("Unknown CM")
        
        # Group duplicates and label them
        raw_df['Stop_Count'] = raw_df.groupby('Project #').cumcount() + 1
        raw_df['Display_Name'] = raw_df.apply(lambda x: f"{x['Project #']} (Stop {x['Stop_Count']})", axis=1)

        # BUTTON: Optimize and Map
        if st.button("🗺️ Optimize Route"):
            with st.spinner("Mapping sites and calculating shortest path..."):
                # Geocode starting point
                start_lat, start_lon = geocode_address(start_addr)
                if start_lat is None:
                    st.error("Could not find your starting address. Please be more specific.")
                else:
                    # Geocode all sites from the CSV
                    # We use the 'Starting Address' column from your CSV
                    raw_df['lat'], raw_df['lon'] = zip(*raw_df['Starting Address'].apply(geocode_address))
                    df_mapped = raw_df.dropna(subset=['lat'])
                    
                    # Optimization: Nearest Neighbor Algorithm
                    ordered_route = []
                    current_pos = (start_lat, start_lon)
                    remaining_points = df_mapped.to_dict('records')
                    
                    while remaining_points:
                        # Find the stop closest to where we currently are
                        next_stop = min(remaining_points, key=lambda x: geodesic(current_pos, (x['lat'], x['lon'])).miles)
                        ordered_route.append(next_stop)
                        # Move our current position to this new stop
                        current_pos = (next_stop['lat'], next_stop['lon'])
                        remaining_points.remove(next_stop)
                    
                    # Store in session state so it doesn't disappear on refresh
                    st.session_state.route = ordered_route
                    st.success(f"Optimized route for {len(ordered_route)} locations!")

        # 6. Displaying the Route Cards
        if 'route' in st.session_state:
            st.subheader("Your Schedule Today")
            
            for i, stop in enumerate(st.session_state.route):
                with st.container(border=True):
                    # Title Row
                    st.markdown(f"### {i+1}. {stop['Display_Name']}")
                    st.write(f"**Contractor:** {stop['Contractor']} | **CM:** {stop['PRG - Construction Manager']}")
                    
                    # Detail Expander
                    with st.expander("📝 View Details & Crew Info"):
                        st.write(f"**Lead:** {stop['Crew Lead']} ({stop['Crew Lead Phone #']})")
                        st.write(f"**Work:** {stop['Work Type']}")
                        st.write(f"**Permit:** {stop['Permit #']}")
                        st.write(f"**Site Range:** {stop['Starting Address']} to {stop['Ending Address']}")

                    # Action Buttons
                    col_nav, col_save = st.columns([1, 1])
                    
                    with col_nav:
                        # Google Maps Link
                        gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={stop['lat']},{stop['lon']}"
                        st.link_button("🚗 Navigate", gmaps_url, use_container_width=True)
                    
                    # Notes Section
                    note_key = f"note_input_{i}"
                    user_note = st.text_area("Field Observations", key=note_key, placeholder="Enter site notes here...")
                    
                    if st.button("✅ Log Visit & Note", key=f"btn_{i}", use_container_width=True):
                        # Data for Google Sheets
                        new_log = pd.DataFrame([{
                            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "Project_ID": stop['Display_Name'],
                            "Contractor": stop['Contractor'],
                            "Status": "Visited",
                            "Notes": user_note
                        }])
                        
                        try:
                            # 1. Read existing data
                            existing_df = conn.read()
                            # 2. Add new row
                            updated_df = pd.concat([existing_df, new_log], ignore_index=True)
                            # 3. Push back to Google Sheets
                            conn.update(data=updated_df)
                            st.toast(f"Logged {stop['Project #']}!", icon="✅")
                        except Exception as e:
                            st.error(f"Sync Error: {e}")

            # 7. Final Download
            st.divider()
            if st.button("💾 Download Daily Log Backup"):
                final_csv = pd.DataFrame(st.session_state.route).to_csv(index=False)
                st.download_button("Download CSV", data=final_csv, file_name=f"Route_Log_{datetime.date.today()}.csv")

    except Exception as e:
        st.error(f"Error processing CSV: {e}")
else:
    st.info("Please upload your 'Daily Street Sheet' CSV in the sidebar to begin.")
