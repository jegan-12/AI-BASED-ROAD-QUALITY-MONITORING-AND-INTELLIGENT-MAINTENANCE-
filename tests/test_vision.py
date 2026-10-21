import io
from datetime import datetime, timezone
import pytest
from PIL import Image
from backend.app.schemas import CaptureMetadata, Detection
from backend.app.vision import preprocess, nms, iou, gps_at, distance_m, same_observation, frames
from backend.app.scoring import severity, load_calibration
from backend.app.config import settings
from ml.calibrate import fit, interpolate


def det(cls="pothole", conf=.9, bbox=None):
    return Detection(defect_class=cls, confidence=conf, bbox=bbox or [.2,.2,.5,.5])


def test_preprocess_resizes_orients_and_converts():
    image = Image.new("RGBA", (2400, 1200), "red")
    out = io.BytesIO()
    image.save(out, "PNG")
    raw, size = preprocess(out.getvalue())
    assert size == (1600, 800)
    assert Image.open(io.BytesIO(raw)).mode == "RGB"


def test_invalid_image():
    with pytest.raises(ValueError):
        preprocess(b"not an image")


def test_exif_orientation():
    image = Image.new("RGB", (80, 40))
    exif = Image.Exif()
    exif[274] = 6
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    _, size = preprocess(out.getvalue())
    assert size == (40, 80)


def test_nms_class_aware_and_thresholded():
    result = nms([det(), det(conf=.8), det(cls="rutting"), det(conf=.1, bbox=[.7,.7,.9,.9])])
    assert len(result) == 2
    assert {d.defect_class for d in result} == {"pothole", "rutting"}
    assert iou([0,0,1,1], [0,0,1,1]) == 1


def test_severity_not_confidence_or_physical_area():
    assert severity(det(conf=.4))[0] == severity(det(conf=.99))[0]
    score, reasons = severity(det())
    assert 40 < score < 100
    assert reasons["area_source"] == "bounding_box_proxy"
    assert reasons["calibration_version"] is None


def test_monotonic_calibration():
    knots = fit([{"raw_score":x,"expert_score":y} for x,y in [(10,20),(20,60),(30,40),(40,90)]])
    assert knots == [[10,20],[20,50],[30,50],[40,90]]
    assert interpolate(knots,25) == 50


def test_calibration_rejects_unprovenanced(tmp_path):
    path=tmp_path/'cal.json'
    path.write_text('{"knots":[[0,0],[100,100]]}')
    with pytest.raises(ValueError):
        load_calibration(path)


def meta(track=None, **kwargs):
    return CaptureMetadata(captured_at=datetime.now(timezone.utc), gps_track=track or [], **kwargs)


def test_gps_interpolation_inflates_uncertainty():
    data=meta([{"offset_seconds":0,"latitude":12,"longitude":77,"uncertainty_m":3},
               {"offset_seconds":4,"latitude":12.00004,"longitude":77,"uncertainty_m":4}])
    lat,lon,uncertainty=gps_at(data,2)
    assert lat == pytest.approx(12.00002)
    assert lon == pytest.approx(77)
    assert uncertainty > 4
    with pytest.raises(ValueError):
        gps_at(data,5)


def test_gps_gap_and_no_static_video_fallback():
    with pytest.raises(ValueError):
        gps_at(meta(latitude=12,longitude=77,gps_uncertainty_m=5),2)
    track=[{"offset_seconds":t,"latitude":12,"longitude":77,"uncertainty_m":5} for t in [0,20]]
    with pytest.raises(ValueError):
        gps_at(meta(track),10)


def test_duplicate_association_requires_all_evidence():
    prev={"class":"pothole","offset":0,"lat":12,"lon":77,"uncertainty":5,"bbox":[.2,.2,.5,.5]}
    assert same_observation(prev,det(),12,77,5,2)
    assert not same_observation(prev,det(),12,77,30,2)
    assert not same_observation(prev,det(),12,77,5,0)
    assert not same_observation(prev,det(),12.1,77,5,2)
    assert distance_m(0,0,0,1) == pytest.approx(111195,rel=.001)


def test_video_decode_and_gps(tmp_path):
    import cv2
    import numpy as np
    path=tmp_path/'clip.avi'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,48))
    assert writer.isOpened()
    for _ in range(25):
        writer.write(np.zeros((48,64,3),dtype=np.uint8))
    writer.release()
    track=[{"offset_seconds":t,"latitude":12,"longitude":77,"uncertainty_m":5} for t in [0,3]]
    result=list(frames(path,'video',meta(track),settings()))
    assert len(result)==2
    assert result[1][1]==2


@pytest.mark.parametrize('box', [[0,0,0,1],[-.1,0,.2,1],[0,0,2,1],[.5,0,.2,1]])
def test_invalid_boxes(box):
    with pytest.raises(ValueError):
        det(bbox=box)

