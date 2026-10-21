"""Create development secrets once without printing them."""
import secrets
from pathlib import Path

path=Path('.env')
if path.exists():
    raise SystemExit('.env already exists; refusing to overwrite it')
text=Path('.env.example').read_text()
for key in ('POSTGRES_PASSWORD','JWT_SECRET','INTERNAL_API_KEY'):
    text=text.replace(key+'=\n',key+'='+secrets.token_hex(32)+'\n')
path.write_text(text)
Path('data/media').mkdir(parents=True,exist_ok=True)
print('Created .env with fresh development secrets. Keep this file private.')

