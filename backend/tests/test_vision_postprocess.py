from app.vision_postprocess import merge_detections, tile_origins
from app.vision_metrics import summarize


def test_tiles_cover_final_edge_and_small_images():
    assert tile_origins(400) == [0]
    starts = tile_origins(4096)
    assert starts[0] == 0 and starts[-1] + 1024 == 4096
    assert all(b - a <= 1024 for a, b in zip(starts, starts[1:]))
    assert len(starts) == len(set(starts))


def test_same_vehicle_different_class_is_not_counted_twice():
    raw = [
        {'label': 'bicycle', 'confidence': .6, 'box': [0, 0, .4, .4]},
        {'label': 'motorcycle', 'confidence': .8, 'box': [.01, .01, .41, .41]},
        {'label': 'motorcycle', 'confidence': .7, 'box': [.6, .6, .9, .9]},
        {'label': 'person', 'confidence': .9, 'box': [0, 0, .4, .4]},
    ]
    kept = merge_detections(raw)
    assert len(kept) == 3
    assert sum(item['label'] == 'motorcycle' for item in kept) == 2
    assert sum(item['label'] == 'person' for item in kept) == 1


def test_total_peak_uses_simultaneous_frame_not_sum_of_class_peaks():
    result = summarize([{'bicycle': 80, 'motorcycle': 40, 'person': 5},
                        {'bicycle': 10, 'motorcycle': 90, 'person': 3}], 100, 5)
    assert result['two_wheeler']['latest']['count'] == 100
    assert result['two_wheeler']['peak']['count'] == 120
    assert result['two_wheeler']['peak']['percent'] == 120
    assert result['motorcycle']['latest']['count'] == 90
    assert result['bicycle']['peak']['count'] == 80
    assert result['quality_status'] == 'unvalidated_general_model'
