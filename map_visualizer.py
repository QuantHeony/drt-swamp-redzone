import os
import json
import logging
from typing import List, Dict, Set
import numpy as np

# sklearn을 선택적으로 import (없으면 클러스터링 없이 진행)
try:
    from sklearn.cluster import DBSCAN
    from scipy.spatial import ConvexHull
    from scipy.stats import gaussian_kde
    CLUSTERING_AVAILABLE = True
    CONVEX_HULL_AVAILABLE = True
except ImportError:
    try:
        from scipy.spatial import ConvexHull
        CLUSTERING_AVAILABLE = False
        CONVEX_HULL_AVAILABLE = True
    except ImportError:
        CLUSTERING_AVAILABLE = False
        CONVEX_HULL_AVAILABLE = False

from logic.db_class import DbClass
from logic.station import Station


class MapVisualizer:
    def __init__(self, db: DbClass, logger: logging.Logger):
        self.db = db
        self.logger = logger
        
    def create_station_map(self, red_zone_station_pks: Set[int], reduction_folder_path: str):
        """정류장 분포 지도 생성"""
        self.logger.info("정류장 분포 지도 생성 시작...")
        
        # 정류장 데이터 준비
        stations_data = []
        red_zones = []
        normal_stations = []
        
        for station_pk, station in self.db.station_dic.items():
            station_info = {
                'name': station.station_name,
                'pk': station.station_pk,
                'lat': station.lat,
                'lon': station.lon,
                'zone_pk': station.zone_pk,
                'is_red_zone': station_pk in red_zone_station_pks
            }
            stations_data.append(station_info)
            
            if station_pk in red_zone_station_pks:
                red_zones.append(station_info)
            else:
                normal_stations.append(station_info)
        
        # 레드존 정류장에 대해서만 영역 생성 (컨벡스 헐 또는 클러스터링)
        red_zone_areas = self._create_red_zone_areas(red_zones)
        
        # HTML 생성
        html_content = self._generate_html_map(stations_data, red_zone_areas, red_zones, normal_stations)
        
        # 파일 저장
        map_path = os.path.join(reduction_folder_path, "station_distribution_map.html")
        with open(map_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"정류장 분포 지도 저장: {map_path}")
        return map_path
    
    def _create_red_zone_areas(self, stations_data: List[Dict]) -> List[Dict]:
        """레드존 정류장에 대해 영역(컨벡스 헐) 생성"""
        areas = []
        
        if not stations_data:
            self.logger.warning("레드존 정류장이 없습니다.")
            return areas
        
        try:
            self.logger.info(f"레드존 영역 생성... (대상: {len(stations_data)}개 정류장)")
            
            # 컨벡스 헐을 사용한 영역 생성
            if CONVEX_HULL_AVAILABLE and len(stations_data) >= 3:
                coords = np.array([[station['lat'], station['lon']] for station in stations_data])
                
                try:
                    # 전체 레드존 정류장에 대한 컨벡스 헐 생성
                    hull = ConvexHull(coords)
                    hull_points = coords[hull.vertices]
                    
                    # 중심점 계산
                    center_lat = np.mean([s['lat'] for s in stations_data])
                    center_lon = np.mean([s['lon'] for s in stations_data])
                    
                    areas.append({
                        'id': 0,
                        'type': 'convex_hull',
                        'center_lat': float(center_lat),
                        'center_lon': float(center_lon),
                        'hull_points': [[float(point[0]), float(point[1])] for point in hull_points],
                        'stations': stations_data,
                        'red_zone_count': len(stations_data),
                        'total_count': len(stations_data)
                    })
                    
                    self.logger.info(f"레드존 컨벡스 헐 영역 생성 완료: {len(hull_points)}개 꼭짓점")
                    
                except Exception as e:
                    self.logger.warning(f"컨벡스 헐 생성 실패: {e}, 클러스터링으로 대체")
                    return self._perform_clustering_fallback(stations_data)
            
            # 컨벡스 헐을 사용할 수 없는 경우 클러스터링 사용
            elif CLUSTERING_AVAILABLE:
                return self._perform_clustering_fallback(stations_data)
            else:
                self.logger.warning("scipy와 sklearn이 모두 없어 영역 생성을 건너뜁니다.")
        
        except Exception as e:
            self.logger.error(f"레드존 영역 생성 중 오류 발생: {e}")
        
        return areas
    
    def _perform_clustering_fallback(self, stations_data: List[Dict]) -> List[Dict]:
        """클러스터링을 사용한 대체 영역 생성"""
        clusters = []
        
        if not CLUSTERING_AVAILABLE:
            return clusters
            
        try:
            # 좌표 데이터 준비
            coords = np.array([[station['lat'], station['lon']] for station in stations_data])
            
            # DBSCAN 클러스터링
            clustering = DBSCAN(eps=0.003, min_samples=2, metric='haversine')
            cluster_labels = clustering.fit_predict(np.radians(coords))
            
            # 클러스터 정보 생성
            unique_labels = set(cluster_labels)
            
            for label in unique_labels:
                if label == -1:  # 노이즈 포인트는 제외
                    continue
                    
                cluster_stations = [stations_data[i] for i, l in enumerate(cluster_labels) if l == label]
                
                if len(cluster_stations) >= 2:
                    # 클러스터 중심점 계산
                    center_lat = np.mean([s['lat'] for s in cluster_stations])
                    center_lon = np.mean([s['lon'] for s in cluster_stations])
                    
                    # 클러스터 반경 계산
                    import math
                    max_distance = 0
                    for station in cluster_stations:
                        lat1, lon1 = math.radians(center_lat), math.radians(center_lon)
                        lat2, lon2 = math.radians(station['lat']), math.radians(station['lon'])
                        
                        dlat = lat2 - lat1
                        dlon = lon2 - lon1
                        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                        c = 2 * math.asin(math.sqrt(a))
                        distance = 6371000 * c
                        max_distance = max(max_distance, distance)
                    
                    max_distance = max_distance * 0.5
                    
                    clusters.append({
                        'id': int(label),
                        'type': 'cluster',
                        'center_lat': float(center_lat),
                        'center_lon': float(center_lon),
                        'radius': float(max_distance),
                        'stations': cluster_stations,
                        'red_zone_count': int(sum(1 for s in cluster_stations if s['is_red_zone'])),
                        'total_count': int(len(cluster_stations))
                    })
        
        except Exception as e:
            self.logger.error(f"클러스터링 중 오류 발생: {e}")
        
        return clusters
    
    def _generate_html_map(self, stations_data: List[Dict], clusters: List[Dict], 
                          red_zones: List[Dict], normal_stations: List[Dict]) -> str:
        """HTML 지도 생성"""
        
        # 지도 중심점 계산
        if stations_data:
            center_lat = np.mean([s['lat'] for s in stations_data])
            center_lon = np.mean([s['lon'] for s in stations_data])
        else:
            center_lat, center_lon = 36.5, 127.3  # 한국 중앙
        
        # 존별 정류장 통계 계산
        zone_stats = {}
        for station in stations_data:
            zone_pk = station['zone_pk']
            if zone_pk not in zone_stats:
                zone_stats[zone_pk] = {
                    'total': 0,
                    'red_zone': 0,
                    'normal': 0
                }
            
            zone_stats[zone_pk]['total'] += 1
            if station['is_red_zone']:
                zone_stats[zone_pk]['red_zone'] += 1
            else:
                zone_stats[zone_pk]['normal'] += 1
        
        # 정류장 데이터를 JSON으로 변환
        stations_json = json.dumps(stations_data, ensure_ascii=False)
        clusters_json = json.dumps(clusters, ensure_ascii=False)
        zone_stats_json = json.dumps(zone_stats, ensure_ascii=False)
        
        html_template = f'''
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TRP 정류장 분포 지도</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body {{
            margin: 0;
            font-family: Arial, sans-serif;
        }}
        #map {{
            height: 100vh;
            width: 100%;
        }}
        .info-panel {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 15px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
            z-index: 1000;
            min-width: 200px;
        }}
        .legend {{
            margin-top: 10px;
        }}
        .legend-item {{
            margin: 5px 0;
            display: flex;
            align-items: center;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            margin-right: 10px;
            border-radius: 50%;
            border: 2px solid #333;
        }}
        .cluster-info {{
            background-color: #f0f0f0;
            padding: 5px;
            margin: 2px 0;
            border-radius: 3px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div class="info-panel">
        <h3>TRP 정류장 분포</h3>
        <div>
            <strong>총 정류장:</strong> {len(stations_data)}개<br>
            <strong>레드존:</strong> {len(red_zones)}개<br>
            <strong>일반 정류장:</strong> {len(normal_stations)}개<br>
            <strong>레드존 영역:</strong> {len(clusters)}개
        </div>
        <div class="legend">
            <h4>범례</h4>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #ff4444;"></div>
                <span>레드존 정류장</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: #4444ff;"></div>
                <span>일반 정류장</span>
            </div>
            <div class="legend-item">
                <div class="legend-color" style="background-color: rgba(255,0,0,0.15); border: 2px dashed red;"></div>
                <span>레드존 영역</span>
            </div>
        </div>
        <div id="cluster-info">
            <h4>레드존 영역 정보</h4>
            <div id="cluster-details"></div>
        </div>
        <div id="zone-info">
            <h4>존별 정류장 현황</h4>
            <div id="zone-details"></div>
        </div>
    </div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        // 지도 초기화
        const map = L.map('map').setView([{center_lat}, {center_lon}], 10);
        
        // 지도 타일 추가
        L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
            attribution: '© OpenStreetMap contributors'
        }}).addTo(map);
        
        // 데이터 로드
        const stations = {stations_json};
        const redZoneAreas = {clusters_json};
        const zoneStats = {zone_stats_json};
        
        // 레드존 영역 오버레이 추가
        redZoneAreas.forEach(area => {{
            if (area.type === 'convex_hull' && area.hull_points) {{
                // 컨벡스 헐 폴리곤 생성
                const polygon = L.polygon(area.hull_points, {{
                    color: 'red',
                    fillColor: 'red',
                    fillOpacity: 0.15,
                    weight: 2,
                    dashArray: '10, 5'
                }}).addTo(map);
                
                const popupContent = `
                    <strong>레드존 영역</strong><br>
                    레드존 정류장: ${{area.red_zone_count}}개<br>
                    영역 유형: 컨벡스 헐<br>
                    꼭짓점: ${{area.hull_points.length}}개
                `;
                polygon.bindPopup(popupContent);
            }} else if (area.type === 'cluster') {{
                // 클러스터 원형 영역 생성 (대체)
                const circle = L.circle([area.center_lat, area.center_lon], {{
                    color: 'orange',
                    fillColor: 'orange',
                    fillOpacity: 0.2,
                    radius: area.radius,
                    weight: 2,
                    dashArray: '5, 5'
                }}).addTo(map);
                
                const popupContent = `
                    <strong>레드존 클러스터 ${{area.id}}</strong><br>
                    총 정류장: ${{area.total_count}}개<br>
                    레드존: ${{area.red_zone_count}}개<br>
                    반경: ${{Math.round(area.radius)}}m
                `;
                circle.bindPopup(popupContent);
            }}
        }});
        
        // 정류장 마커 추가
        stations.forEach(station => {{
            const color = station.is_red_zone ? '#ff4444' : '#4444ff';
            const fillColor = station.is_red_zone ? '#ff6666' : '#6666ff';
            
            const marker = L.circleMarker([station.lat, station.lon], {{
                radius: 6,
                fillColor: fillColor,
                color: color,
                weight: 2,
                opacity: 0.8,
                fillOpacity: 0.6
            }}).addTo(map);
            
            const popupContent = `
                <strong>${{station.name}}</strong><br>
                정류장 ID: ${{station.pk}}<br>
                존 ID: ${{station.zone_pk}}<br>
                유형: ${{station.is_red_zone ? '레드존' : '일반 정류장'}}<br>
                좌표: (${{station.lat.toFixed(6)}}, ${{station.lon.toFixed(6)}})
            `;
            marker.bindPopup(popupContent);
        }});
        
        // 레드존 영역 정보 표시
        const clusterDetails = document.getElementById('cluster-details');
        redZoneAreas.forEach(area => {{
            const div = document.createElement('div');
            div.className = 'cluster-info';
            
            if (area.type === 'convex_hull') {{
                div.innerHTML = `
                    레드존 영역: ${{area.red_zone_count}}개 정류장<br>
                    (컨벡스 헐, ${{area.hull_points.length}}개 꼭짓점)
                `;
            }} else if (area.type === 'cluster') {{
                div.innerHTML = `
                    클러스터 ${{area.id}}: ${{area.total_count}}개 
                    (레드존: ${{area.red_zone_count}}개)
                `;
            }}
            clusterDetails.appendChild(div);
        }});
        
        // 존별 정류장 정보 표시
        const zoneDetails = document.getElementById('zone-details');
        const totalStations = stations.length;
        
        Object.keys(zoneStats).sort((a, b) => parseInt(a) - parseInt(b)).forEach(zoneId => {{
            const stats = zoneStats[zoneId];
            const zonePercentage = ((stats.total / totalStations) * 100).toFixed(1);
            const redZonePercentage = stats.total > 0 ? ((stats.red_zone / stats.total) * 100).toFixed(1) : '0.0';
            
            const div = document.createElement('div');
            div.className = 'cluster-info';
            div.innerHTML = `
                존 ${{zoneId}}: ${{stats.total}}개 (${{zonePercentage}}%)<br>
                └ 레드존: ${{stats.red_zone}}개 (${{redZonePercentage}}%)
            `;
            zoneDetails.appendChild(div);
        }});
        
        // 지도 범위 조정
        if (stations.length > 0) {{
            const group = new L.featureGroup();
            stations.forEach(station => {{
                group.addLayer(L.marker([station.lat, station.lon]));
            }});
            map.fitBounds(group.getBounds().pad(0.1));
        }}
    </script>
</body>
</html>
'''
        return html_template


def create_station_map(db: DbClass, red_zone_station_pks: Set[int], reduction_folder_path: str, logger: logging.Logger):
    """정류장 분포 지도 생성 함수"""
    visualizer = MapVisualizer(db, logger)
    return visualizer.create_station_map(red_zone_station_pks, reduction_folder_path)