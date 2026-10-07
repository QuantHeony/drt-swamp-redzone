import logging
import os
import sys
from datetime import datetime
from typing import List

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
    log_file = os.path.join(log_dir, f"iteration_process_{now_str}.log")
    
    # 루트 로거 설정 (중복 방지)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # 기존 핸들러 모두 제거
    
    # 커스텀 로거 생성
    logger = logging.getLogger("iteration_process")
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


def run_red_zone_algorithm_with_alpha(logger: logging.Logger, param: ParameterConfig, alpha: float, criteria: int = 2) -> tuple:
    """
    특정 alpha 값으로 레드존 알고리즘 실행
    
    Args:
        logger: 로거 인스턴스
        param: 파라미터 설정
        alpha: rr_dmd_alpha 값
        criteria: 데이터 로딩 기준 (1: demand.csv, 2: admin_demand/*.xlsx)
        
    Returns:
        tuple: (생성된 레드존 파일 경로, 수요감소율 폴더 경로, trp_algorithm 객체)
    """
    logger.info("=" * 60)
    logger.info(f"TRP 레드존 알고리즘 시작 (alpha={alpha})")
    logger.info("=" * 60)
    
    # alpha 값 설정
    param.rr_dmd_alpha = alpha
    
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
    logger.info(f"TRP 레드존 알고리즘 완료! (alpha={alpha})")
    
    # 생성된 레드존 파일 경로, 수요감소율 폴더 경로, trp_algorithm 객체 반환
    return trp_algorithm.red_zone_file_path, trp_algorithm.reduction_folder_path, trp_algorithm


def run_sampling_algorithm(logger: logging.Logger, param: ParameterConfig, red_zone_file_path: str, reduction_folder_path: str, alpha: float):
    """
    샘플링 알고리즘 실행
    
    Args:
        logger: 로거 인스턴스
        param: 파라미터 설정
        red_zone_file_path: 레드존 파일 경로
        reduction_folder_path: 수요감소율 폴더 경로
        alpha: rr_dmd_alpha 값
    """
    logger.info("=" * 60)
    logger.info(f"샘플링 알고리즘 시작 (alpha={alpha})")
    logger.info("=" * 60)
    
    if os.path.exists(red_zone_file_path):
        run_sampling_process(red_zone_file_path, param, logger, reduction_folder_path)
        logger.info(f"샘플링 알고리즘 완료! (alpha={alpha})")
    else:
        logger.error(f"레드존 파일을 찾을 수 없습니다: {red_zone_file_path}")


def run_single_iteration(logger: logging.Logger, base_param: ParameterConfig, alpha: float, iteration_num: int) -> dict:
    """
    단일 반복 실행
    
    Args:
        logger: 로거 인스턴스
        base_param: 기본 파라미터 설정
        alpha: rr_dmd_alpha 값
        iteration_num: 반복 번호
        
    Returns:
        dict: 결과 정보
    """
    logger.info("=" * 100)
    logger.info(f"반복 {iteration_num}: alpha={alpha} 시작")
    logger.info("=" * 100)
    
    # 파라미터 복사 (원본 변경 방지)
    param = ParameterConfig()
    param.rr_dmd_alpha = alpha
    param.smr_beta = base_param.smr_beta
    param.smr_gamma = base_param.smr_gamma
    param.enable_sampling = base_param.enable_sampling
    param.sampling_days = base_param.sampling_days
    
    try:
        # 1. 레드존 알고리즘 실행
        red_zone_file_path, reduction_folder_path, trp_algorithm = run_red_zone_algorithm_with_alpha(
            logger, param, alpha, criteria=2
        )
        
        result_info = {
            'alpha': alpha,
            'iteration': iteration_num,
            'red_zone_file_path': red_zone_file_path,
            'reduction_folder_path': reduction_folder_path,
            'red_zone_count': sum(trp_algorithm.R),
            'total_stations': len(trp_algorithm.P),
            'iterations': trp_algorithm.iter,
            'success': True,
            'error': None
        }
        
        # 2. 샘플링 알고리즘 실행 (설정에 따라)
        if param.enable_sampling:
            run_sampling_algorithm(logger, param, red_zone_file_path, reduction_folder_path, alpha)
            
            # 3. 존별 수요 분석 실행
            logger.info("=" * 60)
            logger.info(f"존별 수요 분석 시작 (alpha={alpha})")
            logger.info("=" * 60)
            
            # 데이터베이스 다시 로드 (분석용)
            db_for_analysis = DbClass(criteria=2, logger=logger)
            
            # 레드존 정류장 PK 세트 생성 (TRP 알고리즘 결과에서)
            red_zone_station_pks = set()
            for idx, is_red_zone in enumerate(trp_algorithm.R):
                if is_red_zone == 1:
                    red_zone_station_pks.add(trp_algorithm.P_idx[idx])
            
            csv_path, plot_path = analyze_zone_demand(db_for_analysis, reduction_folder_path, logger, red_zone_station_pks)
            logger.info(f"존별 수요 분석 완료! (alpha={alpha})")
            
            # 4. 정류장 분포 지도 생성
            logger.info("=" * 60)
            logger.info(f"정류장 분포 지도 생성 시작 (alpha={alpha})")
            logger.info("=" * 60)
            
            map_path = create_station_map(db_for_analysis, red_zone_station_pks, reduction_folder_path, logger)
            logger.info(f"정류장 분포 지도 생성 완료! (alpha={alpha})")
            
            result_info.update({
                'csv_path': csv_path,
                'plot_path': plot_path,
                'map_path': map_path
            })
        else:
            logger.info(f"샘플링 실행이 비활성화되어 있습니다. (alpha={alpha})")
        
        logger.info("=" * 100)
        logger.info(f"반복 {iteration_num}: alpha={alpha} 완료")
        logger.info("=" * 100)
        
        return result_info
        
    except Exception as e:
        logger.error(f"반복 {iteration_num} (alpha={alpha}) 실행 중 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        return {
            'alpha': alpha,
            'iteration': iteration_num,
            'success': False,
            'error': str(e)
        }


