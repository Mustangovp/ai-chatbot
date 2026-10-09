const {test,expect}=require('@playwright/test');

const profile={goal:'strength',level:'intermediate',equip:'home',age:'30',weight:'75',height:'178',gender:'male'};
const decision=(kind,extra={})=>({exercise_id:'dumbbell.front_squat',exercise_version:'1.0.0',display_name:'Dumbbell Front Squat',decision_type:kind,...extra});
const decisions=[decision('increase_load',{load_delta_kg:'1.25'}),decision('increase_repetitions',{repetition_delta:2}),
  decision('increase_sets',{set_delta:1}),decision('maintain'),decision('deload'),
  decision('replace_exercise',{replacement:{exercise_id:'bodyweight.push_up',exercise_version:'1.0.0',display_name:'Push-Up'}})];

async function setup(page,{language='en',authenticated=true,adjustments=decisions,fail=false}={}){
  const calls={chat:0,writes:[],reads:0};
  page.on('request',request=>{if(new URL(request.url()).pathname==='/chat')calls.chat++;});
  await page.route('**/auth/me',route=>route.fulfill({json:authenticated?{authenticated:true,email:'local-result@example.com',plan:'free',status:'free'}:{authenticated:false,plan:'free'}}));
  await page.route('**/api/profile',route=>route.fulfill({json:{profile:{...profile,language},training_constraint_records:[]}}));
  await page.route('**/api/history',route=>route.fulfill({json:{workouts:[]}}));
  await page.route('**/api/conversations?*',route=>route.fulfill({json:{messages:[]}}));
  await page.route('**/api/athlete-model',route=>route.fulfill({json:{}}));
  await page.route('**/api/workout',route=>{
    const body=route.request().postDataJSON();calls.writes.push(body);
    return route.fulfill({status:fail?503:200,json:fail?{}:{ok:true,id:'saved-workout',adaptation:{
      workout_id:body.workout_completion.workout_id,decisions:adjustments}}});
  });
  await page.route('**/api/my-training',route=>{calls.reads++;return route.fulfill({json:{latest_workout:null,last_completed:{
    completed_at:'2026-10-05T07:00:00Z',completion_percent:100,exercises:[{
      exercise_id:'dumbbell.front_squat',exercise_version:'1.0.0',prescription_type:'repetitions',completed_sets:1,
      completed_repetitions:10,completed_load:16}],adjustments},active_constraints:[]}});});
  await page.goto('/app?lang='+language);
  await expect.poll(()=>page.evaluate(()=>SESSION.authenticated)).toBe(authenticated);
  if(authenticated)await expect.poll(()=>page.evaluate(()=>DATA_OWNER.kind)).toBe('account');
  await page.evaluate(({profile,language})=>{
    lang=language;ownedStorageSet('apexProfile',JSON.stringify(profile));
    enterConsult('');document.getElementById('profile-modal').classList.remove('on');
    const items=[{prescription_id:'result-squat',exercise_id:'dumbbell.front_squat',exercise_version:'1.0.0',prescribed_sets:1,
      prescription_type:'repetitions',rep_min:8,rep_max:12,rest_seconds:60,difficulty:'intermediate'},
      {prescription_id:'result-hold',exercise_id:'bodyweight.hollow_hold',exercise_version:'1.0.0',prescribed_sets:1,
      prescription_type:'duration',rep_min:null,rep_max:null,duration_min_seconds:20,duration_max_seconds:40,rest_seconds:60,difficulty:'intermediate'}]
      .map(item=>({...item,display_name:ApexExerciseInstructions.display(ApexExerciseInstructions.findByExerciseId(item.exercise_id),language)}));
    const session={session_id:'result-session',session_index:1,exercises:items};
    pendingTrainingCompletion={plan_id:'result-plan',plan_version:'training-plan-blueprint-v3',sessions:[session]};
    pendingCompletionSessions=[session];
    appendCoach().innerHTML=renderMarkdown(['| Exercise | Sets | Reps | Rest |','| --- | --- | --- | --- |',
      ...items.map(item=>`| ${item.display_name} | 1 | ${item.prescription_type==='duration'?'20-40 sec':'8-12'} | 60 |`)].join('\n'));
    startWorkout('result-session');
  },{profile,language});
  return calls;
}
async function complete(page){
  await page.locator('#wo-reps-in').fill('10');
  await page.locator('#wo-weight-in').fill('16');
  await page.locator('#wo-effort-in').selectOption('productive');
  await page.locator('.wo-effort details summary').click();
  await page.locator('#wo-rpe-in').selectOption('7');
  await page.locator('#wo-rir-in').selectOption('3');
  await page.locator('button[onclick="completeSet()"]').click();
  await page.locator('button[onclick="endRest()"]').click();
  await page.locator('#wo-reps-in').fill('32');
  await page.locator('button[onclick="completeSet()"]').click();
  await expect(page.locator('[data-workout-result="completed"]')).toBeVisible();
}
for(const language of ['bg','en']){
  test(`completion facts and persisted next adjustments remain truthful in ${language}`,async({page})=>{
    const calls=await setup(page,{language});await complete(page);
    await expect(page.locator('.completion-adjustments li')).toHaveCount(6);
    const root=page.locator('.wo-summary'),recorded=root.locator('[data-completion-section="recorded"]');
    await expect(root.locator('[data-completion-section]')).toHaveCount(3);
    await expect(root.locator('[data-completion-save-status]')).toHaveText(language==='bg'?'Запазено в профила ти.':'Saved to your account.');
    await recorded.locator('summary').click();
    await expect(recorded).toContainText('10 '+(language==='bg'?'повт.':'reps'));
    await expect(recorded).toContainText('32 '+(language==='bg'?'сек':'sec'));
    await expect(recorded).toContainText('16 '+(language==='bg'?'кг':'kg'));
    await expect(recorded).toContainText(language==='bg'?'Точно както трябва':'About right');
    await expect(recorded).toContainText('RPE 7');await expect(recorded).toContainText('RIR 3');
    const hold=recorded.locator('li').nth(1);
    await expect(hold).not.toContainText(/RPE \d|RIR \d|kg|кг|reps|повт\.|About right|Точно както трябва/);
    await expect(recorded).not.toContainText(/0 kg|0 кг|8–12|20–40/);
    const next=root.locator('[data-completion-section="adjustment"]');
    const replacement=await page.evaluate(language=>ApexExerciseInstructions.display(ApexExerciseInstructions.findByExerciseId('bodyweight.push_up'),language),language);
    for(const text of (language==='bg'?['1.25 кг','2 повторения','1 серия','Запази текущата схема','по-леко',replacement]:
      ['1.25 kg','2 repetitions','1 set','Keep the current prescription','lighter',replacement]))await expect(next).toContainText(text);
    await expect(root).not.toContainText(/policy|fatigue|recovery|readiness|calories|decision_id|🏁/i);
    await expect(root.locator('img,.wo-ex-glyph')).toHaveCount(0);
    expect(calls.writes).toHaveLength(1);expect(calls.chat).toBe(0);
    expect(calls.writes[0]).not.toHaveProperty('recovery');
    expect(calls.writes[0].workout_completion.exercises[1]).toMatchObject({prescription_type:'duration',completed_repetitions:null,completed_duration_seconds:32});
  });
  test(`no event means no confirmed adjustment in ${language}`,async({page})=>{
    await setup(page,{language,adjustments:[]});await complete(page);
    await expect(page.locator('[data-completion-section="adjustment"]')).toContainText(language==='bg'?
      'Няма потвърдена тренировъчна корекция.':'No training adjustment has been confirmed.');
  });
}
test('anonymous completion is usable and never invents server adaptation',async({page})=>{
  const calls=await setup(page,{authenticated:false});await complete(page);
  await expect(page.locator('[data-completion-section="adjustment"]')).toContainText('Sign in to preserve training adaptations across sessions.');
  await expect(page.locator('.completion-adjustments')).toHaveCount(0);
  expect(calls.writes).toHaveLength(0);expect(calls.chat).toBe(0);
});
test('completion actions never auto-send and My Training reads persisted adjustment',async({page})=>{
  const calls=await setup(page);await complete(page);
  await expect(page.locator('.completion-adjustments li')).toHaveCount(6);
  await page.clock.install();
  await page.locator('button[onclick="finishToMyTraining()"]').click();
  await expect(page.locator('#my-training')).toBeVisible();
  await expect(page.locator('#my-training .completion-adjustments li')).toHaveCount(6);
  expect(calls.reads).toBe(1);
  await page.evaluate(()=>closePanel());
  await page.evaluate(()=>finishToCoach());
  await page.clock.runFor(1000);
  await expect(page.locator('#consult')).toHaveClass(/\bon\b/);
  await expect(page.locator('#user-in')).toHaveValue('');expect(calls.chat).toBe(0);
  await page.reload();await page.evaluate(()=>showMyTraining());
  await expect(page.locator('#my-training .completion-adjustments li')).toHaveCount(6);
  expect(calls.chat).toBe(0);
});
test('failed account save does not claim a recorded adjustment or block completion',async({page})=>{
  await setup(page,{fail:true});await complete(page);
  await expect(page.locator('[data-completion-save-status]')).toContainText('Account save has not been confirmed.');
  await expect(page.locator('.completion-adjustments')).toHaveCount(0);
  await expect(page.locator('button[onclick="finishToCoach()"]')).toBeEnabled();
});
for(const viewport of [{width:1440,height:900},{width:390,height:844},{width:360,height:800}]){
  test(`completion result remains readable at ${viewport.width}`,async({page})=>{
    await page.setViewportSize(viewport);await setup(page);await complete(page);
    await expect(page.locator('.completion-adjustments li')).toHaveCount(6);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const root=await page.locator('.wo-summary').boundingBox();
    expect(root.x).toBeGreaterThanOrEqual(0);expect(root.x+root.width).toBeLessThanOrEqual(viewport.width);
    for(const selector of ['[data-completion-section="completed"]','button[onclick="finishToMyTraining()"]','button[onclick="finishToCoach()"]']){
      const element=page.locator(selector);await element.scrollIntoViewIfNeeded();await expect(element).toBeInViewport();
    }
    if(process.env.APEX_COMPLETION_SCREENSHOTS)await page.screenshot({path:process.env.APEX_COMPLETION_SCREENSHOTS+`/completion-${viewport.width}.png`});
  });
}
