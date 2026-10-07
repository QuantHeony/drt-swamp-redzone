from dataclasses import dataclass


@dataclass
class Station:
    station_pk: int
    station_name: str
    station_name_eng: str
    lon: float
    lat: float
    address: str
    gb: str
    demand_cnt: float
    zone_pk: int
    idx:int

    @classmethod
    def from_doc(cls, doc: list) -> 'Station':
        return cls(
            station_pk=int(doc[1]),
            station_name=doc[2],
            station_name_eng=doc[3],
            lon=float(doc[4]),
            lat=float(doc[5]),
            address=doc[6],
            gb=doc[7],
            demand_cnt=float(doc[8]),
            zone_pk=int(doc[9]),
            idx = 0
        )

    def __repr__(self) -> str:
        return (
            f"Station(station_pk={self.station_pk}, zone_pk={self.zone_pk}, "
            f"station_name='{self.station_name}', lon={self.lon}, lat={self.lat}, demand_cnt={self.demand_cnt})"
        )
