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
import html as html_module
import os
import re
import base64
import tempfile
import urllib.request
import urllib.parse
import urllib.error
import json

st.set_page_config(page_title="Mom's Apartments Map", layout="wide")


def _extract_drive_folder_id(url_or_id: str) -> str | None:
    """Extract folder ID from Google Drive URL or return as-is if it looks like an ID."""
    s = (url_or_id or "").strip()
    if not s:
        return None
    # Full URL: https://drive.google.com/drive/folders/1ABC123...
    m = re.search(r"/folders/([a-zA-Z0-9_-]{20,})", s)
    if m:
        return m.group(1)
    # https://drive.google.com/open?id=1ABC123
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]{20,})", s)
    if m:
        return m.group(1)
    # Bare ID (no slashes)
    if "/" not in s and len(s) >= 20:
        return s
    return None


def _list_drive_folder(api_key: str, folder_id: str) -> tuple[dict[str, str], str | None]:
    """List files in a Google Drive folder. Returns (filename->file_id, error_msg or None)."""
    try:
        q = urllib.parse.quote(f"'{folder_id}' in parents")
        url = f"https://www.googleapis.com/drive/v3/files?q={q}&key={api_key}&fields=files(id,name)"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        files = {f["name"]: f["id"] for f in data.get("files", [])}
        return files, None
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body)
        except Exception:
            msg = body or str(e)
        return {}, f"Drive API error ({e.code}): {msg}"
    except urllib.error.URLError as e:
        return {}, f"Network error: {e.reason}"
    except Exception as e:
        return {}, str(e)


def _download_drive_file(api_key: str, file_id: str) -> bytes | None:
    """Download a file from Google Drive by ID."""
    try:
        url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception:
        return None


def _find_drive_file_for_unit(files: dict[str, str], address: str, unit_index: int) -> tuple[str, str, str] | None:
    """
    Find Drive file by address + unit index. Address must match column D exactly.
    Files: address.pdf, address.jpeg, address.jpg | address_1.pdf for 2nd unit, etc.
    Returns (file_id, "pdf"|"image", filename) or None.
    """
    base = str(address).strip()  # Identical to column D
    exts = [".pdf", ".jpeg", ".jpg"]
    if unit_index == 0:
        for ext in exts:
            cand = base + ext
            if cand in files:
                return files[cand], "pdf" if ext == ".pdf" else "image", cand
    else:
        suffix = f"_{unit_index}"
        for ext in exts:
            cand = base + suffix + ext
            if cand in files:
                return files[cand], "pdf" if ext == ".pdf" else "image", cand
    return None
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

# PDF source: from secrets (deployed) or local/upload (dev)
def _get_drive_secrets():
    try:
        s = getattr(st, "secrets", None) or {}
        api_key = (s.get("GOOGLE_DRIVE_API_KEY") or os.environ.get("GOOGLE_DRIVE_API_KEY") or "").strip()
        folder_val = (s.get("GOOGLE_DRIVE_FOLDER_ID") or os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or "").strip()
        folder_id = _extract_drive_folder_id(folder_val) if folder_val else None
        return api_key, folder_id
    except Exception:
        return ("", None)

drive_api_key, drive_folder_id = _get_drive_secrets()
drive_configured = bool(drive_api_key and drive_folder_id)

pdf_folder = None
pdf_uploads = None

if drive_configured:
    st.sidebar.caption("✓ PDFs from Google Drive")
else:
    pdf_folder = st.sidebar.text_input("PDF folder path (optional)", placeholder="e.g. data/pdfs", key="pdf_folder")
    if not pdf_folder or not pdf_folder.strip():
        for cand in ["data/pdfs", "pdfs"]:
            if os.path.isdir(cand):
                pdf_folder = cand
                break
    pdf_uploads = st.sidebar.file_uploader("Upload PDFs", type=["pdf"], accept_multiple_files=True, help="Select all PDFs. Loaded when you view floor plan.", key="pdf_uploads")
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

# Require Excel upload
from_col_d = False
if excel_file is None:
    st.info("Please upload an Excel file.")
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
st.caption("Click a column header to filter, or click a row to view that apartment's floor plan (same as clicking its marker on the map).")

gb = GridOptionsBuilder.from_dataframe(df)
gb.configure_default_column(filterable=True)
gb.configure_selection("single", use_checkbox=False)
tzion_score_col = next((c for c in df.columns if isinstance(c, str) and "ציון" in c and ("סהכ" in c or 'סה"כ' in c)), None)
for col in df.columns:
    opts = {}
    if col in numeric_cols:
        opts["filter"] = "agNumberColumnFilter"
        opts["filterParams"] = {"buttons": ["apply", "reset"]}
    else:
        opts["filter"] = "agSetColumnFilter"
        opts["filterParams"] = {"excelMode": "windows"}
    if col == address_col:
        opts["minWidth"] = 280
    elif col == tzion_score_col:
        opts["minWidth"] = 120
    gb.configure_column(col, **opts)
