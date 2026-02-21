"""
One-time script to create a dummy Excel file for development.
Run: python create_dummy_data.py
"""
import pandas as pd
import os

# Dummy apartment data - each row = one apartment (Tel Aviv, Israel)
# PDF columns: file path to PDF displayed in map hover (relative to uploaded folder)
def _pdf_path(address: str, unit: str) -> str:
    """Generate PDF filename from address + unit (e.g., 15_Dizengoff_Street_Apt1.pdf)"""
    slug = address.replace(", Tel Aviv", "").replace(" ", "_").replace(".", "")
    return f"pdfs/{slug}_{unit.replace(' ', '_')}.pdf"

data = [
    {"Address": "15 Dizengoff Street, Tel Aviv", "Unit": "Apt 1", "Price": 6500, "Bedrooms": 2, "Bathrooms": 1, "Showers": 1, "Living Room Size (1-5)": 4, "Balcony Faces": "North", "Floor Plan PDF": _pdf_path("15 Dizengoff Street, Tel Aviv", "Apt 1"), "Notes": "Corner unit"},
    {"Address": "15 Dizengoff Street, Tel Aviv", "Unit": "Apt 2", "Price": 5200, "Bedrooms": 1, "Bathrooms": 1, "Showers": 1, "Living Room Size (1-5)": 2, "Balcony Faces": "Street", "Floor Plan PDF": _pdf_path("15 Dizengoff Street, Tel Aviv", "Apt 2"), "Notes": "Street facing"},
    {"Address": "15 Dizengoff Street, Tel Aviv", "Unit": "Apt 3", "Price": 8000, "Bedrooms": 3, "Bathrooms": 2, "Showers": 2, "Living Room Size (1-5)": 5, "Balcony Faces": "South", "Floor Plan PDF": _pdf_path("15 Dizengoff Street, Tel Aviv", "Apt 3"), "Notes": "Top floor"},
    {"Address": "42 Ibn Gabirol Street, Tel Aviv", "Unit": "Apt 1", "Price": 7500, "Bedrooms": 2, "Bathrooms": 2, "Showers": 2, "Living Room Size (1-5)": 3, "Balcony Faces": "Garden", "Floor Plan PDF": _pdf_path("42 Ibn Gabirol Street, Tel Aviv", "Apt 1"), "Notes": "Recently renovated"},
    {"Address": "42 Ibn Gabirol Street, Tel Aviv", "Unit": "Apt 2", "Price": 4800, "Bedrooms": 1, "Bathrooms": 1, "Showers": 1, "Living Room Size (1-5)": 1, "Balcony Faces": "No balcony", "Floor Plan PDF": _pdf_path("42 Ibn Gabirol Street, Tel Aviv", "Apt 2"), "Notes": ""},
    {"Address": "88 Rothschild Boulevard, Tel Aviv", "Unit": "Apt 1", "Price": 7000, "Bedrooms": 2, "Bathrooms": 1, "Showers": 1, "Living Room Size (1-5)": 3, "Balcony Faces": "West", "Floor Plan PDF": _pdf_path("88 Rothschild Boulevard, Tel Aviv", "Apt 1"), "Notes": "Quiet building"},
    {"Address": "22 Allenby Street, Tel Aviv", "Unit": "Apt 1", "Price": 8500, "Bedrooms": 3, "Bathrooms": 2, "Showers": 2, "Living Room Size (1-5)": 5, "Balcony Faces": "Sea view", "Floor Plan PDF": _pdf_path("22 Allenby Street, Tel Aviv", "Apt 1"), "Notes": "With balcony"},
    {"Address": "22 Allenby Street, Tel Aviv", "Unit": "Apt 2", "Price": 6000, "Bedrooms": 2, "Bathrooms": 1, "Showers": 1, "Living Room Size (1-5)": 2, "Balcony Faces": "Inner yard", "Floor Plan PDF": _pdf_path("22 Allenby Street, Tel Aviv", "Apt 2"), "Notes": ""},
]

df = pd.DataFrame(data)

# Create data folder if it doesn't exist
os.makedirs("data", exist_ok=True)

output_path = "data/apartments.xlsx"
df.to_excel(output_path, index=False)
print(f"Created {output_path} with {len(df)} rows")
print(f"Addresses: {df['Address'].nunique()} unique (some with multiple units)")
