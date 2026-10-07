import logging
import os
import sys
from datetime import datetime

from logic.trp_algorithm import TrpAlgorithm
from logic.db_class import DbClass
from parameter_config import ParameterConfig
from sampling_processor import run_sampling_process
from zone_analysis import analyze_zone_demand
from map_visualizer import create_station_map


def setup_logging() -> logging.Logger:
    """로깅 설정"""
    log_dir = "./logs"
    os.makedirs(log_dir, exist_ok=True)
    
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"main_process_{now_str}.log")
    
    # 루트 로거 설정 (중복 방지)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # 기존 핸들러 모두 제거
    
    # 커스텀 로거 생성
    logger = logging.getLogger("main_process")
    logger.handlers.clear()  # 기존 핸들러 제거
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 상위 로거로 전파 방지 (중복 출력 방지)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # 콘솔 출력 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    # 파일 출력 핸들러
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    logger.info(f"로그 파일 경로: {log_file}")
    return logger


def run_red_zone_algorithm(logger: logging.Logger, param: ParameterConfig, criteria: int = 2) -> tuple:
    """
    레드존 알고리즘 실행
    
    Args:
        logger: 로거 인스턴스
        param: 파라미터 설정
        criteria: 데이터 로딩 기준 (1: demand.csv, 2: admin_demand/*.xlsx)
        
    Returns:
        tuple: (생성된 레드존 파일 경로, 수요감소율 폴더 경로, trp_algorithm 객체)
    """
    logger.info("=" * 60)
    logger.info("TRP 레드존 알고리즘 시작")
    logger.info("=" * 60)
    
    # 데이터베이스 로드
    logger.info("데이터베이스 로딩 시작...")
    db = DbClass(criteria=criteria, logger=logger)
    logger.info(f"정류장 수: {len(db.station_dic)}, 승객 호출 수: {len(db.passenger_call_dic)}")
    
    # TRP 알고리즘 초기화
    logger.info("TRP 알고리즘 초기화...")
    trp_algorithm = TrpAlgorithm(logger=logger, db=db, param=param)
    
    # 메인 프로세스 실행
    logger.info("TRP 알고리즘 실행 시작...")
    trp_algorithm.main_process()
    
    # 결과 파일 출력
    logger.info("결과 파일 생성 중...")
    trp_algorithm.write_result_file()
    
    # 결과 요약
    red_zone_count = sum(trp_algorithm.R)
    total_stations = len(trp_algorithm.P)
    logger.info(f"레드존 정류장 수: {red_zone_count}/{total_stations}")
    logger.info(f"총 반복 횟수: {trp_algorithm.iter}")
    logger.info("TRP 레드존 알고리즘 완료!")
    
    # 생성된 레드존 파일 경로, 수요감소율 폴더 경로, trp_algorithm 객체 반환
    return trp_algorithm.red_zone_file_path, trp_algorithm.reduction_folder_path, trp_algorithm


def run_sampling_algorithm(logger: logging.Logger, param: ParameterConfig, red_zone_file_path: str, reduction_folder_path: str):
    """
    샘플링 알고리즘 실행
    
    Args:
        logger: 로거 인스턴스
        param: 파라미터 설정
        red_zone_file_path: 레드존 파일 경로
        reduction_folder_path: 수요감소율 폴더 경로
    """
    logger.info("=" * 60)
    logger.info("샘플링 알고리즘 시작")
    logger.info("=" * 60)
    
    if os.path.exists(red_zone_file_path):
        run_sampling_process(red_zone_file_path, param, logger, reduction_folder_path)
        logger.info("샘플링 알고리즘 완료!")
    else:
        logger.error(f"레드존 파일을 찾을 수 없습니다: {red_zone_file_path}")


def main():
    """메인 실행 함수"""
    logger = setup_logging()
    
    try:
        # 파라미터 설정
        param = ParameterConfig()
        logger.info("=" * 80)
        logger.info("TRP 프로젝트 메인 프로세스")
        logger.info("=" * 80)
        logger.info(f"파라미터 설정:")
        logger.info(f"  - TRP alpha: {param.rr_dmd_alpha}")
        logger.info(f"  - TRP beta: {param.smr_beta}")
        logger.info(f"  - TRP gamma: {param.smr_gamma}")
        logger.info(f"  - 샘플링 활성화: {param.enable_sampling}")
        if param.enable_sampling:
            logger.info(f"  - 샘플링 일수: {param.sampling_days}")
        
        # 1. 레드존 알고리즘 실행
        red_zone_file_path, reduction_folder_path, trp_algorithm = run_red_zone_algorithm(logger, param, criteria=2)
        
        # 2. 샘플링 알고리즘 실행 (설정에 따라)
        if param.enable_sampling:
            run_sampling_algorithm(logger, param, red_zone_file_path, reduction_folder_path)
            
            # 3. 존별 수요 분석 실행
            logger.info("=" * 60)
            logger.info("존별 수요 분석 시작")
            logger.info("=" * 60)
            
            # 데이터베이스 다시 로드 (분석용)
            db_for_analysis = DbClass(criteria=2, logger=logger)
            
            # 레드존 정류장 PK 세트 생성 (TRP 알고리즘 결과에서)
            red_zone_station_pks = set()
            for idx, is_red_zone in enumerate(trp_algorithm.R):
                if is_red_zone == 1:
                    red_zone_station_pks.add(trp_algorithm.P_idx[idx])
            
            csv_path, plot_path = analyze_zone_demand(db_for_analysis, reduction_folder_path, logger, red_zone_station_pks)
            logger.info("존별 수요 분석 완료!")
            
            # 4. 정류장 분포 지도 생성
            logger.info("=" * 60)
            logger.info("정류장 분포 지도 생성 시작")
            logger.info("=" * 60)
            
            map_path = create_station_map(db_for_analysis, red_zone_station_pks, reduction_folder_path, logger)
            logger.info("정류장 분포 지도 생성 완료!")
        else:
            logger.info("샘플링 실행이 비활성화되어 있습니다.")
        
        logger.info("=" * 80)
        logger.info("모든 프로세스가 완료되었습니다!")
        logger.info("=" * 80)
        
        # 생성된 파일 정보 출력
        logger.info("생성된 파일들:")
        logger.info(f"  - 레드존 파일: {red_zone_file_path}")
        logger.info(f"  - 수요감소율 폴더: {reduction_folder_path}")
        if param.enable_sampling:
            logger.info(f"  - 샘플링 파일들: {os.path.join(reduction_folder_path, 'sampling_*.csv')}")
            logger.info(f"  - 수요 분포 그래프: {os.path.join(reduction_folder_path, 'hourly_demand_histogram.png')}")
            logger.info(f"  - 존별 수요 분석 CSV: {os.path.join(reduction_folder_path, 'zone_demand_analysis.csv')}")
            logger.info(f"  - 존별 수요 분석 그래프: {os.path.join(reduction_folder_path, 'zone_demand_analysis.png')}")
            logger.info(f"  - 존별 수요 비교 그래프: {os.path.join(reduction_folder_path, 'zone_demand_comparison.png')}")
            logger.info(f"  - 정류장 분포 지도: {os.path.join(reduction_folder_path, 'station_distribution_map.html')}")
        
    except Exception as e:
        logger.error(f"프로세스 실행 중 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()