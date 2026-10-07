import os
import csv
import glob
import logging
from collections import defaultdict
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import numpy as np

from logic.db_class import DbClass
from logic.passenger_call import PassengerCall
from logic.station import Station


class ZoneAnalyzer:
    def __init__(self, db: DbClass, logger: logging.Logger):
        self.db = db
        self.logger = logger
        self.initial_zone_demand = defaultdict(int)  # base
        self.after1_zone_demand = defaultdict(int)   # after1: 레드존 정책 적용 후
        self.sampling_zone_demands = {}  # {day: {zone_pair: count}} for after2
        self.zone_pair_names = {}  # {zone_pair: (origin_zone, dest_zone)}
        self.red_zone_station_pks = set()  # 레드존 정류장 PK 세트
        
    def set_red_zone_stations(self, red_zone_station_pks: set):
        """레드존 정류장 PK 세트 설정"""
        self.red_zone_station_pks = red_zone_station_pks
        self.logger.info(f"레드존 정류장 수: {len(red_zone_station_pks)}")
    
    def analyze_initial_demand(self):
        """초기 수요 데이터의 존별 기종점 분석 (base)"""
        self.logger.info("초기 수요 데이터 존별 기종점 분석 시작...")
        
        for call_pk in self.db.passenger_call_dic:
            call: PassengerCall = self.db.passenger_call_dic[call_pk]
            o_station: Station = self.db.station_dic[call.o_station_pk]
            d_station: Station = self.db.station_dic[call.d_station_pk]
            
            # 기종점 존 코드 생성
            zone_pair = f"{o_station.zone_pk}-{d_station.zone_pk}"
            psg_cnt = call.adult_cnt + call.teenager_cnt + call.child_cnt
            
            self.initial_zone_demand[zone_pair] += psg_cnt
            self.zone_pair_names[zone_pair] = (o_station.zone_pk, d_station.zone_pk)
        
        total_initial = sum(self.initial_zone_demand.values())
        self.logger.info(f"초기 수요 총 건수: {total_initial:,}")
        self.logger.info(f"존별 기종점 패턴 수: {len(self.initial_zone_demand)}")
        
        # 존별 방문 횟수 계산 및 표준편차 계산
        self.initial_zone_std = self.calculate_zone_visit_std(self.initial_zone_demand)
        self.logger.info(f"초기 데이터 존별 방문 표준편차: {self.initial_zone_std:.2f}")
    
    def analyze_after1_demand(self):
        """레드존 정책 적용 후 수요 분석 (after1)"""
        self.logger.info("레드존 정책 적용 후 수요 분석 시작...")
        
        if not self.red_zone_station_pks:
            self.logger.warning("레드존 정류장 PK가 설정되지 않았습니다.")
            return
        
        removed_count = 0
        for call_pk in self.db.passenger_call_dic:
            call: PassengerCall = self.db.passenger_call_dic[call_pk]
            o_station: Station = self.db.station_dic[call.o_station_pk]
            d_station: Station = self.db.station_dic[call.d_station_pk]
            
            # 레드존 정류장 관련 수요는 제거
            if call.o_station_pk in self.red_zone_station_pks and call.d_station_pk in self.red_zone_station_pks:
                removed_count += 1
                continue
            
            # 기종점 존 코드 생성
            zone_pair = f"{o_station.zone_pk}-{d_station.zone_pk}"
            psg_cnt = call.adult_cnt + call.teenager_cnt + call.child_cnt
            
            self.after1_zone_demand[zone_pair] += psg_cnt
            self.zone_pair_names[zone_pair] = (o_station.zone_pk, d_station.zone_pk)
        
        total_after1 = sum(self.after1_zone_demand.values())
        self.logger.info(f"레드존 정책 적용 후 수요 총 건수: {total_after1:,}")
        self.logger.info(f"제거된 수요 건수: {removed_count:,}")
        
        # 존별 방문 횟수 계산 및 표준편차 계산
        self.after1_zone_std = self.calculate_zone_visit_std(self.after1_zone_demand)
        self.logger.info(f"레드존 정책 적용 후 존별 방문 표준편차: {self.after1_zone_std:.2f}")
        
    def analyze_sampling_demand(self, reduction_folder_path: str):
        """샘플링 데이터의 존별 기종점 분석"""
        self.logger.info("샘플링 데이터 존별 기종점 분석 시작...")
        
        # 샘플링 파일들 찾기
        sampling_files = glob.glob(os.path.join(reduction_folder_path, "sampling_*.csv"))
        self.logger.info(f"발견된 샘플링 파일 수: {len(sampling_files)}")
        
        for i, sampling_file in enumerate(sampling_files):
            day_demand = defaultdict(int)
            
            with open(sampling_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                next(reader)  # 헤더 스킵
                
                for row in reader:
                    o_station_pk = int(row[1])
                    d_station_pk = int(row[2])
                    ppl = int(row[11])
                    
                    # 존 정보 가져오기
                    o_station: Station = self.db.station_dic[o_station_pk]
                    d_station: Station = self.db.station_dic[d_station_pk]
                    
                    zone_pair = f"{o_station.zone_pk}-{d_station.zone_pk}"
                    day_demand[zone_pair] += ppl
                    self.zone_pair_names[zone_pair] = (o_station.zone_pk, d_station.zone_pk)
            
            self.sampling_zone_demands[f"day_{i}"] = day_demand
            day_total = sum(day_demand.values())
            self.logger.info(f"Day {i} 총 수요: {day_total:,}")
        
        # 샘플링 데이터의 총합 표준편차 계산은 나중에 수행
    
    def calculate_total_sampling_demand(self):
        """샘플링 데이터의 총합 계산"""
        if not self.sampling_zone_demands:
            return {}
            
        total_demand = defaultdict(int)
        
        # 모든 존 쌍 수집
        all_zone_pairs = set()
        for day_data in self.sampling_zone_demands.values():
            all_zone_pairs.update(day_data.keys())
        
        # 총합 계산
        for zone_pair in all_zone_pairs:
            total_demand[zone_pair] = sum(day_data.get(zone_pair, 0) for day_data in self.sampling_zone_demands.values())
            
        return total_demand
    
    def calculate_daily_average_initial_demand(self):
        """초기 수요 데이터의 일 평균 계산"""
        if not self.initial_zone_demand:
            return {}
            
        num_days = len(self.sampling_zone_demands) if self.sampling_zone_demands else 1
        daily_avg_demand = {}
        
        for zone_pair, total_demand in self.initial_zone_demand.items():
            daily_avg_demand[zone_pair] = total_demand / num_days
            
        return daily_avg_demand
    
    def calculate_daily_average_after1_demand(self):
        """레드존 정책 적용 후 수요 데이터의 일 평균 계산"""
        if not self.after1_zone_demand:
            return {}
            
        num_days = len(self.sampling_zone_demands) if self.sampling_zone_demands else 1
        daily_avg_demand = {}
        
        for zone_pair, total_demand in self.after1_zone_demand.items():
            daily_avg_demand[zone_pair] = total_demand / num_days
            
        return daily_avg_demand
    
    def calculate_zone_visit_std(self, zone_demand_dict):
        """존별 방문 횟수 표준편차 계산"""
        # 각 존별 방문 횟수 계산 (기점 + 종점)
        zone_visits = defaultdict(int)
        
        for zone_pair, demand in zone_demand_dict.items():
            if '-' in zone_pair:
                origin_zone, dest_zone = zone_pair.split('-')
                origin_zone = int(origin_zone)
                dest_zone = int(dest_zone)
                
                # 각 수요당 기점 1회, 종점 1회 방문
                zone_visits[origin_zone] += demand  # 기점 방문
                zone_visits[dest_zone] += demand    # 종점 방문
        
        # 모든 존의 방문 횟수 리스트
        all_zones = set()
        for zone_pair in zone_demand_dict.keys():
            if '-' in zone_pair:
                origin_zone, dest_zone = zone_pair.split('-')
                all_zones.add(int(origin_zone))
                all_zones.add(int(dest_zone))
        
        visit_counts = [zone_visits.get(zone, 0) for zone in sorted(all_zones)]
        
        # 표준편차 계산
        if len(visit_counts) > 1:
            import statistics
            std_dev = statistics.stdev(visit_counts)
        else:
            std_dev = 0.0
            
        return std_dev
    
    def save_analysis_csv(self, reduction_folder_path: str):
        """분석 결과를 CSV로 저장"""
        csv_path = os.path.join(reduction_folder_path, "zone_demand_analysis.csv")
        
        # 샘플링 수요 총합 계산
        total_sampling_demand = self.calculate_total_sampling_demand()
        
        # 초기 수요 및 after1 수요 일 평균 계산
        daily_avg_initial_demand = self.calculate_daily_average_initial_demand()
        daily_avg_after1_demand = self.calculate_daily_average_after1_demand()
        
        # 표준편차 계산
        if not hasattr(self, 'sampling_zone_std'):
            self.sampling_zone_std = self.calculate_zone_visit_std(total_sampling_demand)
        if not hasattr(self, 'after1_zone_std'):
            self.after1_zone_std = self.calculate_zone_visit_std(self.after1_zone_demand)
        
        # 모든 존 쌍 수집
        all_zone_pairs = set(self.initial_zone_demand.keys())
        all_zone_pairs.update(self.after1_zone_demand.keys())
        all_zone_pairs.update(total_sampling_demand.keys())
        for day_data in self.sampling_zone_demands.values():
            all_zone_pairs.update(day_data.keys())
        
        # 수요 총합 계산
        total_initial = sum(self.initial_zone_demand.values())
        total_after1 = sum(self.after1_zone_demand.values())
        total_sampling = sum(total_sampling_demand.values()) if total_sampling_demand else 0
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            
            # 헤더 생성
            header = ["zone_pair", "origin_zone", "dest_zone", 
                     "base_daily_avg_demand", "base_ratio",
                     "after1_daily_avg_demand", "after1_ratio"]
            
            # 일자별 샘플링 데이터 헤더 추가
            day_keys = sorted(self.sampling_zone_demands.keys())
            for day in day_keys:
                header.extend([f"{day}_demand", f"{day}_ratio"])
            
            header.extend(["after2_total_demand", "after2_total_ratio"])
            writer.writerow(header)
            
            # 요약 정보 행 추가
            summary_row = ["SUMMARY", "", "", f"Total: {total_initial}", "", 
                          f"Total: {total_after1}", ""]
            for _ in day_keys:
                summary_row.extend(["", ""])
            summary_row.extend([f"Total: {total_sampling}", ""])
            writer.writerow(summary_row)
            
            std_row = ["STD_DEV", "", "", f"{self.initial_zone_std:.2f}", "", 
                      f"{self.after1_zone_std:.2f}", ""]
            for _ in day_keys:
                std_row.extend(["", ""])
            std_row.extend([f"{self.sampling_zone_std:.2f}", ""])
            writer.writerow(std_row)
            
            # 빈 행 추가
            writer.writerow([""] * len(header))
            
            # 데이터 행 작성
            for zone_pair in sorted(all_zone_pairs):
                o_zone, d_zone = self.zone_pair_names.get(zone_pair, (zone_pair.split('-')[0], zone_pair.split('-')[1]))
                
                # base 데이터 (일 평균)
                initial_daily_avg = daily_avg_initial_demand.get(zone_pair, 0)
                initial_total_demand = self.initial_zone_demand.get(zone_pair, 0)
                initial_ratio = (initial_total_demand / total_initial * 100) if total_initial > 0 else 0
                
                # after1 데이터 (일 평균)
                after1_daily_avg = daily_avg_after1_demand.get(zone_pair, 0)
                after1_total_demand = self.after1_zone_demand.get(zone_pair, 0)
                after1_ratio = (after1_total_demand / total_after1 * 100) if total_after1 > 0 else 0
                
                row = [zone_pair, o_zone, d_zone, 
                      f"{initial_daily_avg:.2f}", f"{initial_ratio:.2f}%",
                      f"{after1_daily_avg:.2f}", f"{after1_ratio:.2f}%"]
                
                # 일자별 샘플링 데이터
                for day in day_keys:
                    day_demand = self.sampling_zone_demands[day].get(zone_pair, 0)
                    day_total = sum(self.sampling_zone_demands[day].values())
                    day_ratio = (day_demand / day_total * 100) if day_total > 0 else 0
                    row.extend([day_demand, f"{day_ratio:.2f}%"])
                
                # 총 샘플링 데이터
                total_demand = total_sampling_demand.get(zone_pair, 0)
                total_ratio = (total_demand / total_sampling * 100) if total_sampling > 0 else 0
                row.extend([f"{total_demand:.0f}", f"{total_ratio:.2f}%"])
                
                writer.writerow(row)
        
        self.logger.info(f"존별 수요 분석 CSV 저장: {csv_path}")
        return csv_path
    
    def create_visualization(self, reduction_folder_path: str):
        """존별 수요 분석 시각화 - 듀얼 축 사용"""
        # 샘플링 수요 총합 계산
        total_sampling_demand = self.calculate_total_sampling_demand()
        
        # 표준편차 계산
        if not hasattr(self, 'sampling_zone_std'):
            self.sampling_zone_std = self.calculate_zone_visit_std(total_sampling_demand)
        
        # 상위 20개 존 쌍만 시각화 (너무 많으면 그래프가 복잡해짐)
        top_zone_pairs = sorted(self.initial_zone_demand.items(), key=lambda x: x[1], reverse=True)[:20]
        
        if not top_zone_pairs:
            self.logger.warning("시각화할 데이터가 없습니다.")
            return
            
        zone_pairs = [pair[0] for pair in top_zone_pairs]
        initial_demands = [pair[1] for pair in top_zone_pairs]  # base
        after1_demands = [self.after1_zone_demand.get(zone_pair, 0) for zone_pair in zone_pairs]  # after1
        after2_demands = [total_sampling_demand.get(zone_pair, 0) for zone_pair in zone_pairs]  # after2
        
        # 비율 계산
        total_initial = sum(self.initial_zone_demand.values())
        total_after1 = sum(self.after1_zone_demand.values())
        total_sampling = sum(total_sampling_demand.values()) if total_sampling_demand else 0
        
        initial_ratios = [(demand / total_initial * 100) if total_initial > 0 else 0 for demand in initial_demands]
        after1_ratios = [(demand / total_after1 * 100) if total_after1 > 0 else 0 for demand in after1_demands]
        after2_ratios = [(demand / total_sampling * 100) if total_sampling > 0 else 0 for demand in after2_demands]
        
        # 그래프 생성 - 듀얼 축 사용
        fig, ax1 = plt.subplots(figsize=(18, 12))
        
        x = np.arange(len(zone_pairs))
        width = 0.25
        
        # 왼쪽 y축 - 수요량
        ax1.set_xlabel('Zone Pairs (Origin-Destination)', fontsize=12)
        ax1.set_ylabel('Demand Count', color='tab:blue', fontsize=12)
        
        # 수요량 막대 그래프 - 3개 단계
        bars1 = ax1.bar(x - width, initial_demands, width, 
                        label='Base (Initial)', alpha=0.8, color='skyblue')
        bars2 = ax1.bar(x, after1_demands, width, 
                        label='After1 (Red-zone Policy)', alpha=0.8, color='orange')
        bars3 = ax1.bar(x + width, after2_demands, width, 
                        label='After2 (Sampling Total)', alpha=0.8, color='lightcoral')
        
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.set_xticks(x)
        ax1.set_xticklabels(zone_pairs, rotation=45, ha='right')
        ax1.grid(True, alpha=0.3)
        
        # 오른쪽 y축 - 비율
        ax2 = ax1.twinx()
        ax2.set_ylabel('Demand Ratio (%)', color='tab:red', fontsize=12)
        
        # 비율 라인 그래프 - 3개 단계
        line1 = ax2.plot(x, initial_ratios, color='darkblue', marker='o', 
                        linewidth=2, markersize=6, label='Base Ratio')
        line2 = ax2.plot(x, after1_ratios, color='darkorange', marker='^', 
                        linewidth=2, markersize=6, label='After1 Ratio')
        line3 = ax2.plot(x, after2_ratios, color='darkred', marker='s', 
                        linewidth=2, markersize=6, label='After2 Ratio')
        
        ax2.tick_params(axis='y', labelcolor='tab:red')
        
        # 제목 및 범례
        plt.title('Zone-based OD Demand Analysis: Base → After1 (Red-zone Policy) → After2 (Sampling)\n'
                 '(Bars: Demand Count, Lines: Demand Ratio)', fontsize=14, pad=20)
        
        # 수요 총량 계산
        initial_total_sum = sum(initial_demands)
        after1_total_sum = sum(after1_demands)
        after2_total_sum = sum(after2_demands)
        
        # 범례 통합 (수요 총량과 표준편차 포함)
        bars_labels = [bars1, bars2, bars3]
        bars_names = [f'Base Total: {initial_total_sum:,} (σ: {self.initial_zone_std:.2f})',
                     f'After1 Total: {after1_total_sum:,} (σ: {self.after1_zone_std:.2f})',
                     f'After2 Total: {after2_total_sum:,} (σ: {self.sampling_zone_std:.2f})']
        lines_labels = [line1[0], line2[0], line3[0]]
        lines_names = ['Base Ratio', 'After1 Ratio', 'After2 Ratio']
        
        # 두 개의 범례 생성
        legend1 = ax1.legend(bars_labels, bars_names, loc='upper left', bbox_to_anchor=(0, 1), fontsize=10)
        legend2 = ax2.legend(lines_labels, lines_names, loc='upper right', bbox_to_anchor=(1, 1))
        
        # 수요량 변화 표시 (Base → After2 주요 변화가 있는 경우)
        for i, (zone_pair, initial, after2) in enumerate(zip(zone_pairs, initial_demands, after2_demands)):
            if initial > 0:
                change_percent = ((after2 - initial) / initial) * 100
                if abs(change_percent) > 20:  # 20% 이상 변화가 있는 경우
                    ax1.annotate(f'{change_percent:+.1f}%', 
                               xy=(i, max(initial, after2)), 
                               xytext=(5, 10), textcoords='offset points',
                               fontsize=8, ha='left', va='bottom',
                               bbox=dict(boxstyle='round,pad=0.2', fc='yellow', alpha=0.7))
        
        plt.tight_layout()
        
        # 저장
        plot_path = os.path.join(reduction_folder_path, "zone_demand_analysis.png")
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"존별 수요 분석 그래프 저장: {plot_path}")
        
        # 추가로 분리된 그래프도 생성
        self._create_separate_charts(reduction_folder_path, zone_pairs, initial_demands, 
                                   after1_demands, after2_demands, initial_ratios, after1_ratios, after2_ratios)
        
        return plot_path
        
    def _create_separate_charts(self, reduction_folder_path: str, zone_pairs: list, 
                               initial_demands: list, after1_demands: list, after2_demands: list,
                               initial_ratios: list, after1_ratios: list, after2_ratios: list):
        """수요량과 비율을 분리한 그래프 생성"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(24, 10))
        
        x = np.arange(len(zone_pairs))
        width = 0.25
        
        # 1. 수요량 비교
        initial_sum = sum(initial_demands)
        after1_sum = sum(after1_demands)
        after2_sum = sum(after2_demands)
        
        ax1.bar(x - width, initial_demands, width, 
                label=f'Base Total: {initial_sum:,} (σ: {self.initial_zone_std:.2f})', alpha=0.8, color='skyblue')
        ax1.bar(x, after1_demands, width, 
                label=f'After1 Total: {after1_sum:,} (σ: {self.after1_zone_std:.2f})', alpha=0.8, color='orange')
        ax1.bar(x + width, after2_demands, width, 
                label=f'After2 Total: {after2_sum:,} (σ: {self.sampling_zone_std:.2f})', alpha=0.8, color='lightcoral')
        
        ax1.set_xlabel('Zone Pairs (Origin-Destination)')
        ax1.set_ylabel('Demand Count')
        ax1.set_title('Zone-based Demand Comparison\n(Base → After1 → After2)')
        ax1.set_xticks(x)
        ax1.set_xticklabels(zone_pairs, rotation=45, ha='right')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. 비율 비교
        ax2.bar(x - width, initial_ratios, width, 
                label='Base Ratio', alpha=0.8, color='darkblue')
        ax2.bar(x, after1_ratios, width, 
                label='After1 Ratio', alpha=0.8, color='darkorange')
        ax2.bar(x + width, after2_ratios, width, 
                label='After2 Ratio', alpha=0.8, color='darkred')
        
        ax2.set_xlabel('Zone Pairs (Origin-Destination)')
        ax2.set_ylabel('Demand Ratio (%)')
        ax2.set_title('Zone-based Demand Ratio Comparison\n(Base → After1 → After2)')
        ax2.set_xticks(x)
        ax2.set_xticklabels(zone_pairs, rotation=45, ha='right')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        # 저장
        separate_plot_path = os.path.join(reduction_folder_path, "zone_demand_comparison.png")
        plt.savefig(separate_plot_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        self.logger.info(f"존별 수요 비교 그래프 저장: {separate_plot_path}")


def analyze_zone_demand(db: DbClass, reduction_folder_path: str, logger: logging.Logger, red_zone_station_pks: set = None):
    """존별 수요 분석 실행"""
    analyzer = ZoneAnalyzer(db, logger)
    
    # 레드존 정류장 PK 설정
    if red_zone_station_pks:
        analyzer.set_red_zone_stations(red_zone_station_pks)
    
    # 초기 수요 분석 (base)
    analyzer.analyze_initial_demand()
    
    # 레드존 정책 적용 후 수요 분석 (after1)
    analyzer.analyze_after1_demand()
    
    # 샘플링 수요 분석 (after2)
    analyzer.analyze_sampling_demand(reduction_folder_path)
    
    # CSV 저장
    csv_path = analyzer.save_analysis_csv(reduction_folder_path)
    
    # 시각화
    plot_path = analyzer.create_visualization(reduction_folder_path)
    
    return csv_path, plot_path