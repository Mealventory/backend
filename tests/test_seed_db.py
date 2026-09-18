import pytest
from app.scripts.seed_db import validate_target
from app.db.fixtures.demo import USERS, fixture_id


@pytest.mark.parametrize('url', [None, 'postgresql://user:pw@prod.example/db_test',
    'postgresql://user:pw@localhost/postgres', 'sqlite://',
    'postgresql://user:pw@localhost/app_test?host=remote',
    'postgresql://user:pw@127.0.0.1/app_demo?service=production'])
def test_unsafe_targets_rejected(url):
    with pytest.raises(ValueError):
        validate_target(url)


def test_local_target_and_stable_identities(monkeypatch):
    for key in ('PGHOST', 'PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE'):
        monkeypatch.delenv(key, raising=False)
    assert validate_target('postgresql://user:pw@127.0.0.1/app_demo').database == 'app_demo'
    assert len({u.id for u in USERS}) == 4
    assert fixture_id('home:0') == fixture_id('home:0')
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    with pytest.raises(ValueError):
        validate_target('postgresql://user:pw@localhost/app_test')
