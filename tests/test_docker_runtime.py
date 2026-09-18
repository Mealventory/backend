"""Opt-in smoke test of the built image against disposable PostgreSQL only."""
import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
import pytest

pytestmark = pytest.mark.skipif(os.getenv('RUN_DOCKER_TESTS') != '1', reason='Requires built Docker image and Docker daemon')


def test_nonroot_container_health_and_database_outage():
    docker = shutil.which('docker')
    assert docker, 'docker must be on PATH'
    image = os.getenv('BACKEND_TEST_IMAGE', 'mealventory-backend:issue48')
    suffix = uuid.uuid4().hex[:10]
    network, database, backend = [f'mealventory-test-{part}-{suffix}' for part in ('net', 'db', 'api')]
    password = secrets.token_hex(24)

    def run(*args, check=True):
        result = subprocess.run([docker, *args], capture_output=True, text=True, timeout=60)
        if check:
            assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def wait_health(expected):
        for _ in range(45):
            state = json.loads(run('inspect', backend))[0]['State']
            if state.get('Health', {}).get('Status') == expected:
                return
            assert state['Running'], run('logs', backend)
            time.sleep(1)
        pytest.fail(f'Container did not become {expected}')

    try:
        run('network', 'create', network)
        run('run', '-d', '--name', database, '--network', network,
            '-e', 'POSTGRES_PASSWORD=' + password, 'postgres:16')
        for _ in range(30):
            if 'accepting connections' in run('exec', database, 'pg_isready', '-U', 'postgres', check=False):
                break
            time.sleep(1)
        else:
            pytest.fail('Disposable database failed to start')
        run('run', '-d', '--name', backend, '--network', network,
            '--health-interval=2s', '--health-start-period=2s', '--health-retries=2',
            '-e', f'DATABASE_URL=postgresql://postgres:{password}@{database}:5432/postgres?connect_timeout=2',
            '-e', 'AI_SERVICE_URL=http://unused-ai:8001', image)
        wait_health('healthy')
        assert run('exec', backend, 'id', '-u') == '10001'
        assert run('exec', backend, 'id', '-un') == 'appuser'
        assert run('exec', backend, 'python', '-c',
                   "from pathlib import Path; print(Path('/app/.env').exists() or Path('/app/credentials').exists())") == 'False'
        run('stop', database)
        wait_health('unhealthy')
        # The process stays alive while readiness is unavailable.
        assert json.loads(run('inspect', backend))[0]['State']['Running']
    finally:
        run('rm', '-f', backend, check=False)
        run('rm', '-f', database, check=False)
        run('network', 'rm', network, check=False)
