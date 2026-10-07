"""All registry identities must resolve without translated-name inference."""
import json
from pathlib import Path
import shutil
import subprocess

from canonical_workout_fixture import canonical_fixtures
from training_engine import load_exercise_library
from training_engine.renderer import _BULGARIAN_EXERCISE_NAMES


def test_all_registry_ids_have_complete_exact_instructions_and_bg_names():
    library = load_exercise_library()
    assert len(library.exercises) == 40
    assert set(_BULGARIAN_EXERCISE_NAMES) == {item.exercise_id for item in library.exercises}
    fixtures = canonical_fixtures()
    node = shutil.which("node")
    assert node
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = { window: {} };
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
const api = context.window.ApexExerciseInstructions;
for (const fixture of JSON.parse(fs.readFileSync(0, 'utf8'))) {
  const record = api.findByExerciseId(fixture.id);
  assert.ok(record, fixture.id);
  for (const language of ['bg', 'en']) {
    assert.ok(api.display(record, language));
    if (language === 'bg') assert.match(api.display(record, language), /[\u0400-\u04ff]/);
    assert.ok(record['muscle_group_' + language]);
    for (const field of ['overview', 'starting', 'execution', 'breathing', 'cues', 'mistakes', 'regression', 'safety']) {
      const value = record[language][field];
      assert.ok(Array.isArray(value) ? value.length && value.every(x => x.trim()) : value && value.trim(), fixture.id + ':' + field);
    }
  }
}
for (const id of ['unknown.plank', 'bodyweight.row', 'dumbbell.pull_up', 'plank', 'Bodyweight.plank']) assert.equal(api.findByExerciseId(id), null, id);
assert.equal(api.findByExerciseId('dumbbell.row'), api.find('Dumbbell Row'));
assert.equal(api.findByExerciseId('band.row'), api.find('Band Row'));
assert.notEqual(api.findByExerciseId('barbell.romanian_deadlift'), api.findByExerciseId('dumbbell.romanian_deadlift'));
"""
    root = Path(__file__).parents[1]
    for fixture in fixtures:
        assert fixture["languages"]["bg"]["metadata"]["sessions"][0]["exercises"][0]["display_name"] != fixture["languages"]["en"]["metadata"]["sessions"][0]["exercises"][0]["display_name"]
    subprocess.run([node, "-e", script, str(root / "static/exercise_instruction_library.js")], input=json.dumps(fixtures), text=True, check=True)
