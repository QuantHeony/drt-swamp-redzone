import logging
import os
import time
import csv
import copy
import math
import geopy
from collections import defaultdict

import numpy as np

from dataclasses import dataclass, field
from typing import List, Dict, DefaultDict

from geopy.distance import geodesic

from parameter_config import ParameterConfig
from logic.station import Station
from logic.passenger_call import PassengerCall
from logic.db_class import DbClass

@dataclass
class TrpAlgorithm:
    logger: logging.Logger
    db: DbClass
    param: ParameterConfig

    label: int = field(init=False)
    # 정류장
    P: List[Station] = field(init=False, default_factory=list)  # Replace 'object' with your specific type if known
    P_idx: List[int] = field(default_factory=list)  # idx
    P_to_idx: Dict[int, int] = field(default_factory=dict)  # pk to index
    # 정류장 지역 정보
    S: List[int] = field(init=False, default_factory=list)
    S_to_P_idx: Dict[int, List[int]] = field(init=False, default_factory=dict)  # key : zone_pk -> val : [P.idx]
    zone_id_list: set[int] = field(init=False, default_factory=set)
    # 레드존 정류장
    R: List[int] = field(init=False)
    red_zone_list: List[int] = field(init=False, default_factory=list)
    # 변수
    iter: int = field(init=False, default=0)
    n: int = field(init=False, default=0)
    total_demand: int = field(init=False, default=0)
    # 변수 매트릭스
    D: np.ndarray = field(init=False)
    DR: np.ndarray = field(init=False)
    SD: DefaultDict = field(init=False, default_factory=lambda: defaultdict(lambda: 0))
    Qk: Dict[int, np.ndarray] = field(init=False, default_factory=dict)

    SDI_dict: DefaultDict = field(init=False, default_factory=lambda: defaultdict(lambda: 0))
    mod_bic_list: List = field(init=False, default_factory=list)
    p_to_s_dict: DefaultDict = field(init=False, default_factory=lambda: defaultdict(
        lambda: 0))  # key : s_pk -> val [visit # of s1]

    def __post_init__(self):
        self.label = int(time.time())
        # 정류장
        self.P = list()
        self.P_idx = list()
        self.P_to_idx = defaultdict(int)
        # 지역 정보
        self.S = list()
        self.red_zone_list = list()  # 레드존 정류장 pk
        self.initialize()

    def initialize(self):
        # 정류장 정보 삽입
        self.n = 0
        for idx, s_pk in enumerate(self.db.station_dic):
            self.P.append(self.db.station_dic[s_pk])
            self.P_idx.append(s_pk)
            self.P_to_idx[s_pk] = idx
            zone_id = self.db.station_dic[s_pk].zone_pk
            self.S.append(zone_id)
            self.zone_id_list.add(zone_id)
            if zone_id not in self.S_to_P_idx:
                self.S_to_P_idx[zone_id] = list()
            self.S_to_P_idx[zone_id].append(idx)
            self.n += 1
        if self.n == 0: raise Exception("station data is empty.")
        self.R = list(np.zeros(self.n))
        self.D = np.zeros((self.n, self.n))

        for c_pk in self.db.passenger_call_dic:
            pc: PassengerCall = self.db.passenger_call_dic[c_pk]
            o_station_pk = pc.o_station_pk
            d_station_pk = pc.d_station_pk
            psg_cnt = pc.adult_cnt + pc.teenager_cnt + pc.child_cnt

            o_idx = self.P_to_idx[o_station_pk]
            d_idx = self.P_to_idx[d_station_pk]
            self.D[o_idx, d_idx] += psg_cnt

        self.DR = copy.deepcopy(self.D)
        self.total_demand = np.sum(self.D)

        # SD 초기화, Qk 초기화
        for zone_id in sorted(self.zone_id_list):
            self.Qk[zone_id] = np.zeros((self.n, self.n))
            self.SD[zone_id] = np.zeros((1, self.n))

        for zone_id in self.Qk:
            for i in range(0, self.Qk[zone_id].shape[0]):
                for j in range(0, self.Qk[zone_id].shape[1]):
                    delta = 0
                    if self.S[i] == zone_id:
                        delta += 1
                    if self.S[j] == zone_id:
                        delta += 1
                    self.Qk[zone_id][i, j] = delta

    def calculate_DR(self):
        for i in range(0, self.D.shape[0]):
            for j in range(0, self.D.shape[1]):
                self.DR[i, j] = int(self.D[i, j]) * (1 - int(self.R[i]) * int(self.R[j]))

    def calculate_Z(self):
        sdMean = np.mean(np.sum(self.SDI, axis=0))
        return sum([(sd - sdMean) ** 2 for sd in np.sum(self.SDI, axis=0)])

    def calculate_modBIC(self, adjuest_Z):
        return self.n * math.log(adjuest_Z / self.n) + (len(self.red_zone_list) + 2) * math.log(self.n)

    def get_SDI(self):
        sdi = np.zeros((self.n, len(self.zone_id_list)))
        self.SDI = sdi
        continue_flag = True
        while (continue_flag):
            for zone_pk in self.zone_id_list:
                # sdi[:, zone_pk] = np.diag(self.DR.dot(self.Qk[zone_pk].T)) + np.diag(self.DR.T.dot(self.Qk[zone_pk])) - np.diag(self.DR) * np.diag(self.Qk[zone_pk])
                self.SDI[:, zone_pk - 1] = np.diag(self.DR.dot(self.Qk[zone_pk].T))
            self.logger.info(f"sdi 합 : {np.sum(self.SDI)} , 열단위 합 {np.sum(self.SDI, axis=0)}")
            self.iter += 1;
            self.logger.info(f"================ [ iteration - {self.iter}] ================ ")
            z = self.calculate_Z()
            sd_mean = np.mean(np.sum(self.SDI, axis=0))
            i_list = []
            for i, i_sum in enumerate(np.sum(self.SDI, axis=1) / np.sum(self.SDI)):
                sub_sd_mean = round(sd_mean - (i_sum / self.SDI.shape[1]), 4)
                ii = 0
                for s in range(0, self.SDI.shape[1]):
                    ii += ((np.sum(self.SDI, axis=0)[s] - self.SDI[i, s]) - sub_sd_mean) ** 2
                i_list.append(z - ii)

            red_zone_candi_idx = i_list.index(max(i_list))
            # red zone이 하나일 경우는 또 다시 채택될수있음 차선 레드존을 잡는다
            while (red_zone_candi_idx in self.red_zone_list):
                i_list[red_zone_candi_idx] = 0
                red_zone_candi_idx = i_list.index(max(i_list))
            self.logger.info(f"* Z : {z} , 감소된 I : {i_list[red_zone_candi_idx]}")
            modBIC = self.calculate_modBIC(i_list[red_zone_candi_idx])
            if len(self.red_zone_list) < 2 or (self.total_demand - np.sum(
                    self.DR)) < self.total_demand * 0.1:  # red zone 정류장이 2개부터 의미가있다 || 수요가 적어도 10%는 줄어야
                self.mod_bic_list.append(modBIC)
                self.red_zone_list.append(red_zone_candi_idx)
            else:
                if self.mod_bic_list[-1] > modBIC:
                    self.mod_bic_list.append(modBIC)
                    self.red_zone_list.append(red_zone_candi_idx)
                else:
                    self.logger.info(
                        f"* 연산종료 ({self.mod_bic_list[-1]} < {modBIC}), Red Zone candi : {red_zone_candi_idx}")
                    continue_flag = False

            if (continue_flag):
                self.R[red_zone_candi_idx] = 1
                before_sum_call = int(np.sum(self.DR))
                if len(self.red_zone_list) > 1:
                    for r in self.red_zone_list:
                        for c in self.red_zone_list:
                            self.DR[r, c] = 0
                after_sum_call = np.sum(self.DR)
                prior_mod_bic = "-" if len(self.mod_bic_list) < 2 else self.mod_bic_list[-2]
                self.logger.info(f"* 추가 레드존 번호 ({red_zone_candi_idx}, ({prior_mod_bic} > {modBIC})")
                self.logger.info(
                    f"* 이번 추가 레드존으로 차단된 호출 수요 : {before_sum_call - after_sum_call} /  총 제거된 호출 수요 : {self.total_demand - after_sum_call}")
                self.logger.info(f"* 현재 총 레드존({self.red_zone_list}")
                if (self.total_demand - after_sum_call) >= self.total_demand * self.param.rr_dmd_alpha:
                    self.logger.info(f"* 초기 수요 대비 { round( (self.total_demand - after_sum_call)/(self.total_demand)  * 100, 0)} % 감소 (기준: {int(self.param.rr_dmd_alpha * 100)}% ")
                    continue_flag = False
                    break

    def write_result_file(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))  # logic/ 디렉토리
        d_path = f'logs/{self.label}-demand.csv'
        demand_full_path = os.path.abspath(os.path.join(base_dir, "..", d_path))
        with open(demand_full_path, 'w', encoding="utf-8-sig", newline='') as csvfile:
            k = csv.writer(csvfile)
            schema = ["o_stationPk", "d_stationPk", "cnt", "after_cnt"]
            k.writerow(schema)
            for m in range(0, self.D.shape[0]):
                for n in range(0, self.D.shape[1]):
                    wrow = [m, n, int(self.D[m, n]), int(self.DR[m, n])]
                    k.writerow(wrow)
        # Point
        s_path = f'logs/{self.label}-station.csv'
        station_full_path = os.path.abspath(os.path.join(base_dir, "..", s_path))
        with open(station_full_path, 'w', encoding="utf-8-sig", newline='') as csvfile:
            k = csv.writer(csvfile)
            schema = ["station_pk", "station_name", "x", "y", "zone_pk", "redZone"]
            k.writerow(schema)

            for idx, s in enumerate(self.P):
                wrow = [s.station_pk, s.station_name, s.lon, s.lat, s.zone_pk, int(self.R[idx])]
                k.writerow(wrow)

    def smr_cost_func(self, r_idx: int, p_idx: int) -> float:
        '''Cost 함수 계산'''
        r: Station = self.P[r_idx]
        p: Station = self.P[p_idx]
        """유클리디안 직선거리 계산 (단위: 미터)"""
        distance = geodesic((r.lat, r.lon), (p.lat, p.lon)).meters
        cost_val = 1 / (1 + math.exp(-0.0095 * (distance - 500)))
        # self.logger.info(f"유사성 검토 - 거리 유사성 r({(r.lat, r.lon)}) -> p({(p.lat, p.lon)}) = {distance} --> {round( (1 - cost_val) * 100,2)}%")
        return cost_val

    def smr_od_pattern_func(self, r_idx: int, p_idx: int) -> float:
        """OD Pattern 함수 계산"""
        d_r = np.sum(self.DR[r_idx]) # 대표 레드존 정류장
        d_i = np.sum(self.DR[p_idx]) # 비교 대상 정류장
        if d_r == 0 or d_i == 0: return 0

        deviation = 0
        for s in self.S_to_P_idx:
            # 지역별 수요
            d_rs = 0
            d_is = 0
            for j_idx in self.S_to_P_idx[s]:
                d_rs += self.DR[r_idx, j_idx]
                d_is += self.DR[p_idx, j_idx]
            deviation += math.sqrt(((d_rs/d_r) - (d_is/d_i)) ** 2)

        od_pattern_val = 1 / (1 + deviation)
        # self.logger.info(f"유사성 검토 - OD Pattern d_r({d_r}), d_i({d_i}) --> {round(od_pattern_val *100,2)}%")
        return  od_pattern_val

    def write_red_zone(self, reduction_rate):
        base_dir = os.path.dirname(os.path.abspath(__file__))  # logic/ 디렉토리
        
        # 수요 감소율과 파라미터 기반 폴더 생성 (소수점 2자리까지)
        reduction_folder = f"reduction_{reduction_rate:.2f}%_alpha{self.param.rr_dmd_alpha}_beta{self.param.smr_beta}_gamma{self.param.smr_gamma}"
        result_dir = os.path.join(base_dir, "result", reduction_folder)
        
        # 디렉토리 없으면 생성
        os.makedirs(result_dir, exist_ok=True)

        # 파라미터 정보와 수요 감소율을 포함한 파일명 생성
        filename = f"{self.label}-red_zone(dmd_alpha={self.param.rr_dmd_alpha},beta={self.param.smr_beta},gamma={self.param.smr_gamma},reduction={reduction_rate:.2f}%).csv"
        full_path = os.path.join(result_dir, filename)
        
        # 클래스 변수로 저장 (샘플링에서 사용할 수 있도록)
        self.red_zone_file_path = full_path
        self.reduction_folder_path = result_dir

        with open(full_path, 'w', encoding="utf-8-sig", newline='') as csvfile:
            writer = csv.writer(csvfile)
            schema = ["red_zone_idx", "red_zone_pk", "name", "zone_id", "lon", "lat"]
            writer.writerow(schema)

            for idx, r_mark in enumerate(self.R):
                if r_mark == 0:
                    continue
                r = self.P[idx]
                wrow = [idx, r.station_pk, r.station_name, r.zone_pk, r.lon, r.lat]
                writer.writerow(wrow)


    def similarity_checker(self):
        for r_idx in self.red_zone_list:
            for p_idx, p_pk in enumerate(self.P_idx):
                if self.R[p_idx] == 1:
                    continue

                cost_value = self.smr_cost_func(r_idx, p_idx)
                od_value = self.smr_od_pattern_func(r_idx, p_idx)
                similarity_value = self.param.smr_beta * (1 - cost_value) + (1 - self.param.smr_beta) * od_value

                if similarity_value >= self.param.smr_gamma:  # 유사성 조건 만족
                    self.R[p_idx] = 1  # 레드존으로 설정
                    # self.logger.info(
                    #     f" 대표 레드존 {r_idx}과 일반 정류장 {p_idx}는 유사성 조건 통과 {similarity_value} > {self.param.smr_gamma}.")

    def validate_demand_reduction(self):
        """레드존 제약에 따른 수요 감소율 검증"""
        # 레드존 정류장 PK 리스트 생성
        red_zone_station_pks = set()
        for idx, is_red_zone in enumerate(self.R):
            if is_red_zone == 1:
                red_zone_station_pks.add(self.P_idx[idx])
        
        # 초기 수요와 제약된 수요 계산
        total_initial_trips = 0
        constrained_trips = 0
        
        # demand 데이터에서 직접 계산
        for c_pk in self.db.passenger_call_dic:
            pc: PassengerCall = self.db.passenger_call_dic[c_pk]
            o_station_pk = pc.o_station_pk
            d_station_pk = pc.d_station_pk
            psg_cnt = pc.adult_cnt + pc.teenager_cnt + pc.child_cnt
            
            total_initial_trips += psg_cnt
            
            # 기점과 종점 모두 레드존에 속하면 제약
            if o_station_pk in red_zone_station_pks and d_station_pk in red_zone_station_pks:
                constrained_trips += psg_cnt
        
        # 최종 수요 (제약되지 않은 수요)
        final_demand = total_initial_trips - constrained_trips
        reduction_rate = (constrained_trips / total_initial_trips * 100) if total_initial_trips > 0 else 0
        
        self.logger.info("=" * 60)
        self.logger.info("레드존 수요 제약 검증 결과")
        self.logger.info("=" * 60)
        self.logger.info(f"레드존 정류장 수: {len(red_zone_station_pks)}")
        self.logger.info(f"레드존 정류장 PK 리스트: {sorted(red_zone_station_pks)}")
        
        # 존별 레드존 정류장 분석
        zone_analysis = self._analyze_red_zone_by_zones(red_zone_station_pks)
        self.logger.info("")
        self.logger.info("존별 레드존 정류장 분석:")
        for zone_pk, data in sorted(zone_analysis.items()):
            self.logger.info(f"  존 {zone_pk}: {data['red_zone_count']:2d}개/{data['total_count']:2d}개 ({data['ratio']:5.1f}%)")
        
        self.logger.info("")
        self.logger.info(f"초기 총 수요 건수: {total_initial_trips:,}")
        self.logger.info(f"제약된 수요 건수: {constrained_trips:,}")
        self.logger.info(f"최종 수요 건수: {final_demand:,}")
        self.logger.info(f"수요 감소율: {reduction_rate:.2f}%")
        self.logger.info("=" * 60)
        
        return {
            'total_initial_trips': total_initial_trips,
            'constrained_trips': constrained_trips,
            'final_demand': final_demand,
            'reduction_rate': reduction_rate,
            'red_zone_station_pks': red_zone_station_pks
        }
    
    def _analyze_red_zone_by_zones(self, red_zone_station_pks):
        """존별 레드존 정류장 분석"""
        from collections import defaultdict
        
        zone_stats = defaultdict(lambda: {'red_zone_count': 0, 'total_count': 0})
        
        # 모든 정류장을 존별로 분류
        for station_pk, station in self.db.station_dic.items():
            zone_pk = station.zone_pk
            zone_stats[zone_pk]['total_count'] += 1
            
            # 레드존 정류장인지 확인
            if station_pk in red_zone_station_pks:
                zone_stats[zone_pk]['red_zone_count'] += 1
        
        # 비율 계산
        for zone_pk, stats in zone_stats.items():
            if stats['total_count'] > 0:
                stats['ratio'] = (stats['red_zone_count'] / stats['total_count']) * 100
            else:
                stats['ratio'] = 0.0
        
        return dict(zone_stats)

    def main_process(self):
        self.calculate_DR()
        self.get_SDI()
        self.similarity_checker()
        self.logger.info("validate_demand_reduction 함수 호출 시작...")
        reduction_result = self.validate_demand_reduction()
        self.write_red_zone(reduction_result['reduction_rate'])
