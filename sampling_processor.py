import os
import csv
import time
import random
import datetime
import logging
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from copy import deepcopy
from typing import Dict, List, Tuple

from osrm_router import OsrmRouter
from logic.db_class import DbClass
from logic.passenger_call import PassengerCall
from logic.station import Station
from parameter_config import ParameterConfig


def run_sampling_process(red_zone_file: str, param: ParameterConfig, logger: logging.Logger, reduction_folder_path: str) -> None:
    """
    샘플링 프로세스 실행
    
    Args:
        red_zone_file: 레드존 파일 경로
        param: 파라미터 설정
        logger: 로거 인스턴스
        reduction_folder_path: 수요감소율 폴더 경로
    """
    logger.info("=" * 50)
    logger.info("샘플링 프로세스 시작")
    logger.info("=" * 50)
    
    # 레드존 데이터 로드
    red_zone_dic = load_red_zone_data(red_zone_file, logger)
    
    # 라우터 및 데이터베이스 초기화
    router = OsrmRouter()
    db = DbClass(criteria=2, logger=logger)
    
    # 시간대별 수요 분석
    hourly_data = analyze_hourly_demand(db, router, logger)
    hourly_demand_count, hour_to_callpks, od_dic, distance_dic = hourly_data
    
    # 수요 분포 계산 및 시각화
    prob_dist, station_prob_dist = calculate_distributions(
        hourly_demand_count, db, logger, reduction_folder_path
    )
    
    # 샘플링 실행
    for day in range(param.sampling_days):
        execute_daily_sampling(
            day, red_zone_dic, db, router, od_dic, distance_dic,
            prob_dist, station_prob_dist, hour_to_callpks, param, logger, reduction_folder_path
        )
    
    logger.info("샘플링 프로세스 완료")


