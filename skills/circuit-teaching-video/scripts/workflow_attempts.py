"""Durable local attempt records, ordered pointers and explicit render fingerprints.

POSIX advisory locks coordinate cooperating invocations using one output directory.
A killed process can leave RUNNING, but cannot make an old success the latest attempt.
No network calls, review approval or publication behavior is implemented here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path, value):
    """Replace a complete JSON document, never expose a partially written one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n').encode()
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def file_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def read_optional(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else None


def tool_fingerprint(name):
    executable = shutil.which(name)
    if executable is None:
        return {'available': False, 'reason': 'not_on_PATH'}
    try:
        result = subprocess.run([executable, '-version'], capture_output=True, text=True,
                                timeout=10, check=True)
        return {'available': True,
                'executable_sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
                'version_output': result.stdout.strip()}
    except (OSError, subprocess.SubprocessError) as exc:
        return {'available': False, 'reason': type(exc).__name__}


def environment_fingerprint(profile, runtime):
    """Actual tool/font/code identities; no cross-environment byte equality claim."""
    packages = {}
    for name in ('Pillow', 'numpy', 'scipy', 'matplotlib', 'fonttools', 'sympy', 'jsonschema'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    repository = Path(__file__).resolve().parents[3]
    dependency_specs = {name: hashlib.sha256((repository/name).read_bytes()).hexdigest()
                        for name in ('requirements.txt', 'requirements-tested.txt', 'requirements-optional.txt', 'requirements-p1.txt')
                        if (repository/name).is_file()}
    value = {'schema_version': 'render-environment-1', 'python': sys.version,
             'platform': platform.platform(), 'machine': platform.machine(), 'cpu_count': os.cpu_count(),
             'dependency_spec_sha256': dependency_specs,
             'packages': packages, 'renderer_runtime': runtime,
             'encoder': tool_fingerprint('ffmpeg'), 'probe': tool_fingerprint('ffprobe'),
             'output_profile': profile}
    return {'sha256': digest(value), 'details': value}


ARTIFACT_NAMES = ('formal_export', 'formal_captions', 'phonetic_voice', 'audio_events', 'timeline',
                  'frozen_scene', 'preview')


class Attempt:
    """One invocation. Sequence is start order, never completion order.

    latest.json is the newest-started attempt, even when older attempts finish
    later. latest_success.json is the newest-started successful attempt. A failed
    run may name a previous successful run ID, but never copies its media fields.
    """
    def __init__(self, output, input_sha256, input_encoding, environment):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.run_id = uuid.uuid4().hex
        self.path = self.output/'runs'/self.run_id/'attempt.json'
        self.lock = self.output/'.attempt-pointers.lock'
        with file_lock(self.lock):
            counter = read_optional(self.output/'attempt-sequence.json') or {'last_sequence': 0}
            sequence = counter['last_sequence']+1
            self.previous_success = read_optional(self.output/'latest_success.json') or {}
            now = timestamp()
            self.record = {'schema_version': 'workflow-attempt-1', 'run_id': self.run_id,
                           'run_sequence': sequence, 'status': 'RUNNING', 'stage': 'load_input',
                           'error_code': None, 'error': None, 'input_sha256': input_sha256,
                           'input_encoding': input_encoding, 'environment_fingerprint': environment,
                           'started_at': now, 'updated_at': now, 'finished_at': None,
                           'new_artifacts': {name: False for name in ARTIFACT_NAMES},
                           'reused_artifacts': {name: False for name in ARTIFACT_NAMES},
                           'previous_success_run_id': self.previous_success.get('run_id'),
                           'review': {'status': 'NOT_PERFORMED', 'previous_reviews_reused': False}}
            atomic_write(self.output/'attempt-sequence.json', {'last_sequence': sequence})
            self._persist_locked()

    def _persist_locked(self):
        # Every pointer target exists first. Files are replaced atomically under
        # the same writer lock; readers can inspect run_id to compare snapshots.
        atomic_write(self.path, self.record)
        latest = read_optional(self.output/'latest.json')
        if not latest or latest.get('run_sequence', -1) <= self.record['run_sequence']:
            atomic_write(self.output/'latest.json', self.record)
        if self.record['status'] == 'SUCCESS':
            success = read_optional(self.output/'latest_success.json')
            if not success or success.get('run_sequence', -1) <= self.record['run_sequence']:
                atomic_write(self.output/'latest_success.json', self.record)

    def stage(self, name):
        self.record.update(stage=name, updated_at=timestamp())
        with file_lock(self.lock):
            self._persist_locked()

    def environment(self, fingerprint):
        self.record['environment_fingerprint'] = fingerprint
        self.record['updated_at'] = timestamp()
        with file_lock(self.lock):
            self._persist_locked()

    def artifact(self, name, *, created=True):
        self.record['new_artifacts'][name] = created
        self.record['reused_artifacts'][name] = not created
        self.record['updated_at'] = timestamp()
        with file_lock(self.lock):
            self._persist_locked()

    def finish(self, status, result=None, error=None):
        if status not in ('SUCCESS', 'UNSAT', 'FAILED'):
            raise ValueError('Unsupported terminal attempt status')
        # Only this invocation's completed result may introduce artifact paths.
        # Failures never inherit old media, scene hashes or review records.
        if result is not None:
            self.record.update({key: value for key, value in result.items() if key != 'schema_version'})
        stage = self.record['stage']
        code = None
        if status == 'UNSAT':
            stage, code = 'solve_timeline', 'CONSTRAINT_UNSAT'
        elif status == 'SUCCESS':
            stage = 'complete'
        else:
            code = ('INTERRUPTED' if isinstance(error, (KeyboardInterrupt, SystemExit)) else
                    'INPUT_ERROR' if stage == 'load_input' else
                    'PREFREEZE_GATE_FAILED' if stage == 'pre_freeze_gate' else
                    'VALIDATION_FAILED' if stage == 'validate_package' else
                    'RENDER_FAILED' if stage == 'render_preview' else 'STAGE_FAILED')
        now = timestamp()
        self.record.update(status=status, stage=stage, error_code=code,
                           error=None if error is None else {'type': type(error).__name__, 'message': str(error)},
                           updated_at=now, finished_at=now,
                           review={'status': 'NOT_PERFORMED', 'previous_reviews_reused': False})
        if status == 'FAILED' and stage == 'pre_freeze_gate':
            self.record['source_model_gate'] = {'status': 'BLOCKED', 'scientific_approval': False,
                                                'audiovisual_approval': False, 'publication_allowed': False}
            if callable(getattr(error, 'record', None)):
                self.record['error']['detail'] = error.record()
        if status == 'FAILED':
            for key in ('preview_path', 'media_sha256', 'scene_path', 'scene_digest'):
                self.record.pop(key, None)
        with file_lock(self.lock):
            self._persist_locked()
        return self.record
