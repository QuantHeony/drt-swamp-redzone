import logging
import os
import csv
import glob
import pandas as pd
import numpy as np
from logic.station import Station
from logic.passenger_call import PassengerCall, CodePassengerCallStatus
from typing import Dict
from dataclasses import dataclass, field

@dataclass
class DbClass:
    def __init__(self, criteria:int, logger:logging.Logger):
        self.logger: logging.Logger = logger
        self.station_dic: Dict[int, Station] = {}
        self.station_pk_dict: Dict[str, int] = {}
        self.station_idx_pk_list = []
        self.station_count_list = []
        self.passenger_call_dic: Dict[int, PassengerCall] = {}

        self.base_dir = os.path.dirname(os.path.abspath(__file__))  # logic/ 디렉토리
        if criteria == 1:
            self.read_station_db()
            self.read_passenger_call_db()
        elif criteria == 2:
            self.read_station_db()
            self.read_passenger_call_db_from_admin()

    def read_station_db(self, station_path: str = "data/station.csv") -> None:
        full_path = os.path.abspath(os.path.join(self.base_dir, "..", station_path))
        with open(full_path, encoding='cp949') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0:  # Skip header
                    continue
                self.station_dic[int(row[1])] = Station.from_doc(row)
                self.station_pk_dict[row[2]] = int(row[1]) # 정류장명 -> 정류장 고유번호.
                self.station_dic[int(row[1])].idx = len(self.station_idx_pk_list)
                self.station_idx_pk_list.append(int(row[1]))
                self.station_count_list.append(1)  # 한번도 방문 안한정류장도 추가 되게끔

        self.logger.info("* Completed to load Station DB")

    def read_passenger_call_db(self, call_path: str = "data/demand.csv") -> None:
        full_path = os.path.abspath(os.path.join(self.base_dir, "..", call_path))
        with open(full_path, encoding='utf-8') as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i == 0:  # Skip header
                    continue
                self.passenger_call_dic[int(row[0])] = PassengerCall.from_doc(row)

        self.logger.info("* Completed to load PassengerCall DB")

    def read_passenger_call_db_from_admin(self, folder_path ="data/admin_demand") -> None:


        full_path = os.path.abspath(os.path.join(self.base_dir, "..", folder_path))
        call_xlsx_files = glob.glob(os.path.join(full_path, "*.xlsx"))

        columns_to_extract = [
            '승객ID', "합승인원", '성인', "청소년", "어린이", '배차분류', '날짜', '호출시각',
            '승차 정류장', '하차 정류장',
            '승차지 위도', '승차지 경도',
            '하차지 위도', '하차지 경도',
            '도착지 위도', '도착지 경도'
        ]

        call_pk = 0
        for file in call_xlsx_files:
            df = pd.read_excel(file)
            selected_df = df[columns_to_extract]
            logging.info(f"수요 데이터 로드 - {call_xlsx_files}")
            for index, row in selected_df.iterrows():
                passenger_id = row['승객ID']
                extra_cnt = row['합승인원']
                adult_cnt = row["성인"]
                teenager_cnt = row["청소년"]
                child_cnt = row["어린이"]
                status = row['배차분류']
                run_date = row['날짜']
                call_time = row['호출시각']
                geton_station = row['승차 정류장']
                getoff_station = row['하차 정류장']
                # geton_lat = row['승차지 위도']
                # geton_lng = row['승차지 경도']
                # getoff_lat = row['하차지 위도']
                # getoff_lng = row['하차지 경도']
                # arrival_lat = row['도착지 위도']
                # arrival_lng = row['도착지 경도']

                status_code = 0
                if status == "이용완료":
                    status_code = CodePassengerCallStatus.DONE
                elif status == "노쇼":
                    status_code = CodePassengerCallStatus.NOSHOW
                elif status == "호출취소":
                    status_code = CodePassengerCallStatus.CANCEL


                if geton_station in self.station_pk_dict and getoff_station in self.station_pk_dict:
                    o_station_pk = self.station_pk_dict[geton_station]
                    d_station_pk = self.station_pk_dict[getoff_station]

                    call_time = run_date + " " + call_time

                    call_pk += 1

                    doc_list = [9999, call_pk, 9999, 9999, 9999, status_code, call_time,
                                o_station_pk, d_station_pk, d_station_pk, call_time, call_time, call_time, call_time,
                                extra_cnt, adult_cnt, teenager_cnt, child_cnt, 99, 0,0,0,0,0, call_time]

                    self.passenger_call_dic[call_pk] = PassengerCall.from_doc(doc_list)

                else:
                    if geton_station not in self.station_pk_dict:
                        logging.info(f"[ERROR] 정류장 정보가 없음. -> {geton_station}")
                    if getoff_station not in self.station_pk_dict:
                        logging.info(f"[ERROR] 정류장 정보가 없음. -> {getoff_station}")

        logging.info(f"[INFO] 총 호출 수요 로드- {call_pk}")