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
    },
    'bodyweight.squat': {
      bg: 'Клек със собствено тегло с контролирана позиция на коленете',
      en: 'Bodyweight squat with controlled knee alignment'
    },
    'bodyweight.wall_push_up': {
      bg: 'Лицева опора към стабилна стена с тяло в права линия',
      en: 'Wall push-up against a stable wall with the body held in a straight line'
    },
    'bodyweight.table_row': {
      bg: 'Гребане под стабилна маса с подравнено тяло',
      en: 'Table row beneath a stable load-bearing table with the body aligned'
    },
    'bodyweight.glute_bridge': {
      bg: 'Глутеус мост с повдигнат таз и стабилен торс',
      en: 'Glute bridge with the hips elevated and torso controlled'
    },
    'bodyweight.plank': {
      bg: 'Преден планк на лакти с тяло в права линия',
      en: 'Forearm front plank with the body held in a straight line'
    },
    'bodyweight.incline_push_up': {
      bg: 'Лицева опора с длани на стабилна повдигната пейка',
      en: 'Incline push-up with hands on a stable elevated bench'
    },
    'dumbbell.goblet_squat': {
      bg: 'Гоблет клек с един вертикален дъмбел пред гърдите',
      en: 'Goblet squat with one vertical dumbbell held at the chest'
    },
    'bodyweight.reverse_lunge': {
      bg: 'Обратен напад със собствено тегло и стъпка назад',
      en: 'Bodyweight reverse lunge with a backward step'
    },
    'bodyweight.hip_hinge': {
      bg: 'Хиндж със собствено тегло, изнесен назад таз и неутрален гръб',
      en: 'Bodyweight hip hinge with hips back and a neutral spine'
    },
    'dumbbell.row': {
      bg: 'Гребане с един дъмбел и опора с другата ръка на пейка',
      en: 'Single-arm dumbbell row with the other hand supported on a bench'
    },
    'band.row': {
      bg: 'Гребане от стоеж с ластик, закрепен пред тялото',
      en: 'Standing band row with a secure anchor in front of the body'
    },
    'dumbbell.overhead_press': {
      bg: 'Стриктна преса от стоеж с два дъмбела над глава',
      en: 'Strict standing overhead press with two dumbbells'
    },
    'dumbbell.seated_press': {
      bg: 'Преса с два дъмбела от седеж с опора за гърба',
      en: 'Seated two-dumbbell press with a supported backrest'
    },
    'bodyweight.pull_up': {
      bg: 'Контролирано набиране с надхват на стабилен лост',
      en: 'Controlled overhand pull-up on a secure bar'
    },
    'barbell.back_squat': {
      bg: 'Клек с щанга върху горната част на гърба в стойка с предпазители',
      en: 'Barbell back squat inside a rack with safety supports'
    },
    'dumbbell.floor_press': {
      bg: 'Преса с два дъмбела от лег на пода със свити колене',
      en: 'Two-dumbbell floor press with knees bent and feet planted'
    },
    'band.chest_press': {
      bg: 'Избутване пред гърдите с ластик, закрепен зад тялото',
      en: 'Standing band chest press with a secure anchor behind the body'
    },
    'cable.chest_press': {
      bg: 'Избутване пред гърдите с две кабелни ръкохватки от стоеж',
      en: 'Standing chest press with two cable handles'
    },
    'dumbbell.chest_supported_row': {
      bg: 'Гребане с два дъмбела с гърди върху наклонена пейка',
      en: 'Two-dumbbell row with the chest supported on an inclined bench'
    },
    'cable.seated_row': {
      bg: 'Гребане от седеж на долен скрипец с опора за стъпалата',
      en: 'Seated low-cable row with feet on fixed supports'
    },
    'band.lat_pulldown': {
      bg: 'Вертикално дърпане от колене с ластик, закрепен над глава',
      en: 'Kneeling band lat pulldown from a secure overhead anchor'
    },
    'cable.lat_pulldown': {
      bg: 'Дърпане на горен скрипец към горната част на гърдите',
      en: 'Seated cable lat pulldown toward the upper chest'
    },
    'dumbbell.split_squat': {
      bg: 'Сплит клек с два дъмбела и задно стъпало на пода',
      en: 'Static split squat with two dumbbells and the rear foot on the floor'
    },
    'dumbbell.step_up': {
      bg: 'Качване на стабилна платформа с два дъмбела',
      en: 'Controlled step-up onto a stable platform with two dumbbells'
    },
    'cable.pull_through': {
      bg: 'Хиндж с въже между краката от долен скрипец зад тялото',
      en: 'Cable pull-through with a rope between the legs from a low rear pulley'
    },
    'barbell.romanian_deadlift': {
      bg: 'Румънска тяга с щанга близо до краката и над пода',
      en: 'Barbell Romanian deadlift with the bar close to the legs and above the floor'
    },
    'bodyweight.dead_bug': {
      bg: 'Дед бъг по гръб с изпънати противоположни ръка и крак',
      en: 'Supine dead bug with the opposite arm and leg extended'
    },
    'band.pallof_press': {
      bg: 'Палоф преса с ластик отстрани и стабилен торс без ротация',
      en: 'Pallof press with a lateral band anchor and a controlled non-rotating torso'
    },
    'bodyweight.march_in_place': {
      bg: 'Маршируване на място с повдигнато коляно и противоположна ръка',
      en: 'Upright march in place with a lifted knee and opposite arm'
    },
    'dumbbell.bench_press': {
      bg: 'Преса с два дъмбела от лег на хоризонтална пейка',
      en: 'Two-dumbbell press lying on a flat bench with feet planted'
    },
    'barbell.bench_press': {
      bg: 'Преса с щанга от лег на хоризонтална пейка с предпазители',
      en: 'Barbell flat bench press inside a rack with safety supports'
    },
    'bodyweight.negative_pull_up': {
      bg: 'Междинна позиция при негативно набиране със стъпало за връщане под лоста',
      en: 'Partially lowered negative pull-up position with a reset step beneath the bar'
    },
    'dumbbell.reverse_lunge': {
      bg: 'Обратен напад с два дъмбела, държани отстрани',
      en: 'Reverse lunge with two dumbbells held at the sides'
    },
    'barbell.deadlift': {
      bg: 'Начална позиция за тяга с щанга и дискове върху пода',
      en: 'Conventional barbell deadlift floor-start position with grounded plates'
    },
    'dumbbell.push_press': {
      bg: 'Начална позиция за пуш преса с два дъмбела и плитко сгъване в коленете',
      en: 'Two-dumbbell push press setup with a shallow knee dip before leg drive'
    }
  };
  // Inherit the app shell's shared revision instead of maintaining a second token.
  const script = global.document && global.document.currentScript;
  const revision = script ? new URL(script.src).searchParams.get('v') : null;
  const suffix = revision ? '?v=' + encodeURIComponent(revision) : '';
  const entries = Object.create(null);
  Object.keys(descriptions).forEach(function (exerciseId) {
    const base = '/static/exercise/visuals/v1/' + exerciseId;
    entries[exerciseId] = Object.freeze({
      exercise_id: exerciseId,
      thumb: base + '--thumb.webp' + suffix,
      protocol: base + '--protocol.webp' + suffix,
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
