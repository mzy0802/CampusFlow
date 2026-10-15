"""Counts are per frame, never summed across a video (no tracking yet)."""


def congestion(count: int, capacity: int):
    if count < 0 or capacity <= 0:
        raise ValueError('Count must be nonnegative and capacity positive')
    percent = round(count / capacity * 100, 1)
    level = 'overloaded' if percent > 100 else 'crowded' if percent >= 80 else 'moderate' if percent >= 50 else 'clear'
    return {'count': count, 'capacity': capacity, 'percent': percent, 'level': level}


def summarize(samples, bicycle_capacity, person_capacity):
    if not samples:
        raise ValueError('No frames were decoded')
    def stats(key, capacity):
        values = [(sample.get('bicycle', 0) + sample.get('motorcycle', 0) + sample.get('uncertain_type', 0)) if key == 'two_wheeler'
                  else sample.get(key, 0) for sample in samples]
        return {
            'latest': congestion(values[-1], capacity),
            'peak': congestion(max(values), capacity),
            'mean_count': round(sum(values) / len(values), 2),
        }
    return {'uncertain_type': stats('uncertain_type', bicycle_capacity),
            'bicycle': stats('bicycle', bicycle_capacity),
            'motorcycle': stats('motorcycle', bicycle_capacity),
            'two_wheeler': stats('two_wheeler', bicycle_capacity),
            'person': stats('person', person_capacity),
            'classification_note': 'motorcycle 为电动两轮车/摩托车候选；尚未具备专用电动车分类能力。',
            'vehicle_capacity_basis': 'shared_two_wheeler_parking_capacity',
            'quality_status': 'unvalidated_general_model',
            'warning': '通用模型可能严重漏检，检测比例低不代表实际空闲；需核验后使用。',
            'sampled_frames': len(samples),
            'counting_method': 'per_frame_not_unique_visitors',
            'display_basis': 'latest_sample'}
