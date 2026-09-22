"""Exercise failure/recovery transitions without requiring production or Docker."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('auto_deploy', Path(__file__).parents[1] / 'auto_deploy.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
OLD, NEW = 'a' * 40, 'b' * 40


def config():
    return {'services': {
        'db': {'image': 'postgres:17-alpine'},
        'api': {'build': {'context': '/release/backend'}},
        'worker': {'build': {'context': '/release/backend'}},
        'web': {'build': {'context': '/release/frontend'}},
        'proxy': {'image': 'caddy:2.9-alpine'},
    }, 'volumes': {'postgres_data': {'name': 'nuvemiq_postgres_data'}}}


class FakeDeployer(deploy.Deployer):
    def __init__(self, root):
        super().__init__({'repo': str(root), 'state_dir': str(root / 'state')})
        self.actions = []
        self.build_failure = False
        self.activation_failure = set()
        self.dirty = False
        self.fetch_failure = False
        self.interrupt = False
        self.target = NEW
        self.candidate = config()
        self.release(OLD).mkdir(parents=True)
        deploy.save_json(self.release(OLD) / 'source.json', config())
        deploy.save_json(self.release(OLD) / 'images.json', {name: f'old-{name}' for name in deploy.SERVICES})
        self.state = dict(current=OLD, previous=None, pending=None, failed=[])
        self.save()

    def clean(self):
        if self.dirty:
            raise RuntimeError('Dirty checkout')

    def git(self, *args):
        if args[0] == 'fetch' and self.fetch_failure:
            raise RuntimeError('Network failed')
        return self.target

    def healthy(self, expected=None):
        pass

    def prepare(self, revision, source):
        self.release(revision).mkdir(parents=True, exist_ok=True)
        return self.candidate

    def compose(self, path, *args, **kwargs):
        self.actions.append(('build', path.parent.name))
        if self.build_failure:
            raise RuntimeError('Build failed')
        return ''

    def pin(self, revision, configuration, images):
        self.actions.append(('pin', revision))

    def activate(self, revision):
        self.actions.append(('activate', revision))
        # The transaction must already be recoverable from disk.
        assert deploy.read_json(self.journal)['pending'] is not None
        if self.interrupt:
            raise KeyboardInterrupt()
        if revision in self.activation_failure:
            raise RuntimeError('Not healthy')


class Transactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.d = FakeDeployer(Path(self.temp.name))
        mock = patch.object(deploy, 'run', return_value='sha256:new-image\n')
        mock.start()
        self.addCleanup(mock.stop)

    def test_success_promotes_only_after_health(self):
        self.d.check()
        self.assertEqual(self.d.state['current'], NEW)
        self.assertEqual(self.d.state['previous'], OLD)
        self.assertIsNone(self.d.state['pending'])
        self.assertEqual(self.d.actions[-1], ('activate', NEW))

    def test_no_change_and_blocked_commit_do_nothing(self):
        self.d.target = OLD
        self.d.check()
        self.d.target = NEW
        self.d.state['failed'] = [NEW]
        self.d.check()
        self.assertEqual(self.d.actions, [])

    def test_build_failure_preserves_running_containers_and_blocks_retry(self):
        self.d.build_failure = True
        with self.assertRaises(RuntimeError):
            self.d.check()
        self.assertEqual(self.d.state['current'], OLD)
        self.assertIn(NEW, self.d.state['failed'])
        self.assertNotIn(('activate', OLD), self.d.actions)
        self.assertNotIn(('activate', NEW), self.d.actions)
        self.d.build_failure = False
        self.d.check()
        self.assertNotIn(('activate', NEW), self.d.actions)

    def test_unhealthy_release_restores_previous(self):
        self.d.activation_failure = {NEW}
        with self.assertRaises(RuntimeError):
            self.d.check()
        self.assertEqual(self.d.actions[-2:], [('activate', NEW), ('activate', OLD)])
        self.assertEqual(self.d.state['current'], OLD)
        self.assertIsNone(self.d.state['pending'])
        self.assertIn(NEW, self.d.state['failed'])

    def test_rollback_failure_remains_pending_then_recovers(self):
        self.d.activation_failure = {OLD, NEW}
        with self.assertRaises(RuntimeError):
            self.d.check()
        self.assertEqual(deploy.read_json(self.d.journal)['pending'], NEW)
        self.d.activation_failure.clear()
        self.d.fetch_failure = True
        self.d.check()  # Recovery must not depend on GitHub/network access.
        self.assertIsNone(self.d.state['pending'])
        self.assertEqual(self.d.state['current'], OLD)

    def test_interrupted_activation_recovers_from_journal(self):
        self.d.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            self.d.check()
        self.d.state = deploy.read_json(self.d.journal)
        self.assertEqual(self.d.state['pending'], NEW)
        self.d.interrupt = False
        self.d.check()
        self.assertEqual(self.d.actions[-1], ('activate', OLD))
        self.assertIn(NEW, self.d.state['failed'])

    def test_dirty_checkout_and_network_error_do_not_activate(self):
        self.d.dirty = True
        with self.assertRaises(RuntimeError):
            self.d.check()
        self.d.dirty = False
        self.d.fetch_failure = True
        with self.assertRaises(RuntimeError):
            self.d.check()
        self.assertEqual(self.d.actions, [])
        self.assertEqual(self.d.state['failed'], [])

    def test_database_upgrade_refused_before_build(self):
        self.d.candidate['services']['db']['image'] = 'postgres:18-alpine'
        with self.assertRaises(RuntimeError):
            self.d.check()
        self.assertEqual(self.d.actions, [])
        self.assertEqual(self.d.state['current'], OLD)

    def test_manual_rollback_blocks_removed_commit(self):
        self.d.state.update(current=NEW, previous=OLD)
        self.d.rollback()
        self.assertEqual(self.d.state['current'], OLD)
        self.assertIn(NEW, self.d.state['failed'])
        self.d.check()
        self.assertEqual(self.d.actions, [('activate', OLD)])


class Boundaries(unittest.TestCase):
    def test_releases_archive_exact_commit_and_preserve_working_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / 'repo'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(repo), *args]).decode().strip()
            git('init', '-q')
            git('config', 'user.email', 'test@example.test')
            git('config', 'user.name', 'Test')
            (repo / 'version').write_text('one')
            git('add', 'version')
            git('commit', '-qm', 'one')
            old = git('rev-parse', 'HEAD')
            (repo / 'version').write_text('two')
            git('commit', '-am', 'two', '-q')
            head = git('rev-parse', 'HEAD')
            (repo / '.env').write_text('SECRET=keep$literal\n')
            d = deploy.Deployer({'repo': str(repo), 'state_dir': str(root / 'state')})
            with patch.object(d, 'config_for', return_value=config()):
                d.prepare(old, old)
            self.assertEqual((d.release(old) / 'version').read_text(), 'one')
            self.assertEqual((repo / 'version').read_text(), 'two')
            self.assertEqual(git('rev-parse', 'HEAD'), head)
            self.assertEqual((d.release(old) / '.env').read_text(), 'SECRET=keep$literal\n')
            self.assertEqual((d.release(old) / '.env').stat().st_mode & 0o777, 0o600)

    def test_dollar_values_preserved_for_compose_interpolation(self):
        original = {'services': {'api': {'environment': {'PASSWORD': 'foo${BAR}$baz'}}}}
        escaped = deploy.literal_compose(original)
        self.assertEqual(escaped['services']['api']['environment']['PASSWORD'], 'foo$${BAR}$$baz')
        self.assertEqual(original['services']['api']['environment']['PASSWORD'], 'foo${BAR}$baz')

    def test_health_rejects_crash_loop_and_wrong_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            d = deploy.Deployer({'repo': temporary, 'state_dir': temporary})
            items = {name: {'Id': name, 'Image': 'good', 'State': {'Running': True},
                            'RestartCount': 0} for name in deploy.SERVICES}
            with patch.object(d, 'container', side_effect=lambda name: items[name]):
                items['worker']['State']['Restarting'] = True
                with self.assertRaisesRegex(RuntimeError, 'worker'):
                    d.health_once()
                items['worker']['State']['Restarting'] = False
                with self.assertRaisesRegex(RuntimeError, 'imagem'):
                    d.health_once({name: 'wrong' for name in deploy.SERVICES})

    def test_runtime_pins_actual_images_and_removes_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            d = deploy.Deployer({'repo': temporary, 'state_dir': temporary})
            d.release(OLD).mkdir(parents=True)
            with patch.object(deploy, 'run') as runner:
                d.pin(OLD, config(), {name: f'sha256:{name}' for name in deploy.SERVICES})
            runtime = deploy.read_json(d.runtime(OLD))
            for name, service in runtime['services'].items():
                self.assertNotIn('build', service)
                self.assertEqual(service['pull_policy'], 'never')
                self.assertEqual(service['image'], f'deepops-local/{name}:{OLD}')
            self.assertEqual(runner.call_count, 5)
            self.assertEqual(d.runtime(OLD).stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
