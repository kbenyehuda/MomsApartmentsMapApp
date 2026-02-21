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
pip install -r requirements.txt
python -m streamlit run app.py
```

Then open http://localhost:8501. Upload your Excel file. When using Google Drive for PDFs, add the secrets; otherwise use a local PDF folder or upload PDFs.

## Deploy to Streamlit Cloud

1. Push this repo to GitHub. (If `MomsApartmentsMapApp` is inside a larger repo, either deploy from a repo where it is the root, or set main file to `MomsApartmentsMapApp/app.py`.)
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app** → choose this repo, branch `main`, main file `app.py`.
4. Before launching: add **Secrets** (Settings → Secrets):

```toml
GOOGLE_DRIVE_API_KEY = "AIza_your_key"
GOOGLE_DRIVE_FOLDER_ID = "1ABC_folder_id_from_drive_url"
```

5. Deploy. Users upload Excel; PDFs load from your Drive automatically. See **GOOGLE_DRIVE_SETUP.md** for details.
