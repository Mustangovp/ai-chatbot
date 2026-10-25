const { test, expect } = require('@playwright/test');
const profile = {goal:'strength', level:'intermediate', equip:'home', age:'30', weight:'75', height:'178', gender:'male'};
function analysis(language = 'en', status = 'comparable', unit = 'reps') {
  const en = language === 'en';
  return {version:'training-progress-chat-v1', language, status,
    summary:status==='comparable' ? (en ? 'Recorded repetitions: 9 to 12. This alone does not establish fitness progress.' :
      'Записани повторения: от 9 до 12. Само това не доказва подобрение на формата.') :
      status==='insufficient' ? (en ? 'One observation is not enough for a comparison.' : 'Един запис не е достатъчен за сравнение.') :
      (en ? 'No verified comparison is available.' : 'Няма налично проверено сравнение.'),
    evidence:en ? 'Verified completed workouts. User-recorded values. UTC.' : 'Проверени завършени тренировки. Въведени стойности. UTC.',
    limitations:en ? 'Technique and recovery may differ.' : 'Техника и възстановяване може да се различават.',
    next_step:en ? 'Record actual execution after your next workout.' : 'Запиши реалното изпълнение след следващата тренировка.',
    series:['comparable','insufficient'].includes(status) ? {
      exercise_id:'dumbbell.front_squat', exercise_version:'1.0.0',
      display_name:en ? 'Dumbbell Front Squat' : 'Преден клек с дъмбели', unit, completed_sets:2, load_kg:null,
      points:[1, 3, 5].slice(0, status === 'insufficient' ? 1 : 3).map((day, index) => ({
        recorded_at:`2026-10-0${day}T09:03:04.123456+00:00`, value:[9,10,12][index]}))
    } : null};
}
async function setup(page, language = 'en') {
  await page.route('https://**/*', route => route.abort());
  await page.route('**/auth/me', route => route.fulfill({json:{authenticated:true,email:'analysis@example.invalid',plan:'free',status:'free'}}));
  await page.route('**/api/profile', route => route.fulfill({json:{profile:{...profile,language},training_constraint_records:[]}}));
  await page.route('**/api/history', route => route.fulfill({json:{workouts:[]}}));
  await page.route('**/api/conversations?*', route => route.fulfill({json:{messages:[]}}));
  await page.route('**/api/athlete-model', route => route.fulfill({json:{}}));
  await page.route('**/api/next-move', route => route.fulfill({status:404,json:{}}));
  await page.goto('/app?lang=' + language);
  await expect.poll(() => page.evaluate(() => SESSION.authenticated && DATA_OWNER.kind === 'account')).toBe(true);
  await page.evaluate(profile => {
    ownedStorageSet('apexProfile', JSON.stringify(profile));
    document.getElementById('profile-modal').classList.remove('on');
    enterConsult('');
  }, profile);
}
async function send(page, data, done = true) {
  const stream = [{progress_analysis:data}, {t:'Verified training analysis.'}, ...(done ? [{done:true}] : [])];
  await page.route('**/chat', route => route.fulfill({contentType:'text/event-stream',
    body:stream.map(event => 'data: ' + JSON.stringify(event) + '\n\n').join('')}));
  await page.locator('#user-in').fill(data.language === 'bg' ? 'Анализирай прогреса ми' : 'Analyse my training progress');
  await page.locator('#user-in').press('Enter');
}
for (const language of ['bg', 'en']) for (const width of [390, 1440]) {
  test(`same evidence drives accessible chart and chronological table ${language} ${width}`, async ({page}) => {
    await page.setViewportSize({width, height:width === 390 ? 844 : 900});
    await setup(page, language);
    const data = analysis(language);
    await send(page, data);
    const root = page.locator('.chat-progress-analysis');
    await expect(root).toBeVisible();
    await expect(root.locator('svg')).toHaveCount(1);
    await expect(root.locator('table')).toHaveCount(1);
    await expect(root.locator('tbody tr')).toHaveCount(3);
    expect(await root.locator('time').evaluateAll(nodes => nodes.map(node => node.dateTime)))
      .toEqual(data.series.points.map(point => point.recorded_at));
    expect(await root.locator('tbody tr td:nth-child(2)').allTextContents()).toEqual(['9','10','12']);
    expect(await root.locator('circle title').allTextContents()).toEqual(data.series.points.map(point =>
      point.recorded_at + ': ' + point.value + (language === 'en' ? ' reps' : ' повт.')));
    await expect(root).toContainText(language === 'bg' ? 'Незаписана' : 'Not recorded');
    const scroll = root.locator('.chat-progress-table');
    await scroll.focus(); await expect(scroll).toBeFocused();
    if (width === 390) expect(await scroll.evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await root.evaluate(node => node.getBoundingClientRect().right <= innerWidth)).toBe(true);
    await expect(root.locator('th[scope="col"]')).toHaveCount(4);
    expect(await root.locator('th').nth(1).evaluate(node => getComputedStyle(node).wordBreak)).toBe('normal');
    await page.evaluate(() => {document.activeElement.blur();const feed=document.getElementById('feed');feed.scrollTop=0;});
    if (process.env.APEX_M21_SCREENSHOTS) await page.screenshot({
      path:process.env.APEX_M21_SCREENSHOTS + `/progress-chat-${language}-${width}.png`,fullPage:true});
  });
}
for (const language of ['bg','en']) for (const status of ['empty','insufficient','unavailable','auth_required']) {
  test(`${status} has no fake chart in ${language}`, async ({page}) => {
    await setup(page,language);
    await send(page, analysis(language,status));
    const root = page.locator('.chat-progress-analysis');
    await expect(root).toBeVisible();
    await expect(root.locator('svg')).toHaveCount(0);
    await expect(root.locator('tbody tr')).toHaveCount(status === 'insufficient' ? 1 : 0);
  });
}
test('duration observations retain seconds', async ({page}) => {
  await setup(page);
  await send(page, analysis('en','comparable','seconds'));
  await expect(page.locator('.chat-progress-analysis th').nth(1)).toHaveText('Recorded duration (sec)');
  await expect(page.locator('.chat-progress-analysis figcaption')).toHaveText('Recorded duration (sec)');
});
test('sub-millisecond timestamps remain exact and do not create an invalid chart', async ({page}) => {
  await setup(page);
  const data=analysis();
  data.series.points.forEach((point,index) => {point.recorded_at=`2026-10-01T09:03:04.12345${index}+00:00`;});
  await send(page,data);
  await expect(page.locator('.chat-progress-analysis svg')).toHaveCount(1);
  expect(await page.locator('.chat-progress-analysis polyline').getAttribute('points')).not.toContain('NaN');
  expect(await page.locator('.chat-progress-analysis time').evaluateAll(nodes=>nodes.map(node=>node.dateTime)))
    .toEqual(data.series.points.map(point=>point.recorded_at));
});
for (const language of ['bg','en']) test(`incomplete SSE discards analysis and does not persist partial output in ${language}`, async ({page}) => {
  await setup(page,language);
  await send(page, analysis(language), false);
  await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','interrupted');
  await expect(page.locator('.chat-progress-analysis')).toHaveCount(0);
  expect(await page.evaluate(() => getHistory().filter(item => item.role === 'assistant'))).toEqual([]);
  expect(await page.evaluate(() => ChatLifecycle.current.progressAnalysis)).toBe(null);
});
test('structured payload stays hidden until done, cancellation discards it', async ({page}) => {
  await setup(page);
  await page.evaluate(data => {
    const x = ChatLifecycle.begin('Analyse my progress',{},[]);
    ChatLifecycle.waiting(x); ChatLifecycle.metadata(x,{progress_analysis:data});
    ChatLifecycle.content(x,'UNFINALIZED_VALUES');
  }, analysis());
  await expect(page.locator('.chat-progress-analysis')).toHaveCount(0);
  await expect(page.locator('#feed')).not.toContainText('UNFINALIZED_VALUES');
  await page.evaluate(() => ChatLifecycle.cancel());
  expect(await page.evaluate(() => ChatLifecycle.current.progressAnalysis)).toBe(null);
  await expect(page.locator('#feed')).not.toContainText('UNFINALIZED_VALUES');
});
test('malformed metadata fails closed and untrusted text never becomes HTML', async ({page}) => {
  await setup(page);
  const invalid = analysis(); invalid.series.points[0].value = '<img src=x onerror=alert(1)>';
  await send(page, invalid);
  await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','failed');
  await expect(page.locator('.chat-progress-analysis')).toHaveCount(0);
  await expect(page.locator('#feed img')).toHaveCount(0);
  const safe = analysis(); safe.summary = '<img src=x onerror=window.hacked=true>';
  await send(page, safe);
  await expect(page.locator('.chat-progress-analysis')).toContainText('<img src=x');
  await expect(page.locator('.chat-progress-analysis img')).toHaveCount(0);
  expect(await page.evaluate(() => window.hacked)).toBeUndefined();
});
test('owner rotation cancels pending analysis without exposing previous account evidence', async ({page}) => {
  await setup(page);
  await page.evaluate(data => {
    const x=ChatLifecycle.begin('Analyse my progress',{},[]);
    ChatLifecycle.waiting(x);ChatLifecycle.metadata(x,{progress_analysis:data});ChatLifecycle.content(x,'OWNED_EVIDENCE');
    SESSION.authenticated=false;rotateAnonymousOwner();
  },analysis());
  await expect(page.locator('.chat-progress-analysis')).toHaveCount(0);
  await expect(page.locator('#feed')).not.toContainText('OWNED_EVIDENCE');
});
test('ordinary Markdown chat remains unchanged', async ({page}) => {
  await setup(page);
  await page.evaluate(() => {
    const x=ChatLifecycle.begin('Hello',{},[]);ChatLifecycle.waiting(x);
    ChatLifecycle.content(x,'**Keep going.**');ChatLifecycle.complete(x);
  });
  await expect(page.locator('#feed strong')).toHaveText('Keep going.');
  await expect(page.locator('.chat-progress-analysis')).toHaveCount(0);
});
for (const language of ['bg','en']) {
  test(`persisted analysis fallback remains a factual table, not a workout ${language}`, async ({page}) => {
    await setup(page,language);
    const text=language==='bg' ? 'Записани повторения: от 9 до 12.\n\nПреден клек с дъмбели\n\n| UTC | Записан брой (бр.) |\n| --- | --- |\n| 2026-10-01T10:00:00+00:00 | 9 |' :
      'Recorded repetitions: 9 to 12.\n\nDumbbell Front Squat\n\n| UTC | Recorded count (repetitions) |\n| --- | --- |\n| 2026-10-01T10:00:00+00:00 | 9 |';
    await page.evaluate(text=>{appendCoach().innerHTML=renderMarkdown(text);},text);
    await expect(page.locator('#feed table tbody tr')).toHaveCount(1);
    await expect(page.locator('#feed .workout-protocol, #feed [data-workout-rejected]')).toHaveCount(0);
  });
}
for (const language of ['bg','en']) test(`real local persisted evidence reaches chat without a model request in ${language}`, async ({page}) => {
  test.skip(!process.env.APEX_M21_INTEGRATION_URL,'Requires the isolated synthetic SQLite preview.');
  await page.route('https://**/*',route=>route.abort());
  await page.setViewportSize({width:390,height:844});
  await page.goto(process.env.APEX_M21_INTEGRATION_URL + '/app?lang='+language);
  await expect.poll(()=>page.evaluate(()=>SESSION.authenticated&&DATA_OWNER.kind==='account')).toBe(true);
  await page.evaluate(()=>{document.getElementById('profile-modal').classList.remove('on');enterConsult('');});
  const completed=page.waitForResponse(response=>new URL(response.url()).pathname==='/chat'&&response.request().method()==='POST');
  await page.locator('#user-in').fill(language==='bg'?'Анализирай тренировъчния ми прогрес':'Analyse my training progress');
  await page.locator('#user-in').press('Enter');
  const response=await completed;
  expect(response.status()).toBe(200);
  const root=page.locator('.chat-progress-analysis');
  await expect(root).toBeVisible();
  const metadata=await page.evaluate(()=>ChatLifecycle.current.progressAnalysis);
  const records=await (await page.request.get(process.env.APEX_M21_INTEGRATION_URL+'/api/progress')).json();
  const persisted=records.record.recent_sessions.map(session=>({
    recorded_at:session.completed_at,
    value:session.exercises.find(item=>item.exercise_id===metadata.series.exercise_id)[
      metadata.series.unit==='seconds'?'completed_duration_seconds':'completed_repetitions']
  })).reverse();
  expect(metadata.series.points).toEqual(persisted);
  await expect(root.locator('tbody tr')).toHaveCount(metadata.series.points.length);
  expect(await root.locator('time').evaluateAll(nodes=>nodes.map(node=>node.dateTime)))
    .toEqual(metadata.series.points.map(point=>point.recorded_at));
  await expect(root).toContainText(language==='bg'?'въведени':'user-recorded');
  await expect(root.locator('svg')).toHaveCount(1);
  await page.evaluate(()=>{document.getElementById('feed').scrollTop=0;});
  if(process.env.APEX_M21_SCREENSHOTS)await page.screenshot({path:process.env.APEX_M21_SCREENSHOTS+'/progress-real-persisted-'+language+'-390.png',fullPage:true});
});
