"""
Mom's Apartments Map App
Upload Excel, view apartments on a map with floor plan links.
"""
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode
import os
import base64
import tempfile

st.set_page_config(page_title="Mom's Apartments Map", layout="wide")
st.title("Mom's Apartments Map")


# Geocoding: Nominatim first, ArcGIS as fallback (both free, no API key)
@st.cache_resource
def get_geocoders():
    nominatim = RateLimiter(Nominatim(user_agent="moms_apartments_map", timeout=10).geocode, min_delay_seconds=1.1)
    from geopy.geocoders import ArcGIS
    arcgis = RateLimiter(ArcGIS(timeout=10).geocode, min_delay_seconds=0.5)
    return nominatim, arcgis

CITY = "תל אביב"  # Tel Aviv - all addresses are here

def geocode_address(address: str, geocode_nominatim, geocode_arcgis):
    """Convert address to (lat, lon). Tries Nominatim, then ArcGIS."""
    query = str(address).strip()
    if CITY not in query and "Tel Aviv" not in query.lower():
        query = f"{query}, {CITY}"
    if "Israel" not in query and "ישראל" not in query:
        query = f"{query}, Israel"
    for geocode in [geocode_nominatim, geocode_arcgis]:
        try:
            result = geocode(query)
            if result:
                return (result.latitude, result.longitude)
        except Exception:
            pass
    return None

# ---- Upload ----
st.sidebar.header("Data")
excel_file = st.sidebar.file_uploader("Upload Excel file", type=["xlsx", "xls"])
pdf_folder = st.sidebar.text_input("PDF folder path (optional)", placeholder="e.g. data/pdfs")
# Auto-detect when deployed: use data/pdfs or pdfs if they exist and user left blank
if not pdf_folder or not pdf_folder.strip():
    for cand in ["data/pdfs", "pdfs"]:
        if os.path.isdir(cand):
            pdf_folder = cand
            break

# Upload PDFs (select all in folder—Ctrl+A). Loaded only when you open "View Floor Plan".
pdf_uploads = st.sidebar.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True, help="Select all PDFs from your folder. Loaded only when you click to view.")
if pdf_uploads:
    st.sidebar.caption(f"✓ {len(pdf_uploads)} PDFs ready")

# Map layer (cached—persists across reruns)
if "map_layer" not in st.session_state:
    st.session_state["map_layer"] = "Street"
layer_options = ["Street", "Satellite", "Terrain", "Google Street", "Google Satellite"]
_idx = layer_options.index(st.session_state["map_layer"]) if st.session_state["map_layer"] in layer_options else 0
map_layer = st.sidebar.radio("Map layer", layer_options, index=_idx, key="map_layer_radio")
st.session_state["map_layer"] = map_layer

# Address column: "כתובת-מיקום" if present, else column D (index 3)
def _get_address_col(df: pd.DataFrame, from_col_d: bool = False) -> str:
    if "כתובת-מיקום" in df.columns:
        return "כתובת-מיקום"
    return df.columns[0] if from_col_d else (df.columns[3] if len(df.columns) > 3 else df.columns[0])

# Use dummy data if no upload
from_col_d = False
if excel_file is None:
    dummy_path = "data/apartments.xlsx"
    if os.path.exists(dummy_path):
        df = pd.read_excel(dummy_path)
        st.sidebar.info(f"Using dummy data: {len(df)} apartments")
    else:
        st.warning("No Excel file uploaded. Run `python create_dummy_data.py` to generate dummy data, or upload an Excel file.")
        st.stop()
else:
    df_full = pd.read_excel(excel_file, sheet_name="דירוג", header=0)
    df = df_full.iloc[:, 3:]  # columns D onwards (skip A,B,C)
    from_col_d = True
    st.sidebar.success(f"Loaded {len(df)} apartments")

# Resolve address column: כתובת-מיקום or column D
address_col = _get_address_col(df, from_col_d)

# ---- Geocode addresses (cached—runs once per set of addresses) ----
unique_addresses = [str(a).strip() for a in df[address_col].dropna().unique().tolist() if a and str(a).strip()]

@st.cache_data(ttl=86400)
def _geocode_all(addresses: tuple) -> dict:
    geocode_nom, geocode_arc = get_geocoders()
    coords = {}
    for addr in addresses:
        latlon = geocode_address(addr, geocode_nom, geocode_arc)
        coords[addr] = latlon
    return coords

with st.spinner("Geocoding addresses (only on first load)…"):
    coords = _geocode_all(tuple(unique_addresses))

