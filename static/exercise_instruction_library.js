/* Deterministic instruction records for the workout-technique follow-up flow. */
(function (global) {
  'use strict';

  const records = [
    {
      id: 'goblet_squat',
      aliases: ['goblet squat', 'goblet клек', 'клек с дъмбел пред гърди'],
      prescription_type: 'repetitions',
      bg: {
        starting: ['Дръж един дъмбел вертикално и близо до гърдите.', 'Постави стъпалата приблизително на ширината на раменете.'],
        steps: ['Стегни корема и седни надолу и леко назад.', 'Коленете следват посоката на пръстите, а цялото стъпало остава на пода.', 'Слез само до дълбочина, в която запазваш неутрална стойка, после се изправи.'],
        breathing: 'Вдишай при слизане и издишай, докато се изправяш.',
        cues: ['Дръж дъмбела близо до тялото.', 'Натискай пода с цялото стъпало.'],
        mistakes: ['Коленете падат навътре.', 'Петите се повдигат или гърбът се заобля.'],
        regression: 'Седни леко до стол и се изправи с контрол.',
        safety: 'Спри, ако усещаш остра болка в коляно, тазобедрена става или кръст.'
      },
      en: {
        starting: ['Hold one dumbbell vertically close to your chest.', 'Set your feet about shoulder width apart.'],
        steps: ['Brace your abdomen and sit down and slightly back.', 'Let the knees track with the toes while the whole foot stays grounded.', 'Descend only as far as you can keep a neutral posture, then stand tall.'],
        breathing: 'Inhale on the way down and exhale as you stand.',
        cues: ['Keep the dumbbell close to your body.', 'Press the floor away with your whole foot.'],
        mistakes: ['Letting the knees collapse inward.', 'Lifting the heels or rounding the back.'],
        regression: 'Use a chair touch squat and stand with control.',
        safety: 'Stop for sharp pain in the knee, hip, or low back.'
      }
    },
    {
      id: 'push_up',
      aliases: ['push up', 'push-up', 'pushups', 'лицева опора', 'лицеви опори'],
      prescription_type: 'repetitions',
      bg: {
        starting: ['Постави ръцете малко по-широко от раменете.', 'Направи права линия от глава до пети и стегни седалището и корема.'],
        steps: ['Сгъвай лактите приблизително на 30–45 градуса от торса.', 'Спусни гърдите контролирано към пода.', 'Избутай пода, за да се върнеш в началната позиция.'],
        breathing: 'Вдишай при спускане и издишай при избутване нагоре.',
        cues: ['Дръж врата неутрален.', 'Тялото се движи като една линия.'],
        mistakes: ['Провисване на таза.', 'Лактите се разтварят твърде широко.'],
        regression: 'Изпълни упражнението с ръце върху стабилна висока опора.',
        safety: 'Намали обхвата или спри при остра болка в китка, лакът или рамо.'
      },
      en: {
        starting: ['Place your hands slightly wider than your shoulders.', 'Make one straight line from head to heels and brace your glutes and abdomen.'],
        steps: ['Bend the elbows about 30–45 degrees from your torso.', 'Lower the chest under control.', 'Push the floor away to return to the start.'],
        breathing: 'Inhale as you lower and exhale as you press up.',
        cues: ['Keep your neck neutral.', 'Move your body as one line.'],
        mistakes: ['Letting the hips sag.', 'Flaring the elbows too wide.'],
        regression: 'Perform the movement with hands on a stable elevated surface.',
        safety: 'Reduce range or stop for sharp wrist, elbow, or shoulder pain.'
      }
    },
    {
      id: 'inverted_row_under_table',
      aliases: ['inverted row under table', 'table row', 'inverted row', 'гребане под маса'],
      prescription_type: 'repetitions',
      bg: {
        starting: ['Използвай само здрава, стабилна маса, която не може да се размести или преобърне.', 'Хвани сигурен ръб и направи права линия с тялото.'],
        steps: ['Дръпни гърдите към ръба на масата.', 'Прибери лопатките назад и надолу.', 'Спусни се контролирано до изпънати ръце.'],
        breathing: 'Издишай при дърпане и вдишай при контролирано спускане.',
        cues: ['Дръж таза стегнат.', 'Мисли за лакти към ребрата.'],
        mistakes: ['Отпускане на таза към пода.', 'Дърпане с повдигнати към ушите рамене.'],
        regression: 'Свий коленете и постави стъпалата по-близо до тялото.',
        safety: 'Не изпълнявай под нестабилна, лека или стъклена маса.'
      },
      en: {
        starting: ['Use only a strong, stable table that cannot move or tip.', 'Grip a secure edge and make one straight line with your body.'],
        steps: ['Pull your chest toward the table edge.', 'Draw the shoulder blades back and down.', 'Lower under control to straight arms.'],
        breathing: 'Exhale as you pull and inhale as you lower with control.',
        cues: ['Keep the hips braced.', 'Think elbows toward ribs.'],
        mistakes: ['Letting the hips drop.', 'Pulling with the shoulders shrugged toward the ears.'],
        regression: 'Bend the knees and place the feet closer to your body.',
        safety: 'Never perform this under an unstable, light, or glass table.'
      }
    },
    {
      id: 'dumbbell_romanian_deadlift',
      aliases: ['dumbbell romanian deadlift', 'romanian deadlift', 'dumbbell rdl', 'румънска тяга с дъмбели', 'румънска тяга'],
      prescription_type: 'repetitions',
      bg: {
        starting: ['Дръж по един дъмбел във всяка ръка.', 'Коленете са леко свити, без да клякаш дълбоко.'],
        steps: ['Избутай таза назад и пази гръбнака неутрален.', 'Плъзгай дъмбелите близо до бедрата и пищялите.', 'Спри, когато усетиш разтягане в задната част на бедрата без загуба на стойка.', 'Избутай таза напред, за да се изправиш.'],
        breathing: 'Вдишай при движението надолу и издишай при изправяне.',
        cues: ['Това е сгъване в таза, не дълбок клек.', 'Дръж тежестите близо до тялото.'],
        mistakes: ['Заобляне на кръста.', 'Прекалено сгъване в коленете.'],
        regression: 'Намали тежестта и работи с по-къс обхват пред огледало.',
        safety: 'Спри при остра болка в кръста или задната част на бедрото.'
      },
      en: {
        starting: ['Hold one dumbbell in each hand.', 'Keep the knees softly bent, not deeply squatted.'],
        steps: ['Push the hips back and keep the spine neutral.', 'Keep the dumbbells close to the thighs and shins.', 'Stop when the hamstrings stretch without losing posture.', 'Drive the hips forward to stand.'],
        breathing: 'Inhale on the way down and exhale as you stand.',
        cues: ['This is a hip hinge, not a deep squat.', 'Keep the weights close to your body.'],
        mistakes: ['Rounding the low back.', 'Bending the knees too much.'],
        regression: 'Use lighter dumbbells and a shorter range in front of a mirror.',
        safety: 'Stop for sharp low-back or hamstring pain.'
      }
    },
    {
      id: 'front_plank',
      aliases: ['front plank', 'plank', 'forearm plank', 'преден планк', 'планк'],
      prescription_type: 'duration',
      bg: {
        starting: ['Постави лактите точно под раменете.', 'Направи права линия от глава до пети и стегни корема и седалището.'],
        steps: ['Поддържай тялото неподвижно.', 'Не позволявай на таза да провисва или да се вдига високо.', 'Спри веднага щом стойката се наруши.'],
        breathing: 'Дишай спокойно и равномерно през цялото задържане.',
        cues: ['Натискай пода с предмишниците.', 'Дръж ребрата прибрани.'],
        mistakes: ['Провисване на таза.', 'Задържане на дъха.'],
        regression: 'Изпълни планка с колене на пода.',
        safety: 'Спри при остра болка в рамо или кръст.'
      },
      en: {
        starting: ['Place the elbows directly under the shoulders.', 'Make one straight line from head to heels and brace the abdomen and glutes.'],
        steps: ['Keep the body still.', 'Do not let the hips sag or rise high.', 'Stop as soon as posture breaks.'],
        breathing: 'Breathe calmly and normally throughout the hold.',
        cues: ['Press the floor away through your forearms.', 'Keep the ribs gently down.'],
        mistakes: ['Letting the hips sag.', 'Holding your breath.'],
        regression: 'Perform the plank with knees on the floor.',
        safety: 'Stop for sharp shoulder or low-back pain.'
      }
    }
  ];

  function normalize(value) {
    return String(value || '').toLocaleLowerCase().normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  }

  function find(name) {
    const normalized = normalize(name);
    return records.find((record) => record.aliases.some((alias) => {
      const key = normalize(alias);
      return normalized === key || normalized.startsWith(key + ' ');
    })) || null;
  }

  function prescription(record, exercise, language) {
    const bg = language !== 'en';
    const sets = String(exercise && exercise.sets || (record.id === 'front_plank' ? 2 : 3));
    const supplied = String(exercise && exercise.reps || '');
    const validDuration = /(?:\bsec(?:ond)?s?\b|\bseconds?\b|сек\b|секун)/i.test(supplied);
    const unit = bg ? (record.prescription_type === 'duration' ? 'сек' : 'повт.') : (record.prescription_type === 'duration' ? 'sec' : 'reps');
    const value = record.prescription_type === 'duration' ? (validDuration ? supplied : '20–40') : (supplied || '8–12');
    return `${sets} ${bg ? 'серии' : 'sets'} × ${value} ${unit}`;
  }

  global.ApexExerciseInstructions = Object.freeze({ find, prescription, records: Object.freeze(records) });
})(window);
