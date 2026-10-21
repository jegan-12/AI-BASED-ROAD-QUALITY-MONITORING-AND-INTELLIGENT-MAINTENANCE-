from fastapi.testclient import TestClient
from backend.app.config import settings
from inference.service import app


def test_demo_inference_is_labeled_and_authenticated(image_bytes):
    with TestClient(app) as client:
        assert client.post('/predict',headers={'X-API-Key':'wrong'},files={'file':('a.jpg',image_bytes)}).status_code==401
        response=client.post('/predict',headers={'X-API-Key':settings().internal_api_key},files={'file':('a.jpg',image_bytes)})
        assert response.status_code==200,response.text
        data=response.json()
        assert data['synthetic'] is True and data['latency_ms']>=0
        assert len(data['detections'])==1
        card=client.get('/model',headers={'X-API-Key':settings().internal_api_key}).json()
        assert card['metrics'] is None

