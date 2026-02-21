# Mom's Apartments Map App

## Excel Structure

Each **row** = one apartment. Example:

| Address | Unit | Price | Bedrooms | Bathrooms | Showers | Living Room Size (1-5) | Balcony Faces | Floor Plan PDF | Notes |
|---------|------|-------|----------|-----------|---------|------------------------|---------------|----------------|-------|
| 15 Dizengoff Street, Tel Aviv | Apt 1 | 6500 | 2 | 1 | 1 | 4 | North | pdfs/15_Dizengoff_Street_Apt1.pdf | Corner unit |
| 15 Dizengoff Street, Tel Aviv | Apt 2 | 5200 | 1 | 1 | 1 | 2 | Street | pdfs/15_Dizengoff_Street_Apt2.pdf | Street facing |
| 42 Ibn Gabirol Street, Tel Aviv | Apt 1 | 7500 | 2 | 2 | 2 | 3 | Garden | pdfs/42_Ibn_Gabirol_Street_Apt1.pdf | Recently renovated |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

**PDF columns** hold the file path (relative or absolute) to the PDF shown in the map hover/popup. The app will match the path to files in the uploaded folder.

## Run the app

```bash
# 1. Generate dummy data (first time only)
python create_dummy_data.py

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch (use python -m if `streamlit` isn't on PATH)
python -m streamlit run app.py
```

Then open http://localhost:8501. Upload your Excel or use the dummy data. Enter a PDF folder path in the sidebar to view/download floor plans.
