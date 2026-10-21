import hashlib
import json
import pytest
from PIL import Image
from ml.metrics import match_counts, summarize
from ml.pipeline import audit_manifest
from ml.calibrate import calibrate


def test_operating_metrics_one_to_one_and_absent_classes():
    predictions=[{'class':'pothole','confidence':c,'bbox':[.1,.1,.3,.3]} for c in [.9,.8,.1]]
    truths=[{'class':'pothole','bbox':[.1,.1,.3,.3]},{'class':'rutting','bbox':[.5,.5,.7,.7]}]
    counts=match_counts(predictions,truths,['pothole','rutting','other'])
    assert counts['pothole']=={'tp':1,'fp':1,'fn':0}
    assert counts['rutting']['fn']==1
    report={r['class']:r for r in summarize(counts)}
    assert report['pothole']['precision']==.5
    assert report['other']['recall'] is None


def manifest(tmp_path):
    data={'name':'synthetic unit-test images','provenance':'Generated color patches, not real roads',
          'license':'CC0 synthetic fixture','classes':['pothole'],'samples':[]}
    for i,split in enumerate(['train','val','test']):
        image=tmp_path/f'{i}.png';label=tmp_path/f'{i}.txt'
        Image.new('RGB',(64,48),(i*50,0,0)).save(image)
        label.write_text('0 0.5 0.5 0.2 0.2\n')
        data['samples'].append({'image':image.name,'label':label.name,'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
          'label_sha256':hashlib.sha256(label.read_bytes()).hexdigest(),'route_group':f'route-{i}','split':split})
    path=tmp_path/'manifest.json';path.write_text(json.dumps(data))
    return path,data


def test_dataset_audit_and_route_leakage(tmp_path):
    path,data=manifest(tmp_path)
    assert len(audit_manifest(path)['samples'])==3
    data['samples'][1]['route_group']='route-0'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='leakage'):
        audit_manifest(path)


def test_dataset_hash_tampering(tmp_path):
    path,data=manifest(tmp_path)
    (tmp_path/'0.txt').write_text('0 0.1 0.1 0.9 0.9')
    with pytest.raises(ValueError,match='hash'):
        audit_manifest(path)


def test_calibration_heldout_and_leakage(tmp_path):
    path=tmp_path/'ratings.csv'
    rows=['raw_score,expert_score,route_group,split']
    rows += [f'{i*4},{min(100,i*4+5)},train-route,train' for i in range(20)]
    rows += [f'{i*8},{min(100,i*8+5)},test-route,test' for i in range(10)]
    path.write_text('\n'.join(rows))
    result=calibrate(path,'test-v1','Synthetic fixture for calibration software tests','a'*64)
    assert result['heldout_mae']==pytest.approx(0)
    path.write_text(path.read_text().replace('test-route','train-route'))
    with pytest.raises(ValueError,match='leakage'):
        calibrate(path,'v1','Synthetic test','a'*64)

