"""
Generate a small SYNTHETIC dataset in the same format as the confidential
operational data used in the paper, so that the pipeline can be run end to end.

The numbers produced here are NOT the study data and will not reproduce the
paper's results. They only illustrate the required input format:

  data/station.csv                 stations (cp949, same columns as the original)
  data/admin_demand/*.xlsx         one file per day of call records

Usage:
    python tools/make_sample_data.py [--days 3] [--calls 250] [--seed 42]
"""
import argparse
import csv
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# zone 3 = core (downtown); zones 1, 2, 4 = periphery.
# Zone ids must be consecutive integers starting at 1 (see TrpAlgorithm.get_SDI).
ZONES = {
    3: dict(n=40, center=(127.362, 36.528), spread=0.006),
    1: dict(n=20, center=(127.355, 36.565), spread=0.012),
    2: dict(n=25, center=(127.325, 36.540), spread=0.012),
    4: dict(n=15, center=(127.375, 36.495), spread=0.012),
}


def make_stations(rng):
    rows, no = [], 1001
    for z, cfg in ZONES.items():
        for _ in range(cfg["n"]):
            lon = cfg["center"][0] + rng.normal(0, cfg["spread"])
            lat = cfg["center"][1] + rng.normal(0, cfg["spread"])
            rows.append([len(rows), no, f"S{no}", f"Stop {no}", round(lon, 6), round(lat, 6),
                         "sample", "sample", 0.0, z])
            no += 1
    return rows


def make_calls(rng, stations, n_calls, day):
    st = pd.DataFrame(stations, columns=["FID", "NO", "name", "name_en", "lon", "lat", "addr", "gb", "dmd", "zone"])
    # core stations attract more trips, which creates the core-periphery imbalance the method targets
    w = np.where(st.zone == 3, 2.0, 1.0) * rng.gamma(2.0, 1.0, len(st))
    w = w / w.sum()
    hours = np.arange(6, 22)
    hw = np.array([4, 10, 9, 8, 7, 7, 9, 6, 6, 7, 9, 8, 5, 3, 2, 1], float)
    hw = hw / hw.sum()
    recs = []
    for _ in range(n_calls):
        o, d = rng.choice(len(st), 2, replace=False, p=w)
        h = rng.choice(hours, p=hw)
        adult = 1 + int(rng.random() < 0.15)
        status = rng.choice(["이용완료", "호출취소", "노쇼"], p=[0.86, 0.12, 0.02])
        recs.append({
            "승객ID": int(rng.integers(1, 10**6)), "합승인원": adult - 1, "성인": adult, "청소년": 0, "어린이": 0,
            "배차분류": status, "날짜": day, "호출시각": f"{h:02d}:{int(rng.integers(0, 60)):02d}:00",
            "승차 정류장": st.name[o], "하차 정류장": st.name[d],
            "승차지 위도": st.lat[o], "승차지 경도": st.lon[o], "하차지 위도": st.lat[d], "하차지 경도": st.lon[d],
            "도착지 위도": st.lat[d], "도착지 경도": st.lon[d],
        })
    return pd.DataFrame(recs).sort_values("호출시각")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--calls", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)

    stations = make_stations(rng)
    os.makedirs(os.path.join(ROOT, "data", "admin_demand"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "station.csv"), "w", newline="", encoding="cp949") as f:
        w = csv.writer(f)
        w.writerow(["FID", "NO", "정류장", "정류_1", "경도_X_", "위도_Y_", "주소_국", "구분", "수요량", "zone"])
        w.writerows(stations)

    for i, day in enumerate(pd.bdate_range("2024-10-14", periods=a.days)):
        df = make_calls(rng, stations, a.calls, day.strftime("%Y-%m-%d"))
        df.to_excel(os.path.join(ROOT, "data", "admin_demand", f"sample_{day:%Y%m%d}.xlsx"), index=False)
    print(f"wrote {len(stations)} stations and {a.days} x {a.calls} sample calls under data/")


if __name__ == "__main__":
    main()