def load_red_zone_data(red_zone_file: str, logger: logging.Logger) -> Dict[int, Dict]:
    """레드존 데이터 로드"""
    red_zone_dic = {}
    
    with open(red_zone_file, encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0:  # 헤더 스킵
                continue
            red_station_pk = int(row[1])
            red_zone_dic[red_station_pk] = {}
    
    logger.info(f"레드존 정류장 수: {len(red_zone_dic)}")
    return red_zone_dic


def analyze_hourly_demand(db: DbClass, router: OsrmRouter, logger: logging.Logger) -> Tuple:
    """시간대별 수요 분석"""
    hourly_demand_count = defaultdict(int)
    hour_to_callpks = defaultdict(list)
    distance_dic: Dict[str, float] = {}
    od_dic = {}
    
    logger.info("시간대별 수요 분석 시작...")
    
    for call_pk in db.passenger_call_dic:
        call: PassengerCall = db.passenger_call_dic[call_pk]
        o_station: Station = db.station_dic[call.o_station_pk]
        d_station: Station = db.station_dic[call.d_station_pk]
        
        # 정류장별 카운트 업데이트
        db.station_count_list[o_station.idx] += 1
        db.station_count_list[d_station.idx] += 1
        
        # 거리 계산 (캐싱)
        od_key = f"{call.o_station_pk}-{call.d_station_pk}"
        if od_key not in od_dic:
            distance, duration = router.get_route(
                o_station.lon, o_station.lat, d_station.lon, d_station.lat
            )
            if distance is not None:
                od_dic[od_key] = distance
            else:
                raise Exception("경로 탐색 실패")
        
        # 일별 거리 합계
        run_date = call.call_time.strftime("%Y-%m-%d")
        distance_dic.setdefault(run_date, 0.0)
        distance_dic[run_date] += od_dic[od_key]
        
        # 시간대별 분류
        hour = call.call_time.hour
        hourly_demand_count[hour] += 1
        hour_to_callpks[hour].append(call_pk)
    
    logger.info("시간대별 수요 분석 완료")
    return hourly_demand_count, hour_to_callpks, od_dic, distance_dic


def calculate_distributions(hourly_demand_count: defaultdict, db: DbClass, 
                          logger: logging.Logger, reduction_folder_path: str = None) -> Tuple[np.ndarray, np.ndarray]:
    """수요 분포 계산 및 시각화"""
    # 시간대별 분포
    hourly_counts = [hourly_demand_count.get(h, 0) for h in range(24)]
    total_count = sum(hourly_counts)
    prob_dist = np.array(hourly_counts) / total_count if total_count > 0 else np.zeros(24)
    
    # 시각화
    plt.figure(figsize=(10, 4))
    plt.bar(range(24), hourly_counts, alpha=0.7, label="Call Count")
    plt.plot(range(24), prob_dist * max(hourly_counts), color='red', 
             linestyle='--', label="Normalized Curve (scaled)")
    plt.xticks(range(24))
    plt.xlabel("Hour")
    plt.ylabel("Demand Count")
    plt.title("Hourly Call Demand Distribution")
    plt.legend()
    plt.grid(True)
    
    # 수요감소율 폴더가 지정된 경우 해당 폴더에 저장, 아니면 현재 디렉토리
    if reduction_folder_path:
        histogram_path = os.path.join(reduction_folder_path, "hourly_demand_histogram.png")
    else:
        histogram_path = "./hourly_demand_histogram.png"
    
    plt.savefig(histogram_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    # 정류장별 분포
    station_counts = np.array(db.station_count_list)
    station_prob_dist = station_counts / station_counts.sum()
    
    logger.info("수요 분포 계산 완료")
    return prob_dist, station_prob_dist


def execute_daily_sampling(day: int, red_zone_dic: Dict, db: DbClass, router: OsrmRouter,
                          od_dic: Dict, distance_dic: Dict, prob_dist: np.ndarray,
                          station_prob_dist: np.ndarray, hour_to_callpks: defaultdict,
                          param: ParameterConfig, logger: logging.Logger, reduction_folder_path: str) -> None:
    """일일 샘플링 실행"""
    time_name = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{day}"
    sampled_od_list = []
    sampled_distance_sum = 0.0
    used_call_pks = set()
    
    # 목표 거리 설정
    target_date = random.choice(list(distance_dic.keys()))
    target_distance = distance_dic[target_date]
    min_distance = target_distance * param.distance_tolerance_lower
    max_distance = target_distance * param.distance_tolerance_upper
    sampled_target_distance = random.uniform(min_distance, max_distance)
    
    logger.info(f"[{day}] - {time_name}")
    logger.info(f"목표 통행거리: {sampled_target_distance:.2f}m")
    logger.info(f"허용 범위: {min_distance:.2f}m ~ {max_distance:.2f}m")
    
    # 샘플링 루프
    for _ in range(param.max_iterations):
        # 시간대 기반 샘플링
        sampled_hour = np.random.choice(range(24), p=prob_dist)
        callpks_in_hour = hour_to_callpks.get(sampled_hour, [])
        
        if not callpks_in_hour:
            continue
        
        # 호출 선택 (중복 방지)
        sampled_callpk = np.random.choice(callpks_in_hour)
        if sampled_callpk in used_call_pks:
            continue
        
        sampled_call = deepcopy(db.passenger_call_dic[sampled_callpk])
        
        # 시간 설정
        random_minute = random.randint(0, 59)
        call_time_str = f"{target_date} {sampled_hour:02d}:{random_minute:02d}:00"
        sampled_call_date_time = datetime.datetime.strptime(call_time_str, "%Y-%m-%d %H:%M:%S")
        sampled_call_time_str = str(sampled_call_date_time.time())
        
        # 레드존 수요 처리
        if sampled_call.o_station_pk in red_zone_dic and sampled_call.d_station_pk in red_zone_dic:
            process_red_zone_demand(sampled_call, red_zone_dic, station_prob_dist, db, logger)
        
        # 거리 계산
        od_key = f"{sampled_call.o_station_pk}-{sampled_call.d_station_pk}"
        if od_key not in od_dic:
            o_station = db.station_dic[sampled_call.o_station_pk]
            d_station = db.station_dic[sampled_call.d_station_pk]
            distance, duration = router.get_route(
                o_station.lon, o_station.lat, d_station.lon, d_station.lat
            )
            od_dic[od_key] = distance
        else:
            distance = od_dic[od_key]
        
        # 샘플 추가
        sampled_od_list.append((
            sampled_callpk, sampled_call.o_station_pk, sampled_call.d_station_pk,
            distance, sampled_call_time_str
        ))
        sampled_distance_sum += distance
        used_call_pks.add(sampled_callpk)
        
        # 목표 달성 체크
        if sampled_distance_sum >= sampled_target_distance:
            logger.info(f"목표 달성: {sampled_distance_sum:.2f}m")
            break
    
    # 결과 저장
    save_sampling_results(sampled_od_list, db, time_name, sampled_distance_sum, logger, reduction_folder_path)


def process_red_zone_demand(sampled_call: PassengerCall, red_zone_dic: Dict,
                           station_prob_dist: np.ndarray, db: DbClass, logger: logging.Logger) -> None:
    """레드존 수요 처리"""
    num = random.randint(1, 3)
    
    if num == 1:  # 출발지만 변경
        new_o_station = sample_non_red_zone_station(red_zone_dic, station_prob_dist, db)
        sampled_call.o_station_pk = new_o_station
    elif num == 2:  # 도착지만 변경
        new_d_station = sample_non_red_zone_station(red_zone_dic, station_prob_dist, db)
        sampled_call.d_station_pk = new_d_station
    else:  # 출발지와 도착지 모두 변경
        new_o_station = sample_non_red_zone_station(red_zone_dic, station_prob_dist, db)
        new_d_station = sample_non_red_zone_station(red_zone_dic, station_prob_dist, db)
        sampled_call.o_station_pk = new_o_station
        sampled_call.d_station_pk = new_d_station
        
        # logger.info(f"OD 변경 [{num}]: {sampled_call.o_station_pk} - {sampled_call.d_station_pk}")


def sample_non_red_zone_station(red_zone_dic: Dict, station_prob_dist: np.ndarray, db: DbClass) -> int:
    """레드존이 아닌 정류장 샘플링"""
    while True:
        sampled_station_idx = np.random.choice(len(station_prob_dist), p=station_prob_dist)
        new_station = db.station_idx_pk_list[sampled_station_idx]
        if new_station not in red_zone_dic:
            return new_station


def save_sampling_results(sampled_od_list: List, db: DbClass, time_name: str, 
                         sampled_distance_sum: float, logger: logging.Logger, reduction_folder_path: str) -> None:
    """샘플링 결과 저장"""
    filename = os.path.join(reduction_folder_path, f"sampling_{time_name}.csv")
    
    with open(filename, "w", newline="", encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        header = ["call_pk", "o_station_pk", "d_station_pk", "o_station_name", 
                 "d_station_name", "o_lat", "o_lon", "d_lat", "d_lon", "distance", "call_time", "ppl"]
        writer.writerow(header)
        
        for i, sample in enumerate(sampled_od_list):
            call_pk = sample[0]
            passenger_call: PassengerCall = db.passenger_call_dic[call_pk]
            o_station: Station = db.station_dic[sample[1]]
            d_station: Station = db.station_dic[sample[2]]
            ppl = passenger_call.extra_cnt + 1
            
            row = [i+1, o_station.station_pk, d_station.station_pk, o_station.station_name,
                   d_station.station_name, o_station.lat, o_station.lon, d_station.lat,
                   d_station.lon, sample[3], sample[4], ppl]
            writer.writerow(row)
    
    logger.info(f"샘플링 결과 저장: {filename}")
    logger.info(f"샘플 개수: {len(sampled_od_list)}, 누적 거리: {sampled_distance_sum:.2f}m")