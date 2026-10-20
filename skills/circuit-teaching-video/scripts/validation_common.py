"""Shared bounded local-file helpers. No external requests or installation."""
from pathlib import Path

def referenced_file(base, value, boundary, errors, label):
    """Resolve contract-relative references inside an explicit overall project boundary."""
    if not isinstance(value,str) or not value.strip():
        errors.append(f'{label}: local path required');return None
    rel=Path(value)
    if rel.is_absolute() or '\\' in value:
        errors.append(f'{label}: absolute/nonportable path forbidden');return None
    base=Path(base);boundary=Path(boundary).resolve();unresolved=base/rel
    # Check the lexical chain before resolving, so a symlink cannot disappear from the check.
    if unresolved.is_symlink() or any(x.is_symlink() for x in unresolved.parents):
        errors.append(f'{label}: symlinks are not accepted');return None
    target=unresolved.resolve()
    if target!=boundary and boundary not in target.parents:
        errors.append(f'{label}: path must stay within project');return None
    if not target.is_file() or target.stat().st_size==0:
        errors.append(f'{label}: missing or empty file {value}');return None
    return target

def local_file(root, value, errors, label):
    if isinstance(value,str) and '..' in Path(value).parts:
        errors.append(f'{label}: top-level path must stay within project');return None
    return referenced_file(root,value,root,errors,label)

def items(contract,key,errors):
    value=contract.get(key,[])
    if not isinstance(value,list) or not all(isinstance(x,dict) for x in value):
        errors.append(f'{key}: expected list of objects');return []
    return value

def nonempty(value): return isinstance(value,str) and bool(value.strip())
