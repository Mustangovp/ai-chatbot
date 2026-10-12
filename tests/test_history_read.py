"""History reads persisted observed execution, without manufacturing completion."""
import pytest

import app as appmod
import db as store
from test_my_training import _client, _complete, _persist, _user


def test_history_requires_account_and_is_private_uncached_read():
    assert appmod.app.test_client().get('/api/history').status_code == 401
    response = _client(_user()).get('/api/history')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'private, no-store'
    assert response.json == {'workouts': [], 'nutrition': [], 'timeline': []}


def test_history_returns_observed_typed_completion_without_prescription_substitution():
    owner = _user()
    plan, _ = _persist(owner)
    payload = _complete(owner, plan, load=None)
    row = _client(owner).get('/api/history').json['workouts'][0]
    assert row['execution_state'] == 'completed'
    assert sum(item['completed_sets'] for item in row['exercises']) == sum(
        item['completed_sets'] for item in payload['exercises'])
    assert {item.get('prescription_type', 'repetitions') for item in row['exercises']} == {'repetitions', 'duration'}
    for item in row['exercises']:
        assert 'sets' not in item and 'reps' not in item
        assert item['completed_load'] is None
        if item.get('prescription_type') == 'duration':
            assert item['actual_duration_seconds'] > 0
            assert item['actual_repetitions'] is None
        else:
            assert item['actual_repetitions'] > 0


@pytest.mark.parametrize('state', ['partial', 'abandoned', 'skipped', 'unknown'])
def test_history_keeps_non_completed_execution_state_and_does_not_create_progress(state):
    owner = _user()
    skipped = state == 'skipped'
    response = _client(owner).post('/api/workout', json={'session': {
        'execution_schema': 'workout-execution-v1', 'execution_state': state,
        'type': 'Original session', 'exercises': [{
            'name': 'Original movement', 'execution_state': state,
            'completed_sets': 0 if skipped else 1, 'actual_repetitions': 0 if skipped else 8,
            'completed_rpe': 7, 'completed_rir': 2, 'completed_effort': 'productive',
        }],
    }})
    assert response.status_code == 200
    history = _client(owner).get('/api/history').json['workouts']
    assert len(history) == 1 and history[0]['execution_state'] == state
    assert history[0]['exercises'][0]['actual_repetitions'] == (0 if skipped else 8)
    assert history[0]['exercises'][0]['completed_rpe'] == 7
    assert store.get_training_progress(owner)['record']['completed_sessions'] == 0


def test_legacy_prescription_is_not_observed_work_and_other_account_is_not_read():
    owner, other = _user(), _user('other-history@example.com')
    store.log_workout(owner, {'type': 'Legacy session', 'completion': 100,
        'exercises': [{'name': 'Legacy movement', 'sets': 12, 'reps': '20-30', 'completed_repetitions': 30}]})
    store.log_workout(other, {'type': 'Foreign session', 'exercises': []})
    rows = _client(owner).get('/api/history').json['workouts']
    assert len(rows) == 1 and rows[0]['type'] == 'Legacy session'
    assert rows[0]['execution_state'] == 'unknown'
    assert rows[0]['exercises'][0]['completed_sets'] is None
    assert rows[0]['exercises'][0]['actual_repetitions'] is None
