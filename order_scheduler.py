from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from termcolor import cprint
from prepare_data import v1, v2, v3, v4, v5, v6
import time
import pymysql
import requests
import json
import pytz
import sys
import pandas as pd
import numpy as np
import pickle
import itertools


def _calculate_feature(df):
    for l in range(1, 11):
        # v2
        df[f"spread_{l}"] = df[f"ask{l}_price"] - df[f"bid{l}_price"]
        df[f"midprice_{l}"] = (df[f"ask{l}_price"] + df[f"bid{l}_price"]) / 2.0

        # v3
        if l > 1:
            df[f"ask_diff_{l}"] = df[f"ask{l}_price"] - df["ask1_price"]
            df[f"bid_diff_{l}"] = df["bid1_price"] - df[f"bid{l}_price"]

    # mean prices and volumes (v4)
    vols = [name for name in list(df.columns) if "_vol" in name]
    prices = [name for name in list(df.columns) if "_price" in name]
    ask_prices = [name for name in prices if "ask" in name]
    bid_prices = [name for name in prices if "bid" in name]
    ask_vols = [name for name in vols if "ask" in name]
    bid_vols = [name for name in vols if "bid" in name]

    df["avg_ask_price"] = df[ask_prices].mean(axis=1).round(6)
    df["avg_bid_price"] = df[bid_prices].mean(axis=1).round(6)
    df["avg_ask_vol"] = df[ask_vols].mean(axis=1).round(6)
    df["avg_bid_vol"] = df[bid_vols].mean(axis=1).round(6)

    df["acc_price_diff"] = 0
    df["acc_vol_diff"] = 0
    for l in range(1, 11):
        df["acc_price_diff"] = (
            df["acc_price_diff"] + df[f"ask{l}_price"] - df[f"bid{l}_price"]
        ).round(6)
        df["acc_vol_diff"] = (
            df["acc_vol_diff"] + df[f"ask{l}_vol"] - df[f"bid{l}_vol"]
        ).round(6)

    # time difference
    df["time_diff"] = df["record_time"] - df["record_time"].shift(5)
    df["time_diff"] = df["time_diff"] / np.timedelta64(1, "s")

    # price and volume derivatives (v6)
    for l in range(1, 11):
        df[f"ask{l}_price_ddx"] = (
            (df[f"ask{l}_price"] - df[f"ask{l}_price"].shift(5))
            / (df["time_diff"] / 60.0)
        ).round(6)
        df[f"bid{l}_price_ddx"] = (
            (df[f"bid{l}_price"] - df[f"bid{l}_price"].shift(5))
            / (df["time_diff"] / 60.0)
        ).round(6)
        df[f"ask{l}_vol_ddx"] = (
            (df[f"ask{l}_vol"] - df[f"ask{l}_vol"].shift(5)) /
            (df["time_diff"] / 60.0)
        ).round(6)
        df[f"ask{l}_vol_ddx"] = (
            (df[f"bid{l}_vol"] - df[f"bid{l}_vol"].shift(5)) /
            (df["time_diff"] / 60.0)
        ).round(6)

    df = df.drop(columns=["record_time", "time_diff"])
    df = df.dropna()

    return df


config_file_path = "./config.json"

with open(config_file_path, "r") as handler:
    config = json.load(handler)

FEE = float(config["exchange"]["fee"])

df = pd.DataFrame(
    columns=[
        "ask1_price",
        "ask1_vol",
        "bid1_price",
        "bid1_vol",
        "ask2_price",
        "ask2_vol",
        "bid2_price",
        "bid2_vol",
        "ask3_price",
        "ask3_vol",
        "bid3_price",
        "bid3_vol",
        "ask4_price",
        "ask4_vol",
        "bid4_price",
        "bid4_vol",
        "ask5_price",
        "ask5_vol",
        "bid5_price",
        "bid5_vol",
        "ask6_price",
        "ask6_vol",
        "bid6_price",
        "bid6_vol",
        "ask7_price",
        "ask7_vol",
        "bid7_price",
        "bid7_vol",
        "ask8_price",
        "ask8_vol",
        "bid8_price",
        "bid8_vol",
        "ask9_price",
        "ask9_vol",
        "bid9_price",
        "bid9_vol",
        "ask10_price",
        "ask10_vol",
        "bid10_price",
        "bid10_vol",
        "record_time",
    ]
)

