import json
from pathlib import Path
from backend.app.main import app

Path('docs/openapi.json').write_text(json.dumps(app.openapi(),indent=2))
print('Wrote docs/openapi.json')