grid_opts = gb.build()

grid_return = AgGrid(
    df,
    gridOptions=grid_opts,
    data_return_mode=DataReturnMode.FILTERED,
    update_mode=GridUpdateMode.FILTERING_CHANGED | GridUpdateMode.SELECTION_CHANGED,
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

# Opaque popup + scrollable content; RTL for Hebrew; dark text; highlight for selected marker
selected_addr = st.session_state.get("_clicked_addr") or ""
popup_css = """
.leaflet-popup-content-wrapper, .leaflet-popup-tip { background: white !important; opacity: 1 !important; }
.leaflet-popup-content { margin: 12px 16px !important; max-height: 450px !important; overflow-y: auto !important; direction: rtl !important; text-align: right !important; color: #333 !important; }
.leaflet-marker-icon.selected-marker { filter: drop-shadow(0 0 4px #0066ff) drop-shadow(0 0 8px #0066ff) !important; }
"""
m.get_root().header.add_child(folium.Element(f"<style>{popup_css}</style>"))
# Script applies highlight to selected marker (add to parent .leaflet-marker-icon); retry until map ready
highlight_script = f"""
<script>
(function() {{
  var sel = {json.dumps(selected_addr)};
  function apply() {{
    document.querySelectorAll('[data-addr]').forEach(function(el) {{
      var icon = el.closest('.leaflet-marker-icon');
      if (icon) icon.classList.remove('selected-marker');
      if (el.dataset.addr === sel) {{
        var icon = el.closest('.leaflet-marker-icon');
        if (icon) icon.classList.add('selected-marker');
      }}
    }});
  }}
  function run() {{ apply(); }}
  var attempts = 0;
  function tryApply() {{
    apply();
    if (document.querySelectorAll('[data-addr]').length === 0 && attempts++ < 20) setTimeout(tryApply, 100);
  }}
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function() {{ setTimeout(tryApply, 300); }});
  else setTimeout(tryApply, 300);
}})();
</script>
"""
m.get_root().header.add_child(folium.Element(highlight_script))

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

def _price_to_m(val):
    """Format price in millions: 6_000_000 → 6 מש״ח, 5_900_000 → 5.9 מש״ח. Below 1M stays as-is."""
    try:
        s = str(val).replace(",", "").replace(" ", "")
        num = float(s)
        if num >= 1_000_000:
            m = num / 1_000_000
            fmt = f"{m:.1f}".rstrip("0").rstrip(".")
            return f"{fmt} מש״ח"
        return str(val)
    except (ValueError, TypeError):
        return str(val)


def _build_popup_html(addr, units, drive_files, price_col, info_cols_main, info_cols_tzion):
    """Build popup HTML for an address and its units (same as map marker popup)."""
    popup_parts = ['<div style="color:#333">', f"<b>{addr}</b>"]
    if price_col and price_col in units.columns:
        prices = [_price_to_m(row[price_col]) for _, row in units.iterrows() if pd.notna(row.get(price_col))]
        if prices:
            price_label = price_col.rstrip(':') if isinstance(price_col, str) else "מחיר"
            popup_parts.append(f"<div style='margin:4px 0 8px 0'><b>{price_label}</b>: {', '.join(prices)}</div>")
    popup_parts.append("<hr style='margin:8px 0'>")
    for i, (_, row) in enumerate(units.iterrows()):
        if i > 0:
            popup_parts.append("<hr style='margin:14px 0; border: none; border-top: 2px solid #333'>")
        unit_lines = []
        for col in info_cols_main:
            if col in row.index and pd.notna(row[col]):
                display_name = col.rstrip(':') if isinstance(col, str) else col
                val = row[col]
                unit_lines.append(f"<tr><td style='padding:2px 8px 2px 0;vertical-align:top'><b>{display_name}:</b></td><td>{val}</td></tr>")
        unit_html = f"<table style='margin-bottom:4px'>{''.join(unit_lines)}</table>"
        popup_parts.append(unit_html)
        if info_cols_tzion:
            tzion_lines = []
            for col in info_cols_tzion:
                if col in row.index and pd.notna(row[col]):
                    display_name = col.rstrip(':') if isinstance(col, str) else col
                    val = row[col]
                    tzion_lines.append(f"<tr><td style='padding:2px 8px 2px 0;vertical-align:top'><b>{display_name}:</b></td><td><b>{val}</b></td></tr>")
            if tzion_lines:
                tzion_table = f"<table style='margin-top:4px'>{''.join(tzion_lines)}</table>"
                popup_parts.append(f"<details style='margin:4px 0'><summary style='cursor:pointer; font-size:12px'>הצג ציון</summary>{tzion_table}</details>")
        if drive_files:
            found = _find_drive_file_for_unit(drive_files, addr, i)
            if found:
                fid, _, _ = found
                preview_url = f"https://drive.google.com/file/d/{fid}/preview"
                view_url = f"https://drive.google.com/file/d/{fid}/view"
                popup_parts.append(
                    '<details style="margin:4px 0"><summary style="cursor:pointer; font-size:12px">הצג תוכנית</summary>'
                    f'<div style="margin:2px 0; padding:0">'
                    f'<iframe src="{preview_url}" width="100%" height="120" style="border:1px solid #ccc; border-radius:4px; margin:0" allow="autoplay"></iframe>'
                    f'<a href="{view_url}" target="_blank" rel="noopener" style="font-size:11px; display:block; margin-top:2px">View in new tab</a>'
                    f'</div></details>'
                )
    popup_parts.append("</div>")
    return "".join(popup_parts)


# Attributes to show in popup (exclude PDF path, address—it's the popup title)
# ציון columns shown separately in expandable section
base_cols = [c for c in df.columns if c not in ["Floor Plan PDF", "Address", address_col] and "PDF" not in c]
price_col = next((c for c in df.columns if isinstance(c, str) and ("מחיר" in c or c == "Price")), None)
base_cols_no_price = [c for c in base_cols if c != price_col] if price_col else base_cols
info_cols_main = [c for c in base_cols_no_price if "ציון" not in c]
info_cols_tzion = [c for c in base_cols_no_price if "ציון" in c]

def _make_icon(addr):
    esc = html_module.escape(str(addr))
    return folium.DivIcon(
        html=f'<div style="font-size: 28px; line-height: 1;" data-addr="{esc}">🏠</div>',
        icon_size=(28, 28),
        icon_anchor=(14, 14),
    )

# Pre-load Drive file list when configured
drive_files: dict[str, str] = {}
drive_error: str | None = None
if drive_configured and drive_api_key and drive_folder_id:
    list_key = f"_drive_list_{drive_folder_id}"
    if list_key not in st.session_state:
        files, err = _list_drive_folder(drive_api_key, drive_folder_id)
        st.session_state[list_key] = files
        st.session_state[list_key + "_err"] = err
    drive_files = st.session_state[list_key]
    drive_error = st.session_state.get(list_key + "_err")

# Only show markers for addresses that have filtered apartments
for addr, (lat, lon) in geocoded.items():
    units = filtered_df[filtered_df[address_col] == addr]
    if units.empty:
        continue

    html = _build_popup_html(addr, units, drive_files or {}, price_col, info_cols_main, info_cols_tzion)
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
    prices_tooltip = []
    if price_col and price_col in units.columns:
        for v in units[price_col].dropna():
            prices_tooltip.append(_price_to_m(v))
    units_part = f" ({n_units} units)" if n_units > 1 else ""
    score_str = f" | <b>סהכ ציון</b> <b>{', '.join(scores)}</b>" if scores else ""
    price_label = (price_col.rstrip(':') if isinstance(price_col, str) else "מחיר") if price_col else "מחיר"
    price_str = f" | <b>{price_label}</b> <b>{', '.join(prices_tooltip)}</b>" if prices_tooltip else ""
    folium.Marker(
        location=[lat, lon],
        popup=folium.Popup(html, max_width=350),
        tooltip=folium.Tooltip(f"{addr}{units_part}{price_str}{score_str}", sticky=True),
        icon=_make_icon(addr),
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

# Find which address was selected: from map click or table row click
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
else:
    selected_rows = grid_return.get("selected_rows") if grid_return else None
    if selected_rows is not None:
        try:
            row = selected_rows.iloc[0] if hasattr(selected_rows, "iloc") else selected_rows[0]
            if address_col in (row.index if hasattr(row, "index") else row):
                clicked_addr = str(row[address_col]).strip()
        except (IndexError, KeyError, TypeError):
            pass
if clicked_addr is not None:
    st.session_state["_clicked_addr"] = clicked_addr

# ---- Floor plan panel (PDF loaded only when she opens "View Floor Plan") ----
def _get_pdf_bytes(
    pdf_path: str,
    pdf_uploads: list | None,
    pdf_folder: str | None,
    drive_folder_id: str | None,
    drive_api_key: str | None,
) -> bytes | None:
    """Get PDF bytes from uploads, local folder, or Google Drive. Loaded on demand only."""
    filename = os.path.basename(pdf_path)
    cache_key = f"_pdf_{filename}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    if pdf_uploads:
        for f in pdf_uploads:
            if f.name == filename:
                data = f.read()
                st.session_state[cache_key] = data
                return data

    if pdf_folder and os.path.isdir(pdf_folder):
        full = os.path.join(pdf_folder, filename)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                data = f.read()
                st.session_state[cache_key] = data
                return data

    if drive_folder_id and drive_api_key:
        list_key = f"_drive_list_{drive_folder_id}"
        if list_key not in st.session_state:
            files, _ = _list_drive_folder(drive_api_key, drive_folder_id)
            st.session_state[list_key] = files
        files = st.session_state[list_key]
        file_id = files.get(filename)
        if file_id:
            data = _download_drive_file(drive_api_key, file_id)
            if data:
                st.session_state[cache_key] = data
                return data

    return None

if clicked_addr:
    units_at_addr = filtered_df[filtered_df[address_col] == clicked_addr]
    pdf_col = "Floor Plan PDF" if "Floor Plan PDF" in df.columns else next((c for c in df.columns if "PDF" in str(c)), None)
    has_source = (
        (pdf_uploads and len(pdf_uploads) > 0)
        or (pdf_folder and os.path.isdir(pdf_folder))
        or (drive_folder_id and drive_api_key)
    )
    # With Drive, we match by address; with local/upload we need pdf_col
    if has_source and not drive_configured:
        has_source = bool(pdf_col)

    if has_source:
        st.subheader("Floor plans")
        any_found = False
        unit_files = []
        for i, (_, row) in enumerate(units_at_addr.iterrows()):
            pdf_path = None
            drive_file_id = None
            display_filename = None
            if drive_configured and drive_files:
                found = _find_drive_file_for_unit(drive_files, clicked_addr, i)
                if found:
                    drive_file_id, _, display_filename = found
                    any_found = True
            elif pdf_col and pdf_col in row.index and pd.notna(row[pdf_col]):
                pdf_path = str(row[pdf_col])
                display_filename = os.path.basename(pdf_path)
                any_found = True
            if drive_file_id or pdf_path:
                unit_files.append((drive_file_id, pdf_path, display_filename))

        def _render_floor_plan(drive_file_id, pdf_path, display_filename):
            if display_filename:
                st.caption(f"**{display_filename}**")
            if drive_file_id:
                preview_url = f"https://drive.google.com/file/d/{drive_file_id}/preview"
                view_url = f"https://drive.google.com/file/d/{drive_file_id}/view"
                st.markdown(f'<iframe src="{preview_url}" width="100%" height="480" style="border:1px solid #ccc; margin:0"></iframe>', unsafe_allow_html=True)
                st.markdown(f'[View in new tab]({view_url})')
            elif pdf_path:
                pdf_bytes = _get_pdf_bytes(pdf_path, pdf_uploads or [], pdf_folder, drive_folder_id, drive_api_key)
                if pdf_bytes:
                    try:
                        b64 = base64.b64encode(pdf_bytes).decode()
                        st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="500" type="application/pdf"></iframe>', unsafe_allow_html=True)
                    except Exception as e:
                        st.caption(f"Could not display PDF: {e}")
                else:
                    st.caption(f"PDF not found: `{os.path.basename(pdf_path)}`")

        if unit_files:
            if len(unit_files) == 1:
                _render_floor_plan(unit_files[0][0], unit_files[0][1], unit_files[0][2])
            else:
                for i, (fid, pp, fn) in enumerate(unit_files):
                    with st.expander(f"⊕ {clicked_addr} {i+1}", expanded=False):
                        _render_floor_plan(fid, pp, fn)

        if has_source and not any_found:
            st.caption("No floor plans found for this address.")
            if drive_configured:
                if drive_error:
                    st.error(f"Google Drive: {drive_error}")
                elif not drive_files:
                    st.warning("Google Drive folder is empty. Add PDF/JPEG files (named as address.pdf, address_1.pdf, etc.).")
                else:
                    expected = f"`{clicked_addr}.pdf`" if len(units_at_addr) == 1 else f"`{clicked_addr}.pdf` / `{clicked_addr}_1.pdf`"
                    st.caption(f"Expected file names in Google Drive (must match column D exactly): {expected}")
            else:
                st.caption("Add a PDF column to your Excel, or configure Google Drive secrets.")

# Table is the AgGrid above; filtered_df drives map and floor plans
