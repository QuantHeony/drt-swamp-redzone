from datetime import datetime
from typing import Optional


def parse_datetime(datetime_str: str) -> Optional[datetime]:
    """
    지정된 형식의 날짜/시간 문자열을 datetime 객체로 변환.

    Args:
        datetime_str (str): 변환할 날짜/시간 문자열.

    Returns:
        Optional[datetime]: 변환된 datetime 객체 또는 None.
    """
    try:
        return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
