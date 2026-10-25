/* Deterministic evidence presentation; no model HTML or independent chart data. */
(function () {
  'use strict';
  const VERSION = 'training-progress-chat-v1';
  const statuses = ['comparable', 'insufficient', 'empty', 'unavailable', 'auth_required'];
  const keys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).sort().join('|') === expected.slice().sort().join('|');
  const instant = value => Date.parse(value.slice(0, 19) + 'Z') +
    Number('0.' + (value.match(/\.(\d+)\+/) || ['', '0'])[1]) * 1000;
  function validate(data) {
    if (!keys(data, ['version', 'language', 'status', 'summary', 'evidence', 'limitations', 'next_step', 'series']) ||
        data.version !== VERSION || !['bg', 'en'].includes(data.language) || !statuses.includes(data.status)) return null;
    if (['summary', 'evidence', 'limitations', 'next_step'].some(key =>
      typeof data[key] !== 'string' || data[key].length > 1000) || !data.summary) return null;
    const series = data.series;
    if (series === null) return ['comparable', 'insufficient'].includes(data.status) ? null : data;
    if (!['comparable', 'insufficient'].includes(data.status) ||
        !keys(series, ['exercise_id', 'exercise_version', 'display_name', 'unit', 'completed_sets', 'load_kg', 'points']) ||
        !/^[a-z_]+\.[a-z_]+$/.test(series.exercise_id) || !/^\d+\.\d+\.\d+$/.test(series.exercise_version) ||
        typeof series.display_name !== 'string' || !series.display_name || series.display_name.length > 160 ||
        !['reps', 'seconds'].includes(series.unit) || !Number.isInteger(series.completed_sets) ||
        series.completed_sets < 1 || series.completed_sets > 100 ||
        (series.load_kg !== null && (typeof series.load_kg !== 'number' || !Number.isFinite(series.load_kg) ||
          series.load_kg < 0 || series.load_kg > 1000)) ||
        !Array.isArray(series.points) || series.points.length < 1 || series.points.length > 5) return null;
    if ((data.status === 'comparable') !== (series.points.length >= 2)) return null;
    let previous = -Infinity;
    for (const point of series.points) {
      if (!keys(point, ['recorded_at', 'value']) || typeof point.recorded_at !== 'string' ||
          !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?\+00:00$/.test(point.recorded_at) ||
          !Number.isInteger(point.value) || point.value < 1 || point.value > 100000) return null;
      const timestamp = instant(point.recorded_at);
      if (!Number.isFinite(timestamp) || timestamp <= previous) return null;
      previous = timestamp;
    }
    return data;
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function svgElement(tag, attributes, text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  let sequence = 0;
  function render(candidate) {
    const data = validate(candidate);
    if (!data) return null;
    const en = data.language === 'en', root = element('section', undefined, 'chat-progress-analysis');
    root.lang = data.language;
    const heading = element('h3', en ? 'Your training evidence' : 'Твоите тренировъчни записи');
    heading.id = 'chat-progress-title-' + (++sequence);
    root.setAttribute('aria-labelledby', heading.id);
    root.append(heading, element('p', data.summary, 'chat-progress-summary'));
    const series = data.series;
    if (series) {
      const label = series.unit === 'reps' ? (en ? 'Recorded repetitions' : 'Записани повторения') :
        (en ? 'Recorded duration' : 'Записана продължителност');
      const unit = series.unit === 'reps' ? (en ? 'reps' : 'повт.') : (en ? 'sec' : 'сек');
      root.append(element('h4', series.display_name));
      if (data.status === 'comparable') {
        const figure = element('figure'), caption = element('figcaption', label + ' (' + unit + ')');
        const svg = svgElement('svg', {viewBox: '0 0 560 210', role: 'img', 'aria-label':
          (en ? 'Recorded values over time; exact values follow in the table.' :
            'Записани стойности във времето; точните стойности са в таблицата.')});
        const points = series.points, start = instant(points[0].recorded_at);
        const span = instant(points[points.length - 1].recorded_at) - start;
        const maximum = Math.max(...points.map(point => point.value));
        const position = point => [48 + 488 * (instant(point.recorded_at) - start) / span,
          164 - 136 * point.value / maximum];
        svg.append(svgElement('path', {d: 'M48 24V164H536', class: 'chat-progress-axis'}));
        svg.append(svgElement('text', {x: 38, y: 168, 'text-anchor': 'end'}, '0'));
        svg.append(svgElement('text', {x: 38, y: 32, 'text-anchor': 'end'}, String(maximum)));
        svg.append(svgElement('polyline', {points: points.map(point => position(point).join(',')).join(' '),
          class: 'chat-progress-line'}));
        for (const point of points) {
          const [cx, cy] = position(point), dot = svgElement('circle', {cx, cy, r: 4, class: 'chat-progress-point'});
          dot.append(svgElement('title', {}, point.recorded_at + ': ' + point.value + ' ' + unit));
          svg.append(dot);
        }
        [points[0], points[points.length - 1]].forEach((point, index) => svg.append(svgElement('text', {
          x: index ? 536 : 48, y: 192, 'text-anchor': index ? 'end' : 'start'
        }, point.recorded_at.slice(0, 10))));
        figure.append(caption, svg);
        root.append(figure);
      }
      const wrapper = element('div', undefined, 'chat-progress-table');
      wrapper.tabIndex = 0;
      wrapper.setAttribute('role', 'region');
      wrapper.setAttribute('aria-label', en ? 'Chronological training records; scroll horizontally' :
        'Хронологични тренировъчни записи; хоризонтално превъртане');
      const table = element('table'), caption = element('caption', en ? 'Recorded execution, not prescribed targets' :
        'Записано изпълнение, не предписани цели');
      const head = element('thead'), row = element('tr');
      [en ? 'Recorded at (UTC)' : 'Записано на (UTC)', label + ' (' + unit + ')',
        en ? 'Completed sets' : 'Завършени серии', en ? 'Recorded load (kg)' : 'Записана тежест (кг)'].forEach(text => {
        const cell = element('th', text); cell.scope = 'col'; row.append(cell);
      });
      head.append(row);
      const body = element('tbody');
      for (const point of series.points) {
        const row = element('tr'), date = element('td'), time = element('time', point.recorded_at.replace('T', ' ').replace('+00:00', ''));
        time.dateTime = point.recorded_at;
        date.append(time);
        row.append(date, element('td', String(point.value)), element('td', String(series.completed_sets)),
          element('td', series.load_kg === null ? (en ? 'Not recorded' : 'Незаписана') : String(series.load_kg)));
        body.append(row);
      }
      table.append(caption, head, body); wrapper.append(table); root.append(wrapper);
    }
    for (const key of ['evidence', 'limitations', 'next_step']) {
      if (!data[key]) continue;
      const paragraph = element('p', undefined, 'chat-progress-' + key);
      const labels = en ? {evidence: 'Evidence', limitations: 'Limits', next_step: 'Next step'} :
        {evidence: 'Данни', limitations: 'Граници', next_step: 'Следваща стъпка'};
      paragraph.append(element('strong', labels[key] + ': '), document.createTextNode(data[key]));
      root.append(paragraph);
    }
    return root;
  }
  window.ApexProgressAnalysis = Object.freeze({validate, render});
}());
