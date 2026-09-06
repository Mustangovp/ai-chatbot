"""Execute the shipped client projection, then accept it through Flask and SQLite."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest
import app as appmod
import db
from training_engine import build_training_plan, load_exercise_library
from training_engine.completion import completion_projection
from training_engine.followups import serialize_conversation_plan
from training_engine.lineage import delivered_plan_lineage

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('state', ['completed', 'partial', 'skipped', 'abandoned', 'unknown', 'empty_abandoned', 'mixed_unknown', 'each_missing'])
def test_template_evidence_survives_server_and_db(state):
    case = state
    state = {'empty_abandoned': 'abandoned', 'mixed_unknown': 'partial', 'each_missing': 'partial'}.get(case, state)
    plan = build_training_plan(recommendation_blueprint_id='client-truth', facts={
        'goal': 'strength', 'level': 'intermediate', 'equipment': 'gym', 'recoveryFeel': 'fresh'})
    projection = completion_projection(plan, load_exercise_library())
    session = projection['sessions'][0]
    exercises = []
    for index, item in enumerate(session['exercises']):
        values = [item['rep_min']] * item['prescribed_sets']
        if state == 'unknown':
            values = [None] * item['prescribed_sets']
        elif state == 'skipped':
            values = []
        elif state in ('partial', 'abandoned'):
            values = [item['rep_min']] if index == 0 else []
        if case == 'empty_abandoned':
            values = []
        elif case in ('mixed_unknown', 'each_missing'):
            values = [item['rep_min']] * item['prescribed_sets']
            if index == 0 or case == 'each_missing':
                values[0] = None
        exercises.append({'name': item['display_name'], 'sets': item['prescribed_sets'],
                          'reps': str(item['rep_min']), 'completion': item,
                          'observedReps': values, 'skipped': state == 'skipped' or (case == 'partial' and index > 0)})
    workout = {'ex': exercises, 'contract': {'plan_id': plan.plan_id, 'plan_version': plan.version,
                                            'session_id': session['session_id']}}
    template = (ROOT / 'templates/apex.html').read_text(encoding='utf-8')
    js = template[template.index('function workoutExecutionEvidence('):template.index('function workoutEffortOptions(')]
    script = 'const WO=' + json.dumps(workout) + ';function inferMuscle(){return {m:"training"};}\n' + js
    script += '\nprocess.stdout.write(JSON.stringify(workoutExecutionEvidence(' + json.dumps('abandoned' if state == 'abandoned' else None) + ')));'
    node = shutil.which('node')
    assert node, 'Node is required for the client/server execution contract test'
    result = json.loads(subprocess.check_output([node, '-e', script], text=True, encoding='utf-8'))
    assert result['session']['execution_state'] == state
    uid = db.get_or_create_user('client-truth@example.com')
    db.persist_delivered_training_plan(uid, delivered_plan_lineage(plan))
    db.update_conversation_runtime_state(f'account:{uid}', 'client-truth', workout_blueprint=serialize_conversation_plan(plan))
    client = appmod.app.test_client()
    client.set_cookie(appmod.SESSION_COOKIE, db.create_session(uid))
    response = client.post('/api/workout', json={'session': result['session'], 'workout_completion': result['completion']})
    assert response.status_code == 200, response.get_json()
    row = next(row for row in client.get('/api/history').get_json()['workouts'] if row['id'] == response.get_json()['id'])
    assert row['execution_state'] == state
    assert row['completion'] == result['session']['completion']
    if result['completion'] is not None:
        assert row['completion_evidence']['exercises'] == result['completion']['exercises']
    else:
        assert row['completion_evidence'] is None
    if state == 'unknown':
        assert all(item['actual_repetitions'] is None for item in row['exercises'])


def test_template_changes_are_confined_to_execution_and_workout_memory():
    # SHA-256 values computed from the current-main presentation around the
    # explicitly authorized workout-memory and execution ranges.
    import hashlib
    after = (ROOT / 'templates/apex.html').read_text(encoding='utf-8')
    def frozen_sections(text):
        # Explicitly authorized execution and local workout-memory ranges only.
        begin = text.index('function truthfulWorkoutRecord(') if 'function truthfulWorkoutRecord(' in text else text.index('function memLoad(')
        end = text.index('const T={', begin)
        text = text[:begin] + '[WORKOUT MEMORY]' + text[end:]
        begin = text.index('        const serverLog=d.workouts.map')
        end = text.index("        ownedStorageSet('apexWorkoutLog'", begin)
        text = text[:begin] + '[WORKOUT HISTORY SYNC]' + text[end:]
        begin = text.index('let WO=null,restTimer=null')
        end = text.index('function feedNearBottom()', begin)
        return text[:begin] + '[WORKOUT EXECUTION]' + text[end:]
    assert hashlib.sha256(frozen_sections(after).encode()).hexdigest() == '30df4319d5a8af98c61608f836109b797171625dc84667b3712c9867f212dbea'
    # Markup and style declarations remain byte-identical, including Core and mobile Consult.
    assert hashlib.sha256(after[:after.index('<script>')].encode()).hexdigest() == '676fd7cc5ac4a460725cf835ec2c481b0d9983dec4a6230d24c303c4fdcec538'
    import re
    assert hashlib.sha256(json.dumps(re.findall(r'style="[^"]*"', after), ensure_ascii=False).encode()).hexdigest() == '9729a5c7dbc0e529aaf044e90fbae3116178c40c58ec15800172a667395ff4e5'