# Filter to addresses we could geocode
geocoded = {a: c for a, c in coords.items() if c is not None}
failed = [a for a, c in coords.items() if c is None]
if failed:
    st.warning(f"Could not geocode: {', '.join(failed[:3])}{'...' if len(failed) > 3 else ''}")

if not geocoded:
    st.error("No addresses could be geocoded. Check that addresses include city (e.g. 'Tel Aviv').")
    st.stop()

# ---- Detect column types (for AgGrid filter config) ----
def _is_numeric(col_name: str) -> bool:
    if col_name not in df.columns:
        return False
    return pd.api.types.is_integer_dtype(df[col_name]) or pd.api.types.is_float_dtype(df[col_name])

filter_cols = [c for c in df.columns if c != "Floor Plan PDF" and "PDF" not in c]
numeric_cols = [c for c in filter_cols if _is_numeric(c)]

# ---- Table with Excel-style column filters (must run first to get filtered_df for map) ----
st.subheader("All Apartments")
st.caption("Click a column header to filter. Filters apply to both the map and table.")

gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_default_column(filterable=True)
for col in df.columns:
    if col in numeric_cols:
        gb.configure_column(col, filter="agNumberColumnFilter", filterParams={"buttons": ["apply", "reset"]})
    else:
        gb.configure_column(col, filter="agSetColumnFilter", filterParams={"excelMode": "windows"})
grid_opts = gb.build()

grid_return = AgGrid(
    df,
    gridOptions=grid_opts,
    data_return_mode=DataReturnMode.FILTERED,
    update_mode=GridUpdateMode.FILTERING_CHANGED,
    fit_columns_on_grid_load=True,
    height=300,
)

filtered_df = grid_return["data"] if grid_return and "data" in grid_return else df
if filtered_df is None or filtered_df.empty:
    filtered_df = df

# ---- Build map (using filtered_df from table) ----
center = list(geocoded.values())[0]
_tile_map = {
    "Street": "OpenStreetMap",
    "Satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "Terrain": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    "Google Street": "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
    "Google Satellite": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
}
_default_tiles = _tile_map.get(st.session_state.get("map_layer", "Street"), "OpenStreetMap")
m = folium.Map(location=center, zoom_start=13, tiles=_default_tiles)

# Opaque popup + scrollable content
popup_css = """
.leaflet-popup-content-wrapper, .leaflet-popup-tip { background: white !important; opacity: 1 !important; }
.leaflet-popup-content { margin: 12px 16px !important; max-height: 280px !important; overflow-y: auto !important; }
"""
m.get_root().header.add_child(folium.Element(f"<style>{popup_css}</style>"))

# Additional tile layers
folium.TileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite",
).add_to(m)
folium.TileLayer(
    tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attr='&copy; <a href="https://opentopomap.org/">OpenTopoMap</a>',
    name="Terrain",
).add_to(m)
folium.TileLayer(
    tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
    attr="Google",
    name="Google Street",
).add_to(m)
folium.TileLayer(
    tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    attr="Google",
    name="Google Satellite",
).add_to(m)
folium.LayerControl(position="topright").add_to(m)

# Attributes to show in popup (exclude PDF path, address—it's the popup title); columns with "ציון" last
base_cols = [c for c in df.columns if c not in ["Floor Plan PDF", "Address", address_col] and "PDF" not in c]
info_cols = [c for c in base_cols if "ציון" not in c] + [c for c in base_cols if "ציון" in c]

# Home icon for markers (DivIcon with emoji - works without external fonts)
home_icon = folium.DivIcon(
    html='<div style="font-size: 28px; line-height: 1;">🏠</div>',
    icon_size=(28, 28),
    icon_anchor=(14, 14),
)

