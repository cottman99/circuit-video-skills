"""P0.1 attempt lifecycle regressions, including real process interleaving."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_workflow as w


def package():
    return json.loads((ROOT/'examples/resistor-divider/content-package.json').read_text())


def read(path):
    return json.loads(Path(path).read_text())


def stop_process_group(process):
    # The helper creates a dedicated session, so this group contains only its
    # own worker and any encoder descendants. Never leave a hung encoder behind.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return process.communicate(timeout=10)


class AttemptLifecycleTests(unittest.TestCase):
    def successful(self, directory, **kwargs):
        return w.run(package(), directory, width=320, fps=2, **kwargs)

    def assert_terminal(self, result, directory, status):
        self.assertEqual(result['status'], status)
        self.assertEqual(result['schema_version'], 'workflow-attempt-1')
        self.assertEqual(result, read(Path(directory)/'runs'/result['run_id']/'attempt.json'))
        for field in ('run_id', 'run_sequence', 'input_sha256', 'environment_fingerprint',
                      'started_at', 'updated_at', 'finished_at', 'stage', 'error_code', 'new_artifacts'):
            self.assertIn(field, result)
        self.assertIsNotNone(result['finished_at'])
        self.assertEqual(result['review'], {'status': 'NOT_PERFORMED', 'previous_reviews_reused': False})

    def assert_no_current_media(self, result):
        for key in ('preview_path', 'media_sha256', 'scene_path', 'scene_digest'):
            self.assertNotIn(key, result)
        self.assertFalse(result['new_artifacts']['preview'])

    def test_environment_capture_failure_cannot_leave_old_success_latest(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.successful(tmp)
            with patch.object(w, 'environment_fingerprint', side_effect=OSError('injected environment read failure')):
                with self.assertRaisesRegex(OSError, 'environment read failure'):
                    self.successful(tmp)
            result = read(Path(tmp)/'latest.json')
            self.assert_terminal(result, tmp, 'FAILED')
            self.assertEqual(result['stage'], 'capture_environment')
            self.assertEqual(result['environment_fingerprint']['status'], 'PENDING_CAPTURE')
            self.assert_no_current_media(result)
            self.assertEqual(read(Path(tmp)/'latest_success.json'), first)

    def test_running_is_persisted_before_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = w.validate_package
            observed = []
            def inspect(source):
                latest = read(Path(tmp)/'latest.json')
                observed.append(latest)
                self.assertEqual(latest['status'], 'RUNNING')
                self.assertEqual(latest['stage'], 'validate_package')
                self.assertEqual(len(latest['input_sha256']), 64)
                self.assertEqual(len(latest['environment_fingerprint']['sha256']), 64)
                self.assertIsNone(latest['finished_at'])
                self.assertEqual(latest, read(Path(tmp)/'runs'/latest['run_id']/'attempt.json'))
                return original(source)
            with patch.object(w, 'validate_package', side_effect=inspect):
                self.successful(tmp)
            self.assertEqual(len(observed), 1)

    def test_success_then_invalid_is_latest_failed_not_prior_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.successful(tmp)
            invalid = package()
            invalid['caption_refs'].pop()
            with self.assertRaises(ValueError) as raised:
                w.run(invalid, tmp)
            current = read(Path(tmp)/'latest.json')
            self.assert_terminal(current, tmp, 'FAILED')
            self.assertEqual(current, raised.exception.workflow_attempt)
            self.assertEqual(current['error_code'], 'VALIDATION_FAILED')
            self.assert_no_current_media(current)
            self.assertNotEqual(current['run_id'], first['run_id'])
            self.assertNotEqual(current['input_sha256'], first['input_sha256'])
            self.assertEqual(current['previous_success_run_id'], first['run_id'])
            self.assertEqual(read(Path(tmp)/'latest_success.json'), first)

    def test_success_then_unsat_preserves_only_historical_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.successful(tmp)
            source = package()
            source['temporal']['actions'][0]['min_read_seconds'] = 20
            result = w.run(source, tmp)
            self.assert_terminal(result, tmp, 'UNSAT')
            self.assertEqual(result, read(Path(tmp)/'latest.json'))
            self.assertEqual(result['error_code'], 'CONSTRAINT_UNSAT')
            self.assert_no_current_media(result)
            self.assertTrue(result['new_artifacts']['timeline'])
            self.assertEqual(read(Path(tmp)/'latest_success.json'), first)

    def test_success_then_render_exception_is_persisted_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.successful(tmp)
            with patch.object(w.p, 'render', side_effect=RuntimeError('injected renderer failure')):
                with self.assertRaisesRegex(RuntimeError, 'injected renderer failure'):
                    self.successful(tmp)
            result = read(Path(tmp)/'latest.json')
            self.assert_terminal(result, tmp, 'FAILED')
            self.assertEqual(result['stage'], 'render_preview')
            self.assertEqual(result['error_code'], 'RENDER_FAILED')
            self.assertTrue(result['new_artifacts']['frozen_scene'])
            self.assertTrue(result['reused_artifacts']['audio_events'])
            self.assert_no_current_media(result)
            self.assertEqual(read(Path(tmp)/'latest_success.json'), first)

    def test_first_invocation_invalid_json_records_raw_input_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            source = directory/'invalid.json'
            raw = b'{ not JSON }'
            source.write_bytes(raw)
            process = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/run_workflow.py'), str(source),
                                      '--output', str(directory/'out'), '--synthetic-audio-fixture'],
                                     capture_output=True, text=True)
            self.assertEqual(process.returncode, 1)
            result = json.loads(process.stderr)
            self.assert_terminal(result, directory/'out', 'FAILED')
            self.assertEqual(result['input_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['input_encoding'], 'raw_file_bytes')
            self.assertEqual(result['stage'], 'load_input')
            self.assert_no_current_media(result)
            self.assertFalse((directory/'out'/'latest_success.json').exists())

    def test_missing_input_has_explicit_unavailable_hash_not_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                w.run_file(Path(tmp)/'missing.json', Path(tmp)/'out')
            result = read(Path(tmp)/'out'/'latest.json')
            self.assert_terminal(result, Path(tmp)/'out', 'FAILED')
            self.assertIsNone(result['input_sha256'])
            self.assertEqual(result['input_encoding'], 'unreadable_file')

    def blocked_process(self, directory, tag, source=None, diagnostic_bytes=0):
        directory = Path(directory)
        src = directory/(tag+'-input.json')
        src.write_text(json.dumps(source or package()))
        ready, gate = directory/(tag+'-ready'), directory/(tag+'-gate')
        script = '''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import run_workflow as w
original=w.p.render
ready,gate=Path(sys.argv[4]),Path(sys.argv[5])
def delayed(*args,**kwargs):
 ready.write_text('ready')
 while not gate.exists():time.sleep(0.01)
 sys.stderr.write('x'*int(sys.argv[6]))
 sys.stderr.flush()
 return original(*args,**kwargs)
w.p.render=delayed
w.run_file(sys.argv[2],sys.argv[3],width=320,fps=2)
'''
        process = subprocess.Popen([sys.executable, '-B', '-c', script, str(ROOT/'scripts'), str(src),
                                    str(directory/'out'), str(ready), str(gate), str(diagnostic_bytes)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        deadline = time.monotonic()+20
        while not ready.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                self.fail('Blocked child failed: '+stop_process_group(process)[1])
            time.sleep(.02)
        if not ready.exists():
            stop_process_group(process)
            self.fail('Child did not reach render stage')
        return process, gate

    def test_killed_attempt_stays_running_not_false_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.successful(Path(tmp)/'out')
            process, _ = self.blocked_process(tmp, 'interrupted')
            try:
                running = read(Path(tmp)/'out'/'latest.json')
                self.assertEqual(running['status'], 'RUNNING')
                self.assertEqual(running['stage'], 'render_preview')
                self.assertNotEqual(running['run_id'], first['run_id'])
                self.assert_no_current_media(running)
            finally:
                stop_process_group(process)
            self.assertEqual(read(Path(tmp)/'out'/'latest.json'), running)
            self.assertEqual(read(Path(tmp)/'out'/'latest_success.json'), first)

    def test_two_concurrent_successes_keep_newer_start_pointers(self):
        with tempfile.TemporaryDirectory() as tmp:
            older, older_gate = self.blocked_process(tmp, 'older', diagnostic_bytes=600000)
            newer = None
            try:
                older_record = read(Path(tmp)/'out'/'latest.json')
                # Same source/output exercises shared audio locking and distinct
                # per-attempt preview paths, not just the pointer helper in isolation.
                newer, newer_gate = self.blocked_process(tmp, 'newer')
                newer_record = read(Path(tmp)/'out'/'latest.json')
                self.assertGreater(newer_record['run_sequence'], older_record['run_sequence'])
                self.assertNotEqual(newer_record['run_id'], older_record['run_id'])
                newer_gate.write_text('go')
                _, stderr = newer.communicate(timeout=20)
                self.assertEqual(newer.returncode, 0, stderr)
                newest_success = read(Path(tmp)/'out'/'latest_success.json')
                self.assertEqual(newest_success['run_id'], newer_record['run_id'])
                older_gate.write_text('go')
                # Drain output while checking pointers. Merely polling a child
                # with PIPE stderr can deadlock when diagnostics fill that pipe.
                # communicate also bounds the wait if the child truly hangs.
                with ThreadPoolExecutor(max_workers=1) as readers:
                    completed = readers.submit(older.communicate, timeout=20)
                    while not completed.done():
                        latest = read(Path(tmp)/'out'/'latest.json')
                        success = read(Path(tmp)/'out'/'latest_success.json')
                        self.assertEqual(latest['run_id'], newer_record['run_id'])
                        self.assertEqual(success['run_id'], newer_record['run_id'])
                        time.sleep(.01)
                    _, stderr = completed.result()
                self.assertEqual(older.returncode, 0, stderr)
                records = [read(p) for p in (Path(tmp)/'out'/'runs').glob('*/attempt.json')]
                self.assertEqual(len(records), 2)
                self.assertTrue(all(r['status'] == 'SUCCESS' for r in records))
                self.assertEqual(len({r['preview_path'] for r in records}), 2)
                self.assertEqual(read(Path(tmp)/'out'/'latest.json')['run_id'], newer_record['run_id'])
                self.assertEqual(read(Path(tmp)/'out'/'latest_success.json')['run_id'], newer_record['run_id'])
            finally:
                for process in (older, newer):
                    if process is not None:
                        stop_process_group(process)

    def test_newer_failure_remains_latest_when_older_success_finishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            older, gate = self.blocked_process(tmp, 'older-success')
            try:
                older_id = read(Path(tmp)/'out'/'latest.json')['run_id']
                invalid = package()
                invalid['caption_refs'].pop()
                with self.assertRaises(ValueError):
                    w.run(invalid, Path(tmp)/'out')
                failed = read(Path(tmp)/'out'/'latest.json')
                self.assertEqual(failed['status'], 'FAILED')
                gate.write_text('go')
                _, stderr = older.communicate(timeout=20)
                self.assertEqual(older.returncode, 0, stderr)
                self.assertEqual(read(Path(tmp)/'out'/'latest.json'), failed)
                success = read(Path(tmp)/'out'/'latest_success.json')
                self.assertEqual(success['run_id'], older_id)
                self.assertEqual(success['status'], 'SUCCESS')
            finally:
                stop_process_group(older)

    def test_cleanup_terminates_pipe_holding_descendant_after_leader_exit(self):
        # A completed leader can leave descendants holding inherited PIPE fds.
        # Cleanup must own and stop the group, not depend on leader.poll().
        script = ("import subprocess,sys; "
                  "subprocess.Popen([sys.executable, '-c', "
                  "'import time; time.sleep(60)']); print('spawned', flush=True)")
        process = subprocess.Popen([sys.executable, '-B', '-c', script],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            self.assertEqual(process.wait(timeout=10), 0)
            started = time.monotonic()
            stdout, stderr = stop_process_group(process)
            self.assertIn('spawned', stdout)
            self.assertEqual(stderr, '')
            self.assertLess(time.monotonic() - started, 10)
        finally:
            stop_process_group(process)

    def test_same_environment_repeat_binds_profile_and_actual_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.successful(tmp, video=True)
            second = self.successful(tmp, video=True)
            self.assert_terminal(first, tmp, 'SUCCESS')
            self.assert_terminal(second, tmp, 'SUCCESS')
            self.assertNotEqual(first['run_id'], second['run_id'])
            self.assertNotEqual(first['preview_path'], second['preview_path'])
            self.assertEqual(first['scene_digest'], second['scene_digest'])
            self.assertEqual(first['render_environment_fingerprint'], second['render_environment_fingerprint'])
            self.assertEqual(first['media_sha256'], second['media_sha256'])
            a, b = [read(Path(run['preview_path'])/'manifest.json') for run in (first, second)]
            self.assertEqual(a['decoded_frame_count'], b['decoded_frame_count'])
            self.assertEqual(a['fps'], b['fps'])
            self.assertEqual((Path(first['preview_path'])/'receipts.jsonl').read_bytes(),
                             (Path(second['preview_path'])/'receipts.jsonl').read_bytes())
            details = b['render_environment_fingerprint']['details']
            self.assertIn('requirements-tested.txt', details['dependency_spec_sha256'])
            self.assertTrue(details['encoder']['available'])
            self.assertIn('fonts', details['renderer_runtime'])
            self.assertEqual(details['output_profile']['width'], 320)


if __name__ == '__main__':
    unittest.main()
