from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from enum import IntEnum
from logic.utils import parse_datetime


class CodePassengerCallStatus(IntEnum):
    DONE = 3  # 이용완료
    NOSHOW = 8
    CANCEL = 9  # 호출취소

    @classmethod
    def from_value(cls, value: int) -> Optional['CodePassengerCallStatus']:
        return cls._value2member_map_.get(value)


@dataclass
class PassengerCall:
    seq: int
    call_pk: int
    passenger_pk: int
    bus_pk: int
    driver_pk: int
    status: Optional[CodePassengerCallStatus]
    call_time: datetime
    o_station_pk: int
    d_station_pk: int
    getoff_station_pk: int
    est_geton_time: datetime
    est_getoff_time: datetime
    geton_time: datetime
    getoff_time: datetime
    extra_cnt: int
    adult_cnt: int
    teenager_cnt: int
    child_cnt: int
    seat_no: str
    created: datetime

    @classmethod
    def from_doc(cls, doc: list) -> 'PassengerCall':
        return cls(
            seq=int(doc[0]),
            call_pk=int(doc[1]),
            passenger_pk=int(doc[2]),
            bus_pk=int(doc[3]),
            driver_pk=int(doc[4]),
            status=CodePassengerCallStatus.from_value(int(doc[5])),
            call_time=parse_datetime(doc[6]),
            o_station_pk=int(doc[7]),
            d_station_pk=int(doc[8]),
            getoff_station_pk=int(doc[9]),
            est_geton_time=parse_datetime(doc[10]),
            est_getoff_time=parse_datetime(doc[11]),
            geton_time=parse_datetime(doc[12]),
            getoff_time=parse_datetime(doc[13]),
            extra_cnt=int(doc[14]),
            adult_cnt=int(doc[15]),
            teenager_cnt=int(doc[16]),
            child_cnt=int(doc[17]),
            seat_no=doc[18],
            created=parse_datetime(doc[24]),
        )