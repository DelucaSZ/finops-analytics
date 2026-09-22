#!/usr/bin/env python3
"""Single-host Compose deployment with immutable images and a durable rollback journal."""
import argparse
import copy
import fcntl
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time

SERVICES = ('db', 'api', 'worker', 'web', 'proxy')
APP_SERVICES = SERVICES[1:]


def log(message):
    print(time.strftime('%Y-%m-%dT%H:%M:%S%z'), message, flush=True)


def run(args, *, cwd=None, timeout=120, capture=True):
    # Never print command arguments: rendered Compose and env may contain secrets.
    result = subprocess.run(args, cwd=cwd, timeout=timeout, check=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    return result.stdout.decode() if capture else ''


def read_json(path):
    return json.loads(path.read_text())


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def literal_compose(value):
    # Compose interpolates even JSON; preserve literal dollars in passwords/config.
    if isinstance(value, str):
        return value.replace('$', '$$')
    if isinstance(value, list):
        return [literal_compose(item) for item in value]
    if isinstance(value, dict):
        return {key: literal_compose(item) for key, item in value.items()}
    return value


class Deployer:
    def __init__(self, config):
        self.repo = Path(config['repo']).resolve()
        self.root = Path(config.get('state_dir', '/var/lib/deepops-deploy')).resolve()
        self.project = config.get('project', 'nuvemiq')
        self.branch = config.get('branch', 'main')
        self.health_timeout = int(config.get('health_timeout', 180))
        self.stabilize = int(config.get('stabilize_seconds', 30))
        self.build_timeout = int(config.get('build_timeout', 1800))
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.journal = self.root / 'state.json'
        self.state = read_json(self.journal) if self.journal.exists() else {}

    def save(self):
        save_json(self.journal, self.state)

    def git(self, *args):
        return run(['git', '-C', str(self.repo), *args]).strip()

    def clean(self):
        if self.git('status', '--porcelain', '--untracked-files=no'):
            raise RuntimeError('Alterações locais rastreadas: resolva-as sem descartar correções antes de continuar.')
        if not (self.repo / '.env').is_file():
            raise RuntimeError('Arquivo .env ausente no repositório.')
        if self.git('ls-files', '.env'):
            raise RuntimeError('.env não pode estar versionado no Git.')

    def compose(self, path, *args, timeout=120, capture=True):
        return run(['docker', 'compose', '--project-name', self.project,
                    '--project-directory', str(path.parent), '--env-file', '/dev/null',
                    '-f', str(path), *args], cwd=path.parent, timeout=timeout, capture=capture)

    def config_for(self, directory):
        return json.loads(run(['docker', 'compose', '--project-name', self.project,
                              '--project-directory', str(directory), '--env-file', str(directory / '.env'),
                              '-f', str(directory / 'compose.yaml'), 'config', '--format', 'json'],
                             cwd=directory))

    def release(self, revision):
        return self.root / 'releases' / revision

    def runtime(self, revision):
        return self.release(revision) / 'runtime.json'

    def prepare(self, revision, source):
        directory = self.release(revision)
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True, mode=0o700)
        archive = subprocess.check_output(['git', '-C', str(self.repo), 'archive', source], timeout=120)
        with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
            bundle.extractall(directory, filter='data')
        shutil.copyfile(self.repo / '.env', directory / '.env')
        os.chmod(directory / '.env', 0o600)
        config = self.config_for(directory)
        if set(config['services']) != set(SERVICES):
            raise RuntimeError('Mudança na lista de serviços exige deploy manual.')
        save_json(directory / 'source.json', config)
        return config

    def container(self, service):
        ids = run(['docker', 'ps', '-aq', '--filter', f'label=com.docker.compose.project={self.project}',
                   '--filter', f'label=com.docker.compose.service={service}',
                   '--filter', 'label=com.docker.compose.oneoff=False']).split()
        if len(ids) != 1:
            raise RuntimeError(f'{service}: esperado exatamente um container; encontrados {len(ids)}.')
        return json.loads(run(['docker', 'inspect', ids[0]]))[0]

    def health_once(self, expected=None):
        containers = {name: self.container(name) for name in SERVICES}
        for name, container in containers.items():
            state = container['State']
            if not state['Running'] or state.get('Paused') or state.get('Restarting'):
                raise RuntimeError(f'{name} não está em execução normal.')
            if 'Health' in state and state['Health']['Status'] != 'healthy':
                raise RuntimeError(f'{name} não está saudável.')
            if expected and container['Image'] != expected[name]:
                raise RuntimeError(f'{name}: imagem diferente da versão esperada.')
        probe = '''import json, urllib.request
from sqlalchemy import text
from app.db.session import engine
with engine.connect() as connection:
    connection.execute(text('SELECT 1'))
for url in ('http://127.0.0.1:8000/health', 'http://web:3000/', 'http://proxy/health', 'http://proxy/'):
    with urllib.request.urlopen(url, timeout=8) as response:
        assert response.status == 200
        if url.endswith('/health'):
            assert json.load(response)['status'] == 'ok'
'''
        run(['docker', 'exec', containers['api']['Id'], 'python', '-c', probe], timeout=45)
        return {name: (item['Id'], item['RestartCount']) for name, item in containers.items()}

    def healthy(self, expected=None):
        deadline = time.monotonic() + self.health_timeout
        stable_since, last = None, None
        while time.monotonic() < deadline:
            try:
                sample = self.health_once(expected)
                if sample != last:
                    stable_since = time.monotonic()
                last = sample
                if time.monotonic() - stable_since >= self.stabilize:
                    return
            except (RuntimeError, subprocess.SubprocessError):
                stable_since, last = None, None
            time.sleep(3)
        raise RuntimeError('Prazo de saúde/estabilização excedido.')

    def pin(self, revision, config, images):
        config = copy.deepcopy(config)
        for name, service in config['services'].items():
            tag = f'deepops-local/{name}:{revision}'
            run(['docker', 'image', 'tag', images[name], tag])
            service['image'] = tag
            service.pop('build', None)
            service['pull_policy'] = 'never'
        save_json(self.runtime(revision), literal_compose(config))
        save_json(self.release(revision) / 'images.json', images)

    def bootstrap(self):
        if self.state:
            raise RuntimeError('Já inicializado; use status/check. O baseline existente foi preservado.')
        self.clean()
        self.healthy()
        source = self.git('rev-parse', 'HEAD')
        revision = f'baseline-{int(time.time())}'
        config = self.prepare(revision, source)
        # Adopt actual running images; the checkout SHA alone cannot identify existing images.
        images = {name: self.container(name)['Image'] for name in SERVICES}
        self.pin(revision, config, images)
        self.state = dict(current=revision, previous=None, pending=None, failed=[],
                          baseline_checkout=source)
        self.save()
        log(f'Baseline saudável preservado: {revision}; nenhuma recriação realizada.')

    def activate(self, revision):
        self.compose(self.runtime(revision), 'up', '-d', '--no-build', '--pull', 'never',
                     '--no-deps', '--force-recreate', '--wait', '--wait-timeout', str(self.health_timeout),
                     *APP_SERVICES, timeout=self.health_timeout + 120, capture=False)
        self.healthy(read_json(self.release(revision) / 'images.json'))

    def recover(self):
        target = self.state['pending']
        current = self.state['current']
        log(f'Restaurando imagens preservadas de {current}.')
        # Persist failure BEFORE recovery; interrupted/failed rollback remains pending.
        if target not in self.state['failed']:
            self.state['failed'].append(target)
        self.save()
        self.activate(current)
        self.state['pending'] = None
        self.save()
        log(f'Rollback validado: {current}. Commit {target} bloqueado.')

    def check(self):
        if not self.state:
            raise RuntimeError('Execute bootstrap antes de habilitar o timer.')
        if self.state.get('pending'):
            self.recover()
            return
        self.clean()
        # Fetch into remote-tracking ref only; never reset or merge the user's checkout.
        self.git('fetch', '--no-tags', 'origin',
                 f'refs/heads/{self.branch}:refs/remotes/origin/{self.branch}')
        target = self.git('rev-parse', f'refs/remotes/origin/{self.branch}')
        if not re.fullmatch('[0-9a-f]{40}', target):
            raise RuntimeError('Referência Git inválida.')
        if target == self.state['current'] or target in self.state['failed']:
            return
        current = self.state['current']
        self.healthy(read_json(self.release(current) / 'images.json'))
        log(f'Preparando commit {target}. Versão atual continua atendendo.')
        try:
            candidate = self.prepare(target, target)
            previous = read_json(self.release(current) / 'source.json')
            # Database upgrades and topology changes cannot safely auto-rollback.
            for key in ('volumes', 'networks', 'configs', 'secrets'):
                if candidate.get(key) != previous.get(key):
                    raise RuntimeError(f'Mudança em {key} exige deploy manual.')
            if candidate['services']['db'] != previous['services']['db']:
                raise RuntimeError('Mudança no banco exige deploy manual.')
            build = copy.deepcopy(candidate)
            for name in ('api', 'worker', 'web'):
                if 'build' not in build['services'][name]:
                    raise RuntimeError(f'{name}: build ausente.')
                build['services'][name]['image'] = f'deepops-build/{name}:{target}'
            build_path = self.release(target) / 'build.json'
            save_json(build_path, literal_compose(build))
            self.compose(build_path, 'build', 'api', 'worker', 'web',
                         timeout=self.build_timeout, capture=False)
            images = {}
            for name in SERVICES:
                if 'build' in build['services'][name]:
                    images[name] = run(['docker', 'image', 'inspect', '--format', '{{.Id}}',
                                        build['services'][name]['image']]).strip()
                elif candidate['services'][name]['image'] == previous['services'][name]['image']:
                    images[name] = read_json(self.release(current) / 'images.json')[name]
                else:
                    image = candidate['services'][name]['image']
                    run(['docker', 'pull', image], timeout=600, capture=False)
                    images[name] = run(['docker', 'image', 'inspect', '--format', '{{.Id}}', image]).strip()
            self.pin(target, candidate, images)
        except Exception:
            self.state['failed'].append(target)
            self.save()
            log(f'Preparação falhou: {target} bloqueado; containers atuais preservados.')
            raise
        self.state['pending'] = target
        self.save()
        try:
            self.activate(target)
        except Exception:
            log('Nova versão falhou. Iniciando rollback automático.')
            self.recover()
            raise
        self.state.update(current=target, previous=current, pending=None)
        self.save()
        log(f'Deploy saudável confirmado: {target}.')

    def rollback(self):
        if self.state.get('pending'):
            self.recover()
            return
        previous = self.state.get('previous')
        if not previous:
            raise RuntimeError('Não há versão anterior registrada.')
        current = self.state['current']
        # Journal the manual rollback as a normal activation, preserving crash recovery.
        self.state['pending'] = previous
        self.save()
        try:
            self.activate(previous)
        except Exception:
            self.recover()
            raise
        self.state.update(current=previous, previous=current, pending=None)
        if current not in self.state['failed']:
            self.state['failed'].append(current)
        self.save()
        log(f'Rollback manual validado: {previous}; {current} bloqueado.')


def main():
    os.umask(0o077)
    os.environ['GIT_TERMINAL_PROMPT'] = '0'
    os.environ.setdefault('GIT_SSH_COMMAND', 'ssh -oBatchMode=yes -oConnectTimeout=15')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('bootstrap', 'check', 'status', 'rollback', 'retry'))
    parser.add_argument('--config', default='/etc/deepops-deploy.json')
    args = parser.parse_args()
    deployer = Deployer(read_json(Path(args.config)))
    with (deployer.root / 'deploy.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log('Outro deploy já está em andamento.')
            return
        # Reload only after taking the lock.
        deployer.state = read_json(deployer.journal) if deployer.journal.exists() else {}
        if args.action == 'status':
            print(json.dumps(deployer.state, indent=2))
        elif args.action == 'retry':
            if not deployer.state:
                raise RuntimeError('Execute bootstrap primeiro.')
            deployer.state['failed'] = []
            deployer.save()
            log('Bloqueios removidos; próxima verificação tentará novamente.')
        else:
            getattr(deployer, args.action)()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Subprocess exception repr can leak inline environment/config; keep errors generic.
        log(str(exc) if isinstance(exc, RuntimeError) else f'Falha: {type(exc).__name__}; consulte o journal.')
        sys.exit(1)
