import json
import os
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'parking.imported.geojson'


def load_parking():
    """Fail early on inconsistent IDs/capacities or unsupported geometry."""
    path = Path(os.getenv('PARKING_DATA_FILE', str(DEFAULT_FILE)))
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list):
        raise ValueError('Parking data must be a GeoJSON FeatureCollection')
    if not isinstance(data.get('is_example'), bool):
        raise ValueError('FeatureCollection must declare boolean is_example')
    ids = set()
    for feature in data['features']:
        props = feature.get('properties', {})
        area_id = props.get('id')
        if not isinstance(area_id, str) or not area_id or area_id in ids:
            raise ValueError('Each parking area needs a unique string properties.id')
        ids.add(area_id)
        capacity = props.get('capacity')
        if type(capacity) is not int or capacity <= 0:
            raise ValueError(f'{area_id}: capacity must be a positive integer')
        if not isinstance(props.get('name'), str) or not props['name']:
            raise ValueError(f'{area_id}: name is required')
        geometry = feature.get('geometry', {})
        if geometry.get('type') != 'Polygon':
            raise ValueError(f'{area_id}: only Polygon is supported in this demo')
        rings = geometry.get('coordinates', [])
        if not rings:
            raise ValueError(f'{area_id}: polygon needs rings')
        for ring in rings:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError(f'{area_id}: rings must be closed with at least 4 positions')
            for point in ring:
                if len(point) != 2 or any(type(v) not in (int, float) for v in point):
                    raise ValueError(f'{area_id}: expected [longitude, latitude]')
                if not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                    raise ValueError(f'{area_id}: coordinates outside WGS84 range')
    return data
