import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


df = pd.read_csv("match_events.csv")

chad_profit = []
chad_time = []

rat_profit = []
rat_time = []

fat_rat_profit = []
fat_rat_time = []

j = 0

for i in df["Competitor"]:
    if i == "Chad":
        chad_profit.append(df["ProfitLoss"][j])
        chad_time.append(df["Time"][j])
    elif i == "Rat":
        rat_profit.append(df["ProfitLoss"][j])
        rat_time.append(df["Time"][j])
    elif i == "FatRat":
        fat_rat_profit.append(df["ProfitLoss"][j])
        fat_rat_time.append(df["Time"][j])
    j += 1


plt.title("Rat")
plt.plot(rat_time, rat_profit)
plt.show()

plt.title("Chad")
plt.plot(chad_time, chad_profit)
plt.show()

plt.title("Fat Rat")
plt.plot(fat_rat_time, fat_rat_profit)
plt.show()
