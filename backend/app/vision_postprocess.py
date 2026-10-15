"""Pure geometry for overlapping image tiles; no image-specific counts or ROI."""
def tile_origins(length, size=1024, overlap=0.25):
    if length <= size:
        return [0]
    stride = max(1, round(size * (1 - overlap)))
    origins = list(range(0, length - size + 1, stride))
    if origins[-1] != length - size:
        origins.append(length - size)
    return origins


def intersection_over_union(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    area_b = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return intersection / max(area_a + area_b - intersection, 1e-12)


def merge_detections(detections, threshold=0.5):
    # Bicycle/motorcycle are alternative classifications of a two-wheeler:
    # overlapping hypotheses compete, instead of being counted twice.
    def group(item):
        return 'person' if item['label'] == 'person' else 'two_wheeler'
    kept = []
    for candidate in sorted(detections, key=lambda item: item['confidence'], reverse=True):
        if not any(group(candidate) == group(old) and intersection_over_union(candidate['box'], old['box']) > threshold for old in kept):
            kept.append(candidate)
    return kept
