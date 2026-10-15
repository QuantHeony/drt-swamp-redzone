# drt-swamp-redzone

Source code for the **Red Zone** demand-control method that addresses the **DRT swamp**,
where short, dense trips in a town centre absorb demand-responsive transit (DRT) capacity and
callers in peripheral areas wait longer and are served less often.

The code selects a set of central stations (the *Red Zone*), treats trips whose origin and
destination are both inside it as excluded from DRT, and builds the counterfactual demand sets
used in the paper.

> **Patent notice.** The Red Zone method in this repository is protected by an SG patent.
> The code is published only so that the paper can be checked and reproduced.
> See [LICENSE](LICENSE) before any use.

## Data availability

The request records used in the paper are confidential operational data of the service
and **are not included in full**. The `data/` folder holds **three days of de-identified
example input** (14, 15 and 16 October 2024; 793 requests) in exactly the format the code
reads: `data/station.csv` is the stop list and `data/admin_demand/example_*.xlsx` are the
request records. The three days let every step run, but they do **not** reproduce the
numbers in the paper, which use 15 weekdays.

De-identification: the records contain no names, contact details, or addresses. Vehicle,
driver, operator and agent fields, passenger nicknames, pickup and drop-off timestamps and
the requested origin location were removed; coordinates are those of the stops. The
operator-issued passenger code persists only for app bookings (39% of requests in the
study period) and was replaced by a pseudonym (`A####`, consistent across the three days);
phone bookings carry a per-request code (`T######`), as in the original records.

`tools/make_sample_data.py` can additionally write a fully **synthetic** set in the same
format to `data_synthetic/`, for format checks only.

## Versions and reproducibility

- **Tag `paper-v1`** is the exact code that produced the paper's results. On the original
  data it yields Red Zones of 39, 52 and 59 stations for α = 0.05, 0.15 and 0.25,
  identical to the paper.
- **`main` corrects a bug in the OD-pattern similarity** (`smr_od_pattern_func`).
  In `paper-v1`, the zone-level demand of the candidate station was read from the
  representative station's row. The candidate's own row is now used, as the method
  intends.
- On the original data the correction only **adds** stations and removes none.
  The Red Zones grow to 45, 55 and 60 stations, and the excluded demand share rises from
  20.98% to 22.40%, 27.56% to 28.20%, and 40.55% to 40.57%.

To reproduce the paper exactly, check out `paper-v1`.

- **C1 (centre-only, Section 5.5.1)** = `candidate_zones=[3]`, α = 0.25. `ParameterConfig.candidate_zones`
  (default `None` = unconstrained) restricts the candidate stops in both stages, representative
  selection and similarity expansion, to the listed zones.

## Repository layout

| Path | Role |
|---|---|
| `logic/trp_algorithm.py` | Red Zone selection (`TrpAlgorithm`) |
| `logic/db_class.py` | Loads stations and call records |
| `logic/station.py`, `logic/passenger_call.py`, `logic/utils.py` | Data classes and helpers |
| `parameter_config.py` | Parameters α, β, γ and sampling settings |
| `main.py` | One run at the α set in `parameter_config.py` |
| `main_iteration.py` | α sweep 0.05 to 0.40 used in the paper |
| `sampling_processor.py` | Refill scenario: re-samples demand after the Red Zone is applied |
| `osrm_router.py` | Road distances from an OSRM server, used by the refill sampling |
| `zone_analysis.py`, `map_visualizer.py` | Zone-level demand summaries and station maps |
| `tools/make_sample_data.py` | Writes the synthetic sample data |
| `tools/apply_red_zone.py` | Removal-only and uniform-cut demand sets |

## Method in brief

1. **Demand matrix.** Calls are aggregated into a station-by-station OD matrix of passengers.
2. **Representative stations.** In each step, the station whose exclusion most reduces the
   variance of zone-level demand (Z) is chosen, subject to a modified BIC stopping rule
   (`get_SDI`). Selection stops once the excluded internal demand reaches the share α.
