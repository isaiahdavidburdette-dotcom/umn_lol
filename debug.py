import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "CLASS_DATA", "combined_clean_data.csv")

df = pd.read_csv(CSV_PATH, nrows=5)  # Just read first 5 rows
print("All columns:")
print(df.columns.tolist())
print("\n First row of data:")
print(df.iloc[0])