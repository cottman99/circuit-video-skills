#!/usr/bin/env python3
"""Bounded public-source audit. Never claim this detects every possible secret."""
from pathlib import Path
import argparse,ast,hashlib,json,re,sys
ROOT=Path(__file__).resolve().parents[1]
BANNED_EXT={'.pdf','.mp4','.wav','.mp3','.mov','.zip','.ttf','.otf','.ttc','.pyc','.pyo'}
PATTERNS={
 'private_conversation_id':r'(?:Sentinel|libfile)_[A-Za-z0-9]{12,}',
 'private_workspace_path':r'/(?:workspace|mnt/data|home/agent)(?:/|\b)',
 'private_session_narrative':r'用户实际反馈|本次用户主动|经本次\s*A/B|本次.*用户.*比较',
 'private_drive_url':r'https?://drive\.google\.com/',
 'github_token':r'\bgh[pousr]_[A-Za-z0-9]{20,}',
 'service_key':r'\bsk-[A-Za-z0-9-]{20,}',
 'private_key':r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',
 'credential_assignment':r'''(?i)(?:access_token|client_secret|api_key)\s*[:=]\s*["'][A-Za-z0-9_\-]{10,}''',
}
def audit(root):
 root=Path(root).resolve();findings=[];files={};links=0
 for p in sorted(root.rglob('*')):
  if '.git' in p.relative_to(root).parts:continue
  if p.is_symlink():findings.append({'file':p.relative_to(root).as_posix(),'issue':'symlink'});continue
  if not p.is_file():continue
  rel=p.relative_to(root).as_posix()
  if p.suffix.lower() in BANNED_EXT or '__pycache__' in p.parts:findings.append({'file':rel,'issue':'excluded_media_font_or_runtime_file'})
  if p.stat().st_size>2_000_000:findings.append({'file':rel,'issue':'unexpected_large_file'})
  if rel not in ['RELEASE_AUDIT.json','artifact_manifest.json']:files[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
  try:text=p.read_text()
  except UnicodeError:continue
  # This scanner contains literal detector patterns, not secrets.
  if p.resolve()!=Path(__file__).resolve():
   for name,pattern in PATTERNS.items():
    if re.search(pattern,text):findings.append({'file':rel,'issue':name})
  if p.suffix=='.py':
   try:ast.parse(text)
   except SyntaxError:findings.append({'file':rel,'issue':'python_syntax'})
  if p.suffix=='.md':
   for target in re.findall(r'\]\(([^)]+)\)',text):
    if target.startswith(('http:','https:','#')):continue
    links+=1
    if not (p.parent/target.split('#')[0]).exists():findings.append({'file':rel,'issue':'broken_local_link','target':target})
 return {'status':'PASS' if not findings else 'FAIL','file_count':len(files),'bytes':sum((root/p).stat().st_size for p in files),'local_links_checked':links,'findings':findings,'scope':'Static common-secret/private-path/media exclusion, local links and Python syntax; not exhaustive security or copyright certification','files':files}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=ROOT);ap.add_argument('--write',action='store_true');a=ap.parse_args();r=audit(a.root)
 if a.write:
  files=r.pop('files');(a.root/'artifact_manifest.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n');(a.root/'RELEASE_AUDIT.json').write_text(json.dumps(r,indent=2)+'\n')
 else:r.pop('files')
 print(json.dumps(r,indent=2));sys.exit(r['status']!='PASS')
