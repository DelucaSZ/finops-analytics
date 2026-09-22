#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ ${EUID} -ne 0 ]]; then
  echo 'Execute com sudo bash scripts/install-auto-deploy.sh.' >&2
  exit 1
fi
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
for command in docker git python3 systemctl; do
  command -v "$command" >/dev/null || { echo "Comando ausente: $command" >&2; exit 1; }
done
python3 -c 'import tarfile; assert hasattr(tarfile, "data_filter"), "Python precisa suportar tarfile.data_filter"'
docker compose version
[[ -f "$repo/.env" ]] || { echo "Falta $repo/.env" >&2; exit 1; }
[[ -z $(git -C "$repo" status --porcelain --untracked-files=no) ]] || {
  echo 'Há alterações locais rastreadas. Preserve/resolva as alterações antes de instalar.' >&2
  exit 1
}
# Verify Git authentication with the same root account used by systemd.
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND='ssh -oBatchMode=yes -oConnectTimeout=15'
timeout 60 git -C "$repo" ls-remote --exit-code origin refs/heads/main >/dev/null
install -m 0755 "$repo/scripts/auto_deploy.py" /usr/local/sbin/deepops-deploy
if [[ ! -f /etc/deepops-deploy.json ]]; then
  python3 - "$repo" <<'PY'
import json, os, sys
with open('/etc/deepops-deploy.json', 'x') as stream:
    os.chmod(stream.name, 0o600)
    json.dump(dict(repo=sys.argv[1], branch='main', project='nuvemiq',
                   state_dir='/var/lib/deepops-deploy', health_timeout=180,
                   stabilize_seconds=30, build_timeout=1800), stream, indent=2)
PY
fi
if [[ ! -f /var/lib/deepops-deploy/state.json ]]; then
  /usr/local/sbin/deepops-deploy bootstrap
fi
cat > /etc/systemd/system/deepops-deploy.service <<'UNIT'
[Unit]
Description=DeepOps - deploy de commits com rollback
Wants=network-online.target
After=network-online.target docker.service
Requires=docker.service

[Service]
Type=oneshot
User=root
UMask=0077
Environment=GIT_TERMINAL_PROMPT=0
ExecStart=/usr/local/sbin/deepops-deploy check
TimeoutStartSec=45min
UNIT
cat > /etc/systemd/system/deepops-deploy.timer <<'UNIT'
[Unit]
Description=Verificar novos commits do DeepOps a cada minuto

[Timer]
OnBootSec=90s
OnUnitInactiveSec=60s
AccuracySec=5s
Unit=deepops-deploy.service

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now deepops-deploy.timer
echo 'Auto deploy instalado. Primeira consulta em até 90 segundos.'
echo 'Logs: journalctl -u deepops-deploy.service -f'
echo 'Estado: sudo deepops-deploy status'
