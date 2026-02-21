# Google Drive Setup for Deployed App

When both secrets are set, the app automatically loads PDFs from your Google Drive folder. **No user action needed**—visitors just upload Excel and view floor plans.

## 1. Create and share a Google Drive folder

1. In [Google Drive](https://drive.google.com), create a folder (e.g. "Apartments PDFs").
2. Upload all floor plan PDFs. Filenames must match your Excel "Floor Plan PDF" column (e.g. `15_Dizengoff_Apt1.pdf`).
3. Right-click folder → **Share** → **Anyone with the link** = **Viewer** → Done.

## 2. Get the folder ID

Copy the folder URL, e.g.:

```
https://drive.google.com/drive/folders/1ABC123xyz_your_folder_id_here
```

The folder ID is the part after `/folders/`. You can use the full URL or just the ID.

## 3. Create a Google Cloud API key

1. [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Library**.
2. Enable **Google Drive API**.
3. **Credentials** → **Create credentials** → **API key**.
4. (Optional) Restrict key: HTTP referrers `https://*.streamlit.app/*`, API = Drive only.

## 4. Add secrets (one-time setup)

In **Streamlit Cloud** → your app → **Settings** → **Secrets**, add:

```toml
GOOGLE_DRIVE_API_KEY = "AIza_your_api_key_here"
GOOGLE_DRIVE_FOLDER_ID = "1ABC123xyz_your_folder_id"
```

Or use the full folder URL:

```toml
GOOGLE_DRIVE_FOLDER_ID = "https://drive.google.com/drive/folders/1ABC123xyz"
```

After that, the app reads PDFs from Drive automatically. No copy-pasting in the UI.

## 5. File naming in Google Drive

File names must match the **exact address** from column D in your Excel:

- One file per address: `{exact_address}.pdf` or `{exact_address}.jpeg`
- Multiple per address: `{exact_address}.pdf`, `{exact_address}_1.pdf`, `{exact_address}_2.jpeg`, …

Supported extensions: `.pdf`, `.jpeg`, `.jpg`. The filename before the extension must be identical to the address in column D (no changes).

## Troubleshooting

| Problem | Check |
|--------|-------|
| PDF not found | Filename in Excel exactly matches Drive (including `.pdf`). |
| API errors | Drive API enabled. Folder shared "Anyone with the link". |
| Empty list | Correct folder ID. API key has Drive API enabled. |
