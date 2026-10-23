/* Next Move M1: one owner-bound recommendation, no model calls until approval. */
(() => {
  'use strict';
  let recommendation = null, owner = null, language = null, pending = null, sequence = 0, failed = false, approving = false;
  const copy = () => lang === 'bg' ? {
    loading: 'Преглеждам следващата ти стъпка…', verify: 'Проверявам запазения контекст.',
    unavailable: 'Не мога да потвърдя следващата стъпка.', retry: 'Опитай отново',
    explain: 'Контекстът не е потвърден. Свободният разговор остава достъпен.',
    recorded: 'Има записана завършена тренировка', context: 'Запазеният ти контекст',
    updated: 'Препоръката се промени. Прегледай я и одобри отново.',
    question: 'Как се чувстваш възстановен днес?', choose: 'Избери отговор',
    fresh: 'Добре възстановен', ok: 'Нормално', tired: 'Уморен', save: 'Запази отговора',
    saving: 'Запазване…', error: 'Отговорът не е потвърден. Опитай отново.',
  } : {
    loading: 'Reviewing your next step…', verify: 'Checking your saved context.',
    unavailable: "I can't verify your next step yet.", retry: 'Try again',
    explain: 'Your context could not be verified. Free-form coaching remains available.',
    recorded: 'A completed workout is recorded', context: 'Your saved context',
    updated: 'Your recommendation changed. Review it and approve again.',
    question: 'How recovered do you feel today?', choose: 'Choose an answer',
    fresh: 'Well recovered', ok: 'As usual', tired: 'Tired', save: 'Save my answer',
    saving: 'Saving…', error: 'Your answer was not confirmed. Please try again.',
  };
  const active = () => SESSION.authenticated && DATA_OWNER.kind === 'account';
  const current = (token, id, locale) => currentAccountRequest(token) && sequence === id && lang === locale;
  const button = () => document.querySelector('.cta:not(.ghost)');
  function clear() {
    sequence++; pending?.controller.abort(); pending = null;
    recommendation = null; owner = null; language = null; failed = false; approving = false;
    button().disabled = false;
  }
  function paint() {
    if (!active()) return;
    const c = copy(), ready = recommendation && owner === ownerRequestToken() && language === lang;
    document.getElementById('read-state').textContent = ready ? recommendation.title : failed ? c.unavailable : c.loading;
    document.getElementById('read-sub').textContent = ready ? recommendation.why : failed ? c.explain : c.verify;
    document.getElementById('cta-train').textContent = ready ? recommendation.action_label : failed ? c.retry : c.loading;
    button().disabled = approving || (!ready && !failed);
    const facts = [];
    if (ready) {
      const known = recommendation.known, opts = tr().wiz.opt;
      if (known.goal && opts.goal[known.goal]) facts.push(opts.goal[known.goal]);
      if (known.equipment && opts.equip[known.equipment]) facts.push(opts.equip[known.equipment]);
      if (recommendation.completed_at) facts.push(c.recorded);
      for (const pattern of recommendation.constraints || []) {
        if (TRAINING_CONSTRAINT_LABELS[pattern]) facts.push(TRAINING_CONSTRAINT_LABELS[pattern][lang]);
      }
    }
    const context = document.getElementById('brief-context');
    context.hidden = false; context.textContent = facts.join(' · ') || c.context;
  }
  async function refresh() {
    if (!active()) { clear(); return; }
    const token = ownerRequestToken(), locale = lang;
    if (pending && pending.owner === token && pending.language === locale) return pending.promise;
    pending?.controller.abort();
    const id = ++sequence, controller = new AbortController();
    recommendation = null; failed = false; paint();
    const promise = (async () => {
      try {
        const response = await fetch('/api/next-move?lang=' + locale, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
        const data = await response.json();
        if (!current(token, id, locale)) return;
        if (!response.ok || !valid(data.recommendation)) throw new Error('unavailable');
        recommendation = data.recommendation; owner = token; language = locale;
      } catch (error) {
        if (current(token, id, locale) && error.name !== 'AbortError') failed = true;
      } finally {
        if (current(token, id, locale)) { pending = null; paint(); }
      }
    })();
    pending = { owner: token, language: locale, controller, promise };
    return promise;
  }
  function valid(value) {
    return value && typeof value.decision_id === 'string' && typeof value.title === 'string' &&
      typeof value.why === 'string' && typeof value.action_label === 'string' && value.known &&
      Array.isArray(value.constraints);
  }
  async function approveCurrent() {
    const token = ownerRequestToken(), locale = lang, id = sequence;
    approving = true; paint();
    try {
      const response = await fetch('/api/next-move/approve?lang=' + locale, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision_id: recommendation.decision_id }) });
      const data = await response.json();
      if (!current(token, id, locale)) return;
      if (response.status === 409 && valid(data.recommendation)) {
        recommendation = data.recommendation; toast(copy().updated); return;
      }
      if (!response.ok) throw new Error('unavailable');
      if (data.workflow === 'profile') openProfile(0);
      else if (data.workflow === 'my_training') void showMyTraining();
      else if (data.workflow === 'checkin') showCheckin(token);
      else if (data.workflow === 'chat' && typeof data.message === 'string') enterConsult(data.message);
      else throw new Error('invalid_workflow');
    } catch (_) {
      if (current(token, id, locale)) { failed = true; recommendation = null; }
    } finally {
      if (current(token, id, locale)) { approving = false; paint(); }
    }
  }
  function approve() {
    if (!active()) return false;
    if (failed) void refresh();
    else if (!approving && recommendation && owner === ownerRequestToken() && language === lang) void approveCurrent();
    return true;
  }
  function showCheckin(token) {
    const c = copy();
    showPanel(c.question, '<form id="next-move-checkin"><div class="field"><label for="next-move-recovery">' + esc(c.question) +
      '</label><select required id="next-move-recovery"><option value="">' + esc(c.choose) + '</option>' +
      ['fresh', 'ok', 'tired'].map(value => '<option value="' + value + '">' + esc(c[value]) + '</option>').join('') +
      '</select></div><p id="next-move-status" role="status"></p><button class="save" type="submit">' + esc(c.save) + '</button></form>');
    document.getElementById('next-move-checkin').addEventListener('submit', async event => {
      event.preventDefault(); if (!currentAccountRequest(token)) return;
      const form = event.currentTarget, locale = lang, id = sequence, value = document.getElementById('next-move-recovery').value;
      const submit = form.querySelector('button'); if (submit.disabled) return; submit.disabled = true;
      document.getElementById('next-move-status').textContent = c.saving;
      try {
        const response = await fetch('/api/next-move/check-in?lang=' + locale, { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ recovery: value }) });
        const data = await response.json(); if (!current(token, id, locale) || !form.isConnected) return;
        if (!response.ok || !valid(data.recommendation)) throw new Error('not_saved');
        recommendation = data.recommendation; owner = token; language = locale; failed = false;
        closePanel(); paint();
      } catch (_) {
        if (current(token, id, locale) && form.isConnected) document.getElementById('next-move-status').textContent = c.error;
      } finally { if (currentAccountRequest(token) && form.isConnected) submit.disabled = false; }
    });
  }
  window.ApexNextMove = { paint, refresh, approve, clear };
})();