def main():
    """메인 실행 함수"""
    logger = setup_logging()
    
    try:
        # 파라미터 설정
        base_param = ParameterConfig()
        
        # alpha 값 범위 설정 (0.05 ~ 0.4, 0.05 간격)
        alpha_values = [round(0.05 + i * 0.05, 2) for i in range(8)]  # [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4]
        
        logger.info("=" * 120)
        logger.info("TRP 프로젝트 반복 실행 프로세스")
        logger.info("=" * 120)
        logger.info(f"기본 파라미터 설정:")
        logger.info(f"  - TRP beta: {base_param.smr_beta}")
        logger.info(f"  - TRP gamma: {base_param.smr_gamma}")
        logger.info(f"  - 샘플링 활성화: {base_param.enable_sampling}")
        if base_param.enable_sampling:
            logger.info(f"  - 샘플링 일수: {base_param.sampling_days}")
        logger.info(f"반복 alpha 값: {alpha_values}")
        logger.info(f"총 반복 수: {len(alpha_values)}")
        
        # 결과 저장용 리스트
        all_results = []
        
        # 각 alpha 값에 대해 반복 실행
        for i, alpha in enumerate(alpha_values, 1):
            result = run_single_iteration(logger, base_param, alpha, i)
            all_results.append(result)
        
        # 전체 결과 요약
        logger.info("=" * 120)
        logger.info("모든 반복이 완료되었습니다!")
        logger.info("=" * 120)
        
        # 성공/실패 요약
        successful = [r for r in all_results if r['success']]
        failed = [r for r in all_results if not r['success']]
        
        logger.info(f"성공한 반복: {len(successful)}/{len(all_results)}")
        if failed:
            logger.warning(f"실패한 반복: {len(failed)}개")
            for fail in failed:
                logger.warning(f"  - Alpha {fail['alpha']}: {fail['error']}")
        
        # 성공한 결과들의 상세 정보
        logger.info("\n반복 결과 요약:")
        logger.info("-" * 80)
        logger.info(f"{'Alpha':<8} {'레드존':<10} {'전체정류장':<10} {'비율(%)':<10} {'반복수':<8} {'폴더경로'}")
        logger.info("-" * 80)
        
        for result in successful:
            red_ratio = (result['red_zone_count'] / result['total_stations']) * 100
            folder_name = os.path.basename(result['reduction_folder_path'])
            logger.info(f"{result['alpha']:<8} {result['red_zone_count']:<10} {result['total_stations']:<10} "
                       f"{red_ratio:<9.2f} {result['iterations']:<8} {folder_name}")
        
        logger.info("=" * 120)
        logger.info("생성된 모든 파일들:")
        for result in successful:
            logger.info(f"\nAlpha {result['alpha']}:")
            logger.info(f"  - 레드존 파일: {result['red_zone_file_path']}")
            logger.info(f"  - 결과 폴더: {result['reduction_folder_path']}")
            if 'csv_path' in result:
                logger.info(f"  - 존별 수요 분석 CSV: {result['csv_path']}")
                logger.info(f"  - 존별 수요 분석 그래프: {result['plot_path']}")
                logger.info(f"  - 정류장 분포 지도: {result['map_path']}")
        
    except Exception as e:
        logger.error(f"전체 프로세스 실행 중 오류 발생: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    main()