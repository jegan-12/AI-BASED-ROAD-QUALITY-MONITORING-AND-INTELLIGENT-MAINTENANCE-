import io
import math
from datetime import timedelta
from PIL import Image, ImageOps, UnidentifiedImageError
from .schemas import CaptureMetadata

Image.MAX_IMAGE_PIXELS = 20_000_000


def preprocess(raw: bytes, max_side=1600):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError("Image exceeds 20 megapixels")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((max_side, max_side))
            result = io.BytesIO()
            image.save(result, format="JPEG", quality=90)
            return result.getvalue(), image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Invalid or unsafe image") from exc


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union else 0


def nms(detections, threshold=0.35, overlap=0.5):
    kept = []
    for detection in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if detection.confidence < threshold:
            continue
        if not any(detection.defect_class == d.defect_class and iou(detection.bbox, d.bbox) > overlap for d in kept):
            kept.append(detection)
    return kept


def distance_m(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dlat, dlon = b-a, math.radians(lon2-lon1)
    h = math.sin(dlat/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def gps_at(metadata: CaptureMetadata, offset: float):
    if not metadata.gps_track:
        if offset != 0 or any(v is None for v in (metadata.latitude, metadata.longitude, metadata.gps_uncertainty_m)):
            raise ValueError("Image requires coordinates and uncertainty; video requires a GPS track")
        return metadata.latitude, metadata.longitude, metadata.gps_uncertainty_m
    track = metadata.gps_track
    for point in track:
        if abs(point.offset_seconds - offset) < 1e-6:
            return point.latitude, point.longitude, point.uncertainty_m
    for a, b in zip(track, track[1:]):
        if a.offset_seconds < offset < b.offset_seconds:
            if b.offset_seconds - a.offset_seconds > 10:
                raise ValueError("GPS interpolation gap exceeds 10 seconds")
            t = (offset-a.offset_seconds)/(b.offset_seconds-a.offset_seconds)
            delta_lon = (b.longitude-a.longitude+180) % 360 - 180
            lon = (a.longitude + t*delta_lon+180) % 360-180
            # Conservative extra uncertainty for interpolation, not a positional accuracy claim.
            extra = distance_m(a.latitude, a.longitude, b.latitude, b.longitude) / 2
            return a.latitude+t*(b.latitude-a.latitude), lon, max(a.uncertainty_m, b.uncertainty_m)+extra
    raise ValueError("GPS track does not cover frame timestamp")


def same_observation(previous, detection, lat, lon, uncertainty, offset):
    return (previous["class"] == detection.defect_class and
            0 < offset - previous["offset"] <= 5 and
            max(uncertainty, previous["uncertainty"]) <= 15 and
            distance_m(lat, lon, previous["lat"], previous["lon"]) <= 8 and
            iou(previous["bbox"], detection.bbox) >= 0.6)


def frames(path, kind, metadata, config):
    if kind == "image":
        raw, _ = preprocess(path.read_bytes())
        yield 0, 0.0, raw, gps_at(metadata, 0)
        return
    import cv2
    cap = cv2.VideoCapture(str(path))
    try:
        fps, count = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not cap.isOpened() or not math.isfinite(fps) or fps <= 0 or count <= 0:
            raise ValueError("Video cannot be decoded")
        duration = count / fps
        if duration > config.max_video_seconds:
            raise ValueError("Video exceeds duration limit")
        if not metadata.gps_track:
            raise ValueError("Video requires timestamped GPS track")
        offsets = [i * config.frame_interval_seconds for i in range(math.ceil(duration / config.frame_interval_seconds))]
        if len(offsets) > config.max_frames:
            raise ValueError("Video exceeds sample limit")
        positions = [gps_at(metadata, offset) for offset in offsets]
        for index, (offset, position) in enumerate(zip(offsets, positions)):
            cap.set(cv2.CAP_PROP_POS_MSEC, offset * 1000)
            ok, frame = cap.read()
            if not ok:
                raise ValueError("Video frame decode failed")
            height, width = frame.shape[:2]
            if width * height > Image.MAX_IMAGE_PIXELS:
                raise ValueError("Video frame exceeds pixel limit")
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.thumbnail((1600, 1600))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=90)
            yield index, offset, out.getvalue(), position
    finally:
        cap.release()