3. **Expansion by similarity.** A non-selected station joins the Red Zone when
   `β · (1 − distance cost) + (1 − β) · OD-pattern similarity ≥ γ` with respect to a
   representative station (`similarity_checker`).
4. **Scenarios.**
   - *Removal-only:* drop trips whose origin and destination are both in the Red Zone.
   - *Refill:* those trips are moved to non-restricted stations, then calls are re-sampled
     following the hourly profile until total daily road distance is within ±15% of a
     randomly chosen observed day (`sampling_processor.py`, 16 synthetic days).
   - *Uniform cut (benchmark):* drop the same number of calls per day at random.

Paper defaults are β = 0.7 and γ = 0.4. Zone codes must be consecutive integers starting at 1.

## Requirements

Python 3.11 or later.

```bash
pip install -r requirements.txt
```

The refill sampling needs an [OSRM](https://project-osrm.org/) server with a road network
covering the study area. It uses `http://localhost:5000` by default; see `osrm_router.py`.
Without OSRM, set `enable_sampling = False` in `parameter_config.py`.

The service-level results in the paper came from a commercial DRT simulator, which is not part
of this repository. The demand sets produced here are its inputs.

## Usage

Run every command from the repository root.

```bash
# 1. (optional) write a synthetic set to data_synthetic/ (does not touch data/)
python tools/make_sample_data.py --days 3 --calls 250 --seed 42

# 2. Red Zone for one α (set rr_dmd_alpha in parameter_config.py)
python main.py

# 3. α sweep used in the paper
python main_iteration.py

# 4. counterfactual demand sets from a Red Zone file
python tools/apply_red_zone.py "logic/result/<folder>/<id>-red_zone(...).csv" --mode removal --out out/removal
python tools/apply_red_zone.py "logic/result/<folder>/<id>-red_zone(...).csv" --mode uniform --seed 1 --out out/uniform_s1
```

Outputs:

- `logic/result/reduction_<rate>%_alpha<α>_beta<β>_gamma<γ>/`: Red Zone station list
  (`*-red_zone(...).csv`), refill samples (`sampling_*.csv`), zone summaries and maps.
- `logs/`: run logs plus the OD matrix before and after the Red Zone is applied.

## Input format

`data/station.csv` uses cp949 encoding with one row per station.

| Column | Meaning |
|---|---|
| `FID` | Row index |
| `NO` | Station id |
| `정류장` | Station name, which call records refer to |
| `정류_1` | English name |
| `경도_X_`, `위도_Y_` | Longitude and latitude (WGS84) |
| `주소_국`, `구분` | Address and type, not used by the algorithm |
| 9th column (`2024_09_23` in the example file) | Demand count, not used by the algorithm; columns are read by position |
| `zone` | Zone id, consecutive integers from 1 |

`data/admin_demand/*.xlsx` holds call records, one row per call.

| Column | Meaning |
|---|---|
| `승객ID` | Passenger code (pseudonym in the example data), not used by the algorithm |
| `합승인원` | Number of accompanying passengers |
| `성인`, `청소년`, `어린이` | Adults, teenagers and children; passenger count is their sum |
| `배차분류` | Call outcome: `이용완료` completed, `호출취소` cancelled, `노쇼` no-show |
| `날짜`, `호출시각` | Date (`YYYY-MM-DD`) and call time (`HH:MM:SS`) |
| `호출방법` | Booking channel: `앱(실시간)` app, `전화(실시간)` phone; not used by the algorithm |
| `승차 정류장`, `하차 정류장` | Origin and destination station names, matched to `station.csv` |
| `승차지/하차지/도착지 위도·경도` | Coordinates, read but not used |

## Citation

If you use this code, please cite the paper. Full reference to be added on publication.

## License

Not open source. See [LICENSE](LICENSE).
