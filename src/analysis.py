import pandas as pd

df = pd.read_csv("lap_data.csv")

if df.empty:
    print("No data found")
    exit()

print("Max speed:", df["speed"].max())
print("Avg speed:", df["speed"].mean())
print("Min speed:", df["speed"].min())