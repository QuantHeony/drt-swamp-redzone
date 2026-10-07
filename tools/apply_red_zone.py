"""
Build the counterfactual demand sets compared in the paper from a red-zone file.

  removal  : drop every call whose origin AND destination are both red-zone stations
             (red-zone internal trips; scenario "removal-only").
  uniform  : drop the same number of calls per day at random, ignoring zones
             (benchmark "uniform cut"); the per-day counts come from the removal rule.

The refill scenario (removed capacity re-filled until daily trip distance matches
Before within +/-15%) is produced by sampling_processor.py.

Input calls are read from data/admin_demand/*.xlsx (same format as the loader in
logic/db_class.py). Output is one xlsx per input file in --out.

Usage:
    python tools/apply_red_zone.py <red_zone.csv> --mode removal --out out/removal
    python tools/apply_red_zone.py <red_zone.csv> --mode uniform --seed 1 --out out/uniform_s1
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("red_zone_csv")
    ap.add_argument("--mode", choices=["removal", "uniform"], required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    st = pd.read_csv(os.path.join(ROOT, "data", "station.csv"), encoding="cp949")
    name_to_pk = dict(zip(st.iloc[:, 2], st.iloc[:, 1]))
    red = set(pd.read_csv(a.red_zone_csv, encoding="utf-8-sig").red_zone_pk.astype(int))
    os.makedirs(a.out, exist_ok=True)

    total_in = total_out = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "admin_demand", "*.xlsx"))):
        df = pd.read_excel(f)
        o = df["승차 정류장"].map(name_to_pk)
        d = df["하차 정류장"].map(name_to_pk)
        internal = o.isin(red) & d.isin(red)
        if a.mode == "removal":
            keep = ~internal
        else:
            # one generator per (seed, day) so each day is reproducible on its own
            day = int(str(df["날짜"].iloc[0]).replace("-", "")[:8])
            drop = np.random.default_rng([a.seed, day]).choice(len(df), int(internal.sum()), replace=False)
            keep = ~pd.Series(np.isin(np.arange(len(df)), drop), index=df.index)
        df[keep].to_excel(os.path.join(a.out, os.path.basename(f)), index=False)
        total_in += len(df)
        total_out += int(keep.sum())
        print(f"{os.path.basename(f)}: {len(df)} calls -> {int(keep.sum())} kept ({int(internal.sum())} red-zone internal)")
    print(f"total: {total_in} -> {total_out} ({a.mode})")


if __name__ == "__main__":
    main()
