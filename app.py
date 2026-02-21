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

def geocode_address(address: str, geocode_nominatim, geocode_arcgis):
    """Convert address to (lat, lon). Tries Nominatim, then ArcGIS."""
    # Ensure Israel is in the query for better results
    query = str(address).strip()
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

# Use dummy data if no upload
if excel_file is None:
    dummy_path = "data/apartments.xlsx"
    if os.path.exists(dummy_path):
        df = pd.read_excel(dummy_path)
        st.sidebar.info(f"Using dummy data: {len(df)} apartments")
    else:
        st.warning("No Excel file uploaded. Run `python create_dummy_data.py` to generate dummy data, or upload an Excel file.")
        st.stop()
else:
    df = pd.read_excel(excel_file)
    st.sidebar.success(f"Loaded {len(df)} apartments")

# Ensure required columns exist
required = ["Address", "Price"]
for col in required:
    if col not in df.columns:
        st.error(f"Excel must have a '{col}' column.")
        st.stop()

# ---- Geocode addresses ----
geocode_nom, geocode_arc = get_geocoders()
address_col = "Address"

# Get unique addresses
unique_addresses = df[address_col].dropna().unique().tolist()

with st.spinner("Geocoding addresses..."):
    coords = {}
    for addr in unique_addresses:
        if addr and str(addr).strip():
            latlon = geocode_address(str(addr), geocode_nom, geocode_arc)
            coords[addr] = latlon

# Filter to addresses we could geocode
geocoded = {a: c for a, c in coords.items() if c is not None}
failed = [a for a, c in coords.items() if c is None]
if failed:
    st.warning(f"Could not geocode: {', '.join(failed[:3])}{'...' if len(failed) > 3 else ''}")

if not geocoded:
    st.error("No addresses could be geocoded. Check that addresses include city (e.g. 'Tel Aviv').")
    st.stop()

# ---- Build map ----
# Center on first geocoded point or Tel Aviv
center = list(geocoded.values())[0]
m = folium.Map(location=center, zoom_start=13, tiles="OpenStreetMap")

# Opaque popup + scrollable content
popup_css = """
.leaflet-popup-content-wrapper, .leaflet-popup-tip { background: white !important; opacity: 1 !important; }
.leaflet-popup-content { margin: 12px 16px !important; max-height: 280px !important; overflow-y: auto !important; }
"""
m.get_root().header.add_child(folium.Element(f"<style>{popup_css}</style>"))

# Additional tile layers: Satellite, Terrain (Google Maps-style layer switcher)
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
folium.LayerControl(position="topright").add_to(m)

# Attributes to show in popup (exclude PDF path for display)
info_cols = [c for c in df.columns if c not in ["Floor Plan PDF", "Address"] and "PDF" not in c]

# Home icon for markers (DivIcon with emoji - works without external fonts)
home_icon = folium.DivIcon(
    html='<div style="font-size: 28px; line-height: 1;">🏠</div>',
    icon_size=(28, 28),
    icon_anchor=(14, 14),
)

for addr, (lat, lon) in geocoded.items():
    units = df[df[address_col] == addr]

    popup_parts = [f"<b>{addr}</b><hr style='margin:8px 0'>"]
    for _, row in units.iterrows():
        unit_lines = []
        for col in info_cols:
            if col in row.index and pd.notna(row[col]):
                unit_lines.append(f"<tr><td style='padding:2px 8px 2px 0;vertical-align:top'><b>{col}:</b></td><td>{row[col]}</td></tr>")
        unit_html = f"<table style='margin-bottom:10px'>{''.join(unit_lines)}</table>"
        popup_parts.append(unit_html)

    html = "".join(popup_parts)
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(html, max_width=350),
        tooltip=addr,
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
    units_at_addr = df[df[address_col] == clicked_addr]
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

# ---- Apartment list ----
st.subheader("All Apartments")
st.dataframe(df, use_container_width=True, hide_index=True)