# Only show markers for addresses that have filtered apartments
for addr, (lat, lon) in geocoded.items():
    units = filtered_df[filtered_df[address_col] == addr]
    if units.empty:
        continue

    popup_parts = [f"<b>{addr}</b><hr style='margin:8px 0'>"]
    for i, (_, row) in enumerate(units.iterrows()):
        if i > 0:
            popup_parts.append("<hr style='margin:14px 0; border: none; border-top: 2px solid #333'>")
        unit_lines = []
        for col in info_cols:
            if col in row.index and pd.notna(row[col]):
                display_name = col.rstrip(':') if isinstance(col, str) else col
                val = row[col]
                val_html = f"<b>{val}</b>" if isinstance(col, str) and "ציון" in col else str(val)
                unit_lines.append(f"<tr><td style='padding:2px 8px 2px 0;vertical-align:top'><b>{display_name}:</b></td><td>{val_html}</td></tr>")
        unit_html = f"<table style='margin-bottom:4px'>{''.join(unit_lines)}</table>"
        popup_parts.append(unit_html)

    n_units = len(units)
    score_col = None
    for c in units.columns:
        if isinstance(c, str) and "ציון" in c and ("סהכ" in c or 'סה"כ' in c):
            score_col = c
            break
    if score_col is None:
        tzion_cols = [c for c in units.columns if isinstance(c, str) and "ציון" in c]
        score_col = tzion_cols[-1] if tzion_cols else None
    scores = []
    if score_col and score_col in units.columns:
        for v in units[score_col].dropna():
            scores.append(str(v))
    units_part = f" ({n_units} units)" if n_units > 1 else ""
    score_str = f" | <b>סהכ ציון</b> <b>{', '.join(scores)}</b>" if scores else ""
    html = "".join(popup_parts)
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(html, max_width=350),
        tooltip=folium.Tooltip(f"{addr}{units_part}{score_str}", sticky=True),
        icon=home_icon,
    ).add_to(m)

# ---- Render map (full width, large) ----
map_height = 700
map_data = st_folium(m, height=map_height, use_container_width=True, returned_objects=["last_object_clicked", "last_clicked"])

# Download standalone HTML (send to anyone—they open in browser, no app needed)
with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
    tmp.close()
    try:
        m.save(tmp.name)
        with open(tmp.name, "rb") as f:
            html_bytes = f.read()
        st.sidebar.download_button("📥 Download HTML map", html_bytes, file_name="apartments_map.html", mime="text/html", help="Standalone file—send to anyone, they open in a browser")
    finally:
        os.unlink(tmp.name)

def _dist(c1, c2):
    """Simple distance between (lat,lon) points."""
    return (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2

# Find which address was clicked (nearest marker)
clicked_addr = None
click_data = map_data.get("last_object_clicked") or map_data.get("last_clicked")
if click_data and "lat" in click_data and "lng" in click_data:
    clat, clng = click_data["lat"], click_data["lng"]
    best_addr, best_d = None, float("inf")
    for addr, (lat, lon) in geocoded.items():
        d = _dist((clat, clng), (lat, lon))
        if d < best_d:
            best_d, best_addr = d, addr
    clicked_addr = best_addr

# ---- Floor plan panel (PDF loaded only when she opens "View Floor Plan") ----
def _get_pdf_bytes(pdf_path: str, pdf_uploads: list) -> bytes | None:
    """Get PDF bytes from uploads (by filename) or folder. Loaded on demand only."""
    filename = os.path.basename(pdf_path)
    cache_key = f"_pdf_{filename}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    for f in (pdf_uploads or []):
        if f.name == filename:
            data = f.read()
            st.session_state[cache_key] = data
            return data
    if pdf_folder and os.path.isdir(pdf_folder):
        full = os.path.join(pdf_folder, filename)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                return f.read()
    return None

if clicked_addr:
    units_at_addr = filtered_df[filtered_df[address_col] == clicked_addr]
    pdf_col = "Floor Plan PDF" if "Floor Plan PDF" in df.columns else None
    has_source = ((pdf_uploads and len(pdf_uploads) > 0) or (pdf_folder and os.path.isdir(pdf_folder))) and pdf_col

    if has_source:
        st.subheader("Floor plans")
        for _, row in units_at_addr.iterrows():
            if pdf_col in row.index and pd.notna(row[pdf_col]):
                pdf_path = str(row[pdf_col])
                pdf_filename = os.path.basename(pdf_path)
                unit_label = row.get("Unit", "")
                load_key = f"_loaded_{clicked_addr}_{unit_label}".replace(" ", "_")
                with st.expander(f"⊕ {unit_label} — View Floor Plan", expanded=False):
                    if st.session_state.get(load_key):
                        with st.spinner("Loading floor plan…"):
                            pdf_bytes = _get_pdf_bytes(pdf_path, pdf_uploads or [])
                        if pdf_bytes:
                            try:
                                b64 = base64.b64encode(pdf_bytes).decode()
                                pdf_html = f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="500" type="application/pdf"></iframe>'
                                st.markdown(pdf_html, unsafe_allow_html=True)
                            except Exception as e:
                                st.caption(f"Could not display PDF: {e}")
                        else:
                            st.caption(f"PDF not found: `{pdf_filename}`")
                    elif st.button("Show floor plan", key=load_key):
                        st.session_state[load_key] = True
                        st.rerun()

# Table is the AgGrid above; filtered_df drives map and floor plans
