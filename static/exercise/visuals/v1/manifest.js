(function (global) {
  'use strict';

  const descriptions = {
    'dumbbell.front_squat': {
      bg: 'Преден клек с два дъмбела, поддържани на височината на раменете',
      en: 'Dumbbell front squat with two dumbbells supported at shoulder height'
    },
    'bodyweight.push_up': {
      bg: 'Лицева опора с тяло в права линия',
      en: 'Push-up with the body held in a straight line'
    },
    'dumbbell.bent_over_row': {
      bg: 'Гребане с два дъмбела от наклонен стоеж',
      en: 'Bent-over row with two dumbbells'
    },
    'dumbbell.romanian_deadlift': {
      bg: 'Румънска тяга с два дъмбела и изнесен назад таз',
      en: 'Romanian deadlift with two dumbbells and hips hinged back'
    },
    'bodyweight.hollow_hold': {
      bg: 'Задържане по гръб с повдигнати рамене и крака',
      en: 'Hollow body hold with shoulders and legs lifted'
    }
  };
  const entries = Object.create(null);
  Object.keys(descriptions).forEach(function (exerciseId) {
    const base = '/static/exercise/visuals/v1/' + exerciseId;
    entries[exerciseId] = Object.freeze({
      exercise_id: exerciseId,
      thumb: base + '--thumb.webp',
      protocol: base + '--protocol.webp',
      alt: Object.freeze(descriptions[exerciseId])
    });
  });
  Object.freeze(entries);

  global.ApexExerciseVisuals = Object.freeze({
    version: '1',
    resolve: function (exerciseId) {
      // Display names and instruction IDs are deliberately not visual authority.
      return typeof exerciseId === 'string' && Object.hasOwn(entries, exerciseId)
        ? entries[exerciseId] : null;
    }
  });
})(window);
