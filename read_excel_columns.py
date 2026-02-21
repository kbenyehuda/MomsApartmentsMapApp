"""
Read Excel file, columns D onwards. ALL DATA IS IN HEBREW.
Sheet: דירוג | Column D: address (כתובת) | Headers & values: Hebrew
Run: python read_excel_columns.py path/to/file.xlsx
"""
import sys
import pandas as pd

SHEET_NAME = "דירוג"


def read_excel_from_column_d(filepath: str) -> pd.DataFrame:
    """
    Read Excel sheet 'דירוג', columns D onwards.
    All columns, headers, and values are in Hebrew.
    """
    df = pd.read_excel(
        filepath,
        sheet_name=SHEET_NAME,
        usecols="D:ZZ",  # columns D through ZZ (skip A, B, C)
        header=0,
        engine="openpyxl",
        dtype=str,  # preserve Hebrew text, avoid numeric coercion
    )
    return df


def main():
    if len(sys.argv) < 2:
        print("Usage: python read_excel_columns.py <path/to/excel.xlsx>")
        print("Example: python read_excel_columns.py data/apartments.xlsx")
        sys.exit(1)

    filepath = sys.argv[1]
    print(f"Reading: {filepath}")
    print(f"Sheet: {SHEET_NAME}")

    # Debug: list available sheets
    xl = pd.ExcelFile(filepath)
    print(f"Available sheets: {xl.sheet_names}")

    try:
        df = read_excel_from_column_d(filepath)
    except Exception as e:
        print(f"Error reading file: {e}")
        raise

    print(f"\nShape: {df.shape} rows x {df.shape[1]} columns")
    print(f"\nColumn names (D onwards):\n{list(df.columns)}")
    print(f"\nFirst few rows:\n{df.head()}")
    print(f"\nColumn D (address) dtype: {df.iloc[:, 0].dtype}")
    print(f"\nColumn D sample values:\n{df.iloc[:, 0].head()}")

    return df


if __name__ == "__main__":
    df = main()