cprint("[INFO] Collecting 10 minutes of data before trading", "blue")

for minute in range(10):
    r = requests.get(
        "https://api.kucoin.com/api/v1/market/orderbook/level2_100?symbol=ETH-USDT"
    )
    if r.status_code is not 200:
        cprint(
            f"[ERROR] GET Request to orderbook data is not successful. Statut code {r.status_code}",
            "red",
        )
        sys.exit(0)

    data = r.json()
    orderbook_data = data["data"]
    curr_timestamp = datetime.now(pytz.utc)
    arr = []
    for i in range(10):
        arr.append(float(orderbook_data["asks"][i][0]))
        arr.append(float(orderbook_data["asks"][i][1]))
        arr.append(float(orderbook_data["bids"][i][0]))
        arr.append(float(orderbook_data["bids"][i][1]))

    arr.append(curr_timestamp)

    df = df.append(pd.Series(arr, index=df.columns), ignore_index=True)
    cprint(f"[INFO] Minute {minute} data collected", "blue")
    if minute < 9:
        time.sleep(10)

cprint(f"[INFO] Finished collecting data. Loading trained models", "blue")

clf_1 = pickle.load(open("./SVM_Models/SVM_model_v2v3.sav", "rb"))
clf_2 = pickle.load(open("./SVM_Models_Fix1_10mil/SVM_model_v2v3v6.sav", "rb"))
clf_3 = pickle.load(
    open("./SVM_Models_Fix1_10mil/SVM_model_v2v3v4v5.sav", "rb"))
clf_4 = pickle.load(
    open("./SVM_Models_Fix1_10mil/SVM_model_v2v4v5v6.sav", "rb"))
clf_5 = pickle.load(open("./SVM_Models_Fix1_10mil/SVM_model_v2v3v4.sav", "rb"))

cprint(f"[INFO] 5 trained SVM models loaded. Ready for incoming data", "blue")

# while 1:
r = requests.get(
    "https://api.kucoin.com/api/v1/market/orderbook/level2_100?symbol=ETH-USDT"
)
if r.status_code is not 200:
    cprint(
        f"[ERROR] GET Request to orderbook data is not successful. Statut code {r.status_code}",
        "red",
    )
    sys.exit(0)

data = r.json()
orderbook_data = data["data"]
curr_timestamp = datetime.now(pytz.utc)
arr = []
for i in range(10):
    arr.append(float(orderbook_data["asks"][i][0]))
    arr.append(float(orderbook_data["asks"][i][1]))
    arr.append(float(orderbook_data["bids"][i][0]))
    arr.append(float(orderbook_data["bids"][i][1]))

arr.append(curr_timestamp)

df = df.append(pd.Series(arr, index=df.columns), ignore_index=True)
cprint(f"[INFO] Gathered latest orderbook data. Calculating features", "blue")
df = _calculate_feature(df)
df = df.tail(1)
df = df.drop(columns=list(itertools.chain(v1)))
cprint(f"[INFO] Features calculated. Predicting", "blue")
print(df)
vote = 0
y_pred = clf_1.predict(df.drop(columns=list(itertools.chain(v4, v5, v6))))
print(y_pred)

y_pred = clf_2.predict(
    df.drop(columns=list(itertools.chain(v4, v5))))
print(y_pred)

y_pred = clf_3.predict(
    df.drop(columns=list(itertools.chain(v6))))
print(y_pred)

y_pred = clf_4.predict(
    df.drop(columns=list(itertools.chain(v3))))
print(y_pred)

y_pred = clf_5.predict(
    df.drop(columns=list(itertools.chain(v5, v6))))
print(y_pred)

# print(df)


# sched = BackgroundScheduler()
# alarm_time = datetime.now() + timedelta(seconds=10)
# print(alarm_time)
# sched.add_job(alarm, "date", run_date=alarm_time, args=[datetime.now()])

# try:
#     sched.start()
#     while True:
#         time.sleep(9)
# except (KeyboardInterrupt, SystemExit):
#     pass
