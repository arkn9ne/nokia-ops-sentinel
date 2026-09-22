import streamlit as st
import pandas as pd
import plotly.express as px
import os
import glob
import re
import datetime

# --- PAGE CONFIGURATION & STYLING ---
st.set_page_config(page_title="Nokia Ops Sentinel", page_icon="🏭", layout="wide")

# Custom CSS for Nokia-inspired styling (flowing gradient, clean cards)
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #001133 0%, #124191 50%, #001133 100%);
        background-attachment: fixed;
        color: #ffffff;
    }
    /* Style metrics and charts to look like elevated cards */
    div[data-testid="stMetric"], div[data-testid="stDataFrame"], .js-plotly-plot {
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 15px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    h1, h2, h3 {
        font-weight: 300 !important;
        letter-spacing: 0.5px;
    }
</style>
""", unsafe_allow_html=True)

# --- PASSWORD AUTHENTICATION GATE ---
def check_password():
    def password_entered():
        try:
            correct_password = st.secrets.get("APP_PASSWORD")
        except Exception:
            correct_password = None

        if correct_password is None:
            st.error("⛔ Security configuration error: Password secret is missing. Access denied.")
            return

        if st.session_state["password_input"] == correct_password:
            st.session_state["password_correct"] = True
            del st.session_state["password_input"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.title("🔒 Nokia Ops Sentinel: Authenticate")
        st.markdown("This dashboard contains restricted production tracking data.")
        st.text_input("Enter Access Password:", type="password", on_change=password_entered, key="password_input")
        return False
    elif not st.session_state["password_correct"]:
        st.title("🔒 Nokia Ops Sentinel: Authenticate")
        st.text_input("Enter Access Password:", type="password", on_change=password_entered, key="password_input")
        st.error("⛔ Incorrect password. Please try again.")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ==============================================================================
# MAIN DASHBOARD
# ==============================================================================

st.title("🏭 Nokia Ops Sentinel: Zero-Friction Command Center")

# --- HELPER: STATION CLASSIFICATION ---
def classify_process(proc_name):
    p = str(proc_name).strip().upper()
    if '5DX' in p or 'AXI' in p or 'X-RAY' in p or 'XRAY' in p:
        return '5DX'
    elif 'AOI' in p or 'AOR' in p or 'INSPECT SMT' in p or 'PBA INSPECT' in p or 'PAIRED BRD' in p:
        return 'AOI'
    elif 'DEBUG' in p or 'REPAIR' in p or ('RWK' in p and '5DX' not in p):
        return 'Debug / Repair'
    elif 'TEST' in p or 'DUT' in p or 'FUNCTIONAL' in p:
        return 'Functional Test'
    elif 'ASSY' in p or 'ASSEMBLY' in p or 'SMT' in p:
        return 'Assembly'
    else:
        return 'Other Inspection / Ops'

# --- HELPER: DATE EXTRACTION FROM FILENAME ---
def extract_date_from_filename(filename):
    match = re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{2})', filename)
    if match:
        try:
            return pd.to_datetime(match.group(1), format='%d-%b-%y')
        except Exception:
            pass
    return pd.NaT

# --- AUTOMATED FOLDER LOADER WITH CACHING ---
@st.cache_data(ttl=3600)
def load_all_reports_from_folder(folder_path="./data"):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        
    excel_files = glob.glob(os.path.join(folder_path, "*.xlsx")) + glob.glob(os.path.join(folder_path, "*.xls"))
    if not excel_files:
        return None, []

    combined_dfs = []
    loaded_filenames = []

    for filepath in excel_files:
        try:
            filename = os.path.basename(filepath)
            xls = pd.ExcelFile(filepath)
            if 'Shop Order' in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name='Shop Order')
                
                snapshot_date = extract_date_from_filename(filename)
                if pd.isna(snapshot_date):
                    snapshot_date = pd.to_datetime(os.path.getmtime(filepath), unit='s').normalize()
                else:
                    snapshot_date = snapshot_date.normalize()

                df['Snapshot Date'] = snapshot_date
                
                for col in df.select_dtypes(include=['datetime', 'datetime64']).columns:
                    if col != 'Snapshot Date':
                        df[col] = df[col].astype(str)
                    
                df['Station Group'] = df['Process'].apply(classify_process)
                df['Qty'] = pd.to_numeric(df['Qty'], errors='coerce').fillna(1) if 'Qty' in df.columns else 1
                
                combined_dfs.append(df)
                loaded_filenames.append(filename)
        except Exception:
            pass

    if combined_dfs:
        master = pd.concat(combined_dfs, ignore_index=True).fillna("N/A")
        master = master.sort_values(by='Snapshot Date', ascending=True)
        return master, loaded_filenames
    return None, []

master_df, loaded_files = load_all_reports_from_folder()

st.sidebar.header("⚙️ Data Sync Status")
if loaded_files:
    st.sidebar.success(f"⚡ Loaded {len(loaded_files)} report(s).")
else:
    st.sidebar.warning("No files found in `./data` folder.")

if st.sidebar.button("🔒 Lock Dashboard"):
    st.session_state["password_correct"] = False
    st.rerun()

# --- RENDER DASHBOARD ---
if master_df is not None:
    # Get chronological dates
    available_dates = master_df['Snapshot Date'].dt.date.unique()
    available_dates.sort()
    latest_date = available_dates[-1]

    # Mode Selector
    mode = st.radio(
        "Select Perspective:",
        ["🟢 LIVE Status (Latest Snapshot)", "📈 Historical Station Trends"],
        horizontal=True
    )

    # MODE 1: LIVE STATUS
    if mode == "🟢 LIVE Status (Latest Snapshot)":
        st.caption(f"Showing live floor snapshot from **{latest_date.strftime('%b %d, %Y')}**")
        
        # Filter to the latest date
        live_df = master_df[master_df['Snapshot Date'].dt.date == latest_date].copy()

        # Filters
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            all_programs = sorted([p for p in live_df['Program'].unique() if p != "N/A"])
            selected_programs = st.multiselect("Filter Program:", all_programs, default=all_programs)
        
        with filter_col2:
            # Safely check for Type column, otherwise use a placeholder or skip
            if 'Type' in live_df.columns:
                all_types = sorted([t for t in live_df['Type'].unique() if t != "N/A"])
                selected_types = st.multiselect("Filter Type (PA, TRX, etc.):", all_types, default=all_types)
            else:
                st.info("No 'Type' column detected in dataset.")
                selected_types = None

        # Apply Filters
        filtered_live = live_df[live_df['Program'].isin(selected_programs)]
        if 'Type' in live_df.columns and selected_types is not None:
            filtered_live = filtered_live[filtered_live['Type'].isin(selected_types)]

        # Metrics
        total_wip = filtered_live['Qty'].sum()
        aoi_count = filtered_live[filtered_live['Station Group'] == 'AOI']['Qty'].sum()
        fdx_count = filtered_live[filtered_live['Station Group'] == '5DX']['Qty'].sum()
        debug_count = filtered_live[filtered_live['Station Group'] == 'Debug / Repair']['Qty'].sum()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("📦 Live Total WIP", f"{int(total_wip):,} units")
        m2.metric("🔍 Live AOI Load", f"{int(aoi_count):,} units")
        m3.metric("⚡ Live 5DX Load", f"{int(fdx_count):,} units")
        m4.metric("🛠️ Live Debug / Repair", f"{int(debug_count):,} units")

        c1, c2 = st.columns(2)
        with c1:
            fig_live_proc = px.bar(filtered_live, x="Program", y="Qty", color="Station Group", title="Live Station Distribution", height=420, color_discrete_sequence=px.colors.qualitative.Prism)
            fig_live_proc.update_layout(barmode='stack', plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color="white")
            st.plotly_chart(fig_live_proc, use_container_width=True)

        with c2:
            wo_sum = filtered_live.groupby(['Work order', 'Program'])['Qty'].sum().reset_index().sort_values(by='Qty', ascending=False).head(10)
            fig_wo = px.bar(wo_sum, x="Qty", y="Work order", color="Program", orientation='h', title="Top 10 Work Orders", height=420, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_wo.update_layout(yaxis={'categoryorder':'total ascending'}, plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color="white")
            st.plotly_chart(fig_wo, use_container_width=True)

    # MODE 2: HISTORICAL TRENDS
    elif mode == "📈 Historical Station Trends":
        st.subheader("📊 Factory Backlog Trajectory")
        
        if len(available_dates) > 1:
            date_range = st.slider(
                "Select Date Range",
                min_value=available_dates[0],
                max_value=available_dates[-1],
                value=(available_dates[0], available_dates[-1]),
                format="MMM DD, YYYY"
            )
            start_date, end_date = date_range
        else:
            st.info("Only one day of data available. Slider disabled.")
            start_date, end_date = available_dates[0], available_dates[0]

        # Filter master data based on date slider
        mask = (master_df['Snapshot Date'].dt.date >= start_date) & (master_df['Snapshot Date'].dt.date <= end_date)
        history_df = master_df.loc[mask]

        trend_df = history_df.groupby(['Snapshot Date', 'Station Group'])['Qty'].sum().reset_index()
        
        # Create user-friendly date strings for the charts/tables
        trend_df['Date Str'] = trend_df['Snapshot Date'].dt.strftime('%b %d')

        fig_area = px.area(
            trend_df, x="Date Str", y="Qty", color="Station Group", 
            title=f"Total Factory Backlog ({start_date.strftime('%b %d')} to {end_date.strftime('%b %d')})", 
            height=500, color_discrete_sequence=px.colors.qualitative.Bold
        )
        # Force the x-axis to respect chronological order, not alphabetical string order
        chronological_date_strs = trend_df.drop_duplicates('Snapshot Date').sort_values('Snapshot Date')['Date Str'].tolist()
        fig_area.update_xaxes(categoryorder='array', categoryarray=chronological_date_strs)
        fig_area.update_layout(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font_color="white", xaxis_title="Date", yaxis_title="WIP Quantity")
        
        st.plotly_chart(fig_area, use_container_width=True)

        st.subheader("📋 Historical Matrix")
        # Format dates nicely for the table columns
        history_df['Date Str'] = history_df['Snapshot Date'].dt.strftime('%b %d')
        pivot_history = history_df.pivot_table(index='Station Group', columns='Date Str', values='Qty', aggfunc='sum', fill_value=0)
        
        # Reorder matrix columns strictly by chronological date
        ordered_cols = [col for col in chronological_date_strs if col in pivot_history.columns]
        pivot_history = pivot_history[ordered_cols]
        
        st.dataframe(pivot_history, use_container_width=True)

else:
    st.info("👋 Welcome! Place your RF8 `.xlsx` report files inside the `data` folder of your project to populate the dashboard automatically.")