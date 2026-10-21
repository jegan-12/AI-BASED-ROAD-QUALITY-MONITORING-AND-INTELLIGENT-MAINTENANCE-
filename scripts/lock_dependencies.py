"""Pin the installed closure of direct project requirements (excludes unrelated audit tooling)."""
from importlib.metadata import distribution
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

requirements=Path('backend/requirements.txt')
roots=[Requirement(line) for line in requirements.read_text().splitlines() if line and not line.startswith(('#','-'))]
visited={}


def visit(req):
    name=canonicalize_name(req.name)
    extras=set(req.extras)
    if name in visited and extras.issubset(visited[name][1]):
        return
    dist=distribution(req.name)
    visited[name]=(dist.version,extras | (visited[name][1] if name in visited else set()))
    for value in dist.requires or []:
        child=Requirement(value)
        if child.marker is None or any(child.marker.evaluate({'extra':extra}) for extra in ['',*extras]):
            visit(child)


for root in roots:
    visit(root)
requirements.write_text('-c constraints.txt\n'+'\n'.join(f'{r.name}'+('['+','.join(sorted(r.extras))+']' if r.extras else '')+'=='+distribution(r.name).version for r in roots)+'\n')
Path('backend/constraints.txt').write_text('# Generated from the validated Python 3.12 environment; direct and transitive pins.\n'+'\n'.join(f'{name}=={version}' for name,(version,_) in sorted(visited.items()))+'\n')
print(f'Locked {len(visited)} project dependencies')

