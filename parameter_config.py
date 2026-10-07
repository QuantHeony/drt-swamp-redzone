
class ParameterConfig():
    # TRP 알고리즘 파라미터
    rr_dmd_alpha:float = 0.05
    smr_beta:float = 0.7
    smr_gamma:float = 0.4
    
    # 샘플링 관련 파라미터
    enable_sampling: bool = True  # 샘플링 실행 여부
    sampling_days: int = 16  # 샘플링 일수
    distance_tolerance_lower: float = 0.85  # 거리 허용 범위 하한
    distance_tolerance_upper: float = 1.15  # 거리 허용 범위 상한
    max_iterations: int = 10000  # 최대 반복 횟수
