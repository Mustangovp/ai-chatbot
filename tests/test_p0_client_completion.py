"""Execute the shipped client projection, then accept it through Flask and SQLite."""
import json
import hashlib
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


_PROTECTED_TEMPLATE_BLOCKS = {
    # Core renderer and its sole state authorities.
    'core_runtime': ('class BreathEngine{', 'function truthfulWorkoutRecord('),
    # P0 truth handling in local workout memory.
    'workout_memory': ('function truthfulWorkoutRecord(', 'const T={'),
    # P0 truth handling while reconciling the account workout timeline.
    'workout_history_sync': ('        const serverLog=d.workouts.map', '    if(conversationResponse.ok)'),
    # P0 execution observations and canonical completion payload generation.
    'workout_execution': ('let WO=null,restTimer=null', 'function feedNearBottom()'),
}

_PROTECTED_TEMPLATE_HASHES = {
    'core_runtime': 'd3922dd1f8da465dc9529bd5db8e8ad3ecc8287e64a50df123645756a6ee10c7',
    'workout_memory': '47ad99846b2884f01a0c85b6af57769279424981f6590c288c1f7f4a66a98c26',
    'workout_history_sync': '61d31b1430c619311d11a95dc00018c4a40aefc77e7f42c91b0f3d64c1dc10f4',
    'workout_execution': '16603d10477684313c93355ba1b16d3eb020b2be66007d8a9110a3fbac259d8c',
}


def _protected_template_hashes(template):
    hashes = {}
    for name, (start, end) in _PROTECTED_TEMPLATE_BLOCKS.items():
        begin = template.index(start)
        finish = template.index(end, begin)
        hashes[name] = hashlib.sha256(template[begin:finish].encode()).hexdigest()
    return hashes


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
    after = (ROOT / 'templates/apex.html').read_text(encoding='utf-8')
    assert _protected_template_hashes(after) == _PROTECTED_TEMPLATE_HASHES

    # The presentation may evolve, but the actual Core bootstrap remains fixed.
    assert '<canvas id="core"></canvas>' in after
    assert "core=new LivingCore(document.getElementById('core'));" in after
    assert 'core.setPhysiology(computePhysiology()); core.start();' in after

    core_runtime = after[after.index('class BreathEngine{'):after.index('function truthfulWorkoutRecord(')]
    for marker in (
        'class BreathEngine{',
        'class AttentionEngine{',
        'class AthleteModel{',
        'class PresenceEngine{',
        'class LivingCore{',
        'function computeApexPosition(ph){',
    ):
        assert marker in core_runtime
