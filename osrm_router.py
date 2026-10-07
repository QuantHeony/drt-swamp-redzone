import requests

class OsrmRouter:
    def __init__(self, base_url="http://localhost:5000", profile="driving"):
        """
        :param base_url: OSRM 서버 주소
        :param profile: routing profile - driving / walking / cycling 등
        """
        self.base_url = base_url.rstrip("/")
        self.profile = profile

    def get_route(self, start_lon, start_lat, end_lon, end_lat):
        """
        두 지점 간 경로의 거리(m)와 시간(sec)을 반환합니다.

        :param start_lon: 출발지 경도
        :param start_lat: 출발지 위도
        :param end_lon: 도착지 경도
        :param end_lat: 도착지 위도
        :return: (distance_in_meters, duration_in_seconds)
        """
        coords = f"{start_lon},{start_lat};{end_lon},{end_lat}"
        url = f"{self.base_url}/route/v1/{self.profile}/{coords}?overview=false"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "Ok":
                raise ValueError(f"OSRM returned error: {data.get('message', 'Unknown error')}")

            route = data["routes"][0]
            return route["distance"], route["duration"]

        except Exception as e:
            print(f"[ERROR] Failed to get route: {e}")
            return None, None
