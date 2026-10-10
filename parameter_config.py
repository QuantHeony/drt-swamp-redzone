
class ParameterConfig():
    # TRP 알고리즘 파라미터
    rr_dmd_alpha:float = 0.05
    smr_beta:float = 0.7
    smr_gamma:float = 0.4
    # Constrained variant (paper, Section 3.3 / scenario C1): restrict candidate stops
    # in BOTH stages (representative selection and similarity expansion) to the zones
    # listed here. None = unconstrained (default; patent / paper main results).
    candidate_zones: list | None = None   # e.g. [3] for centre-only

    # 샘플링 관련 파라미터
    enable_sampling: bool = True  # 샘플링 실행 여부
    sampling_days: int = 16  # 샘플링 일수
    distance_tolerance_lower: float = 0.85  # 거리 허용 범위 하한
    distance_tolerance_upper: float = 1.15  # 거리 허용 범위 상한
    max_iterations: int = 10000  # 최대 반복 횟수
