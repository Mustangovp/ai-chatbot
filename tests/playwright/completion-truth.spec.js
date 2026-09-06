const {test, expect} = require('@playwright/test');

async function start(page) {
  await page.goto('/app?lang=en');
  await page.evaluate(() => {
    ownedStorageSet('apexProfile',JSON.stringify({goal:'strength',age:'30',weight:'75',height:'178',gender:'male',level:'beginner',equip:'full_gym'}));
    enterConsult('');document.getElementById('profile-modal').classList.remove('on');
    window.executionPosts=[];
    const original=window.fetch;
    window.fetch=async (url,options)=>{
      if(url==='/api/workout'){executionPosts.push(JSON.parse(options.body));return new Response('{}',{status:200});}
      return original(url,options);
    };
    SESSION.authenticated=true;
    const session={session_id:'truth-session',session_index:1,exercises:['Push-up','Squat'].map((name,i)=>({
      prescription_id:'p'+i,exercise_id:'exercise.'+i,exercise_version:'1.0.0',display_name:name,
      prescribed_sets:2,rep_min:8,rep_max:12,rest_seconds:60
    }))};
    pendingTrainingCompletion={plan_id:'truth-plan',plan_version:'v2',sessions:[session]};
    pendingCompletionSessions=[session];
    const el=appendCoach();
    el.innerHTML=renderMarkdown('| Exercise | Sets | Reps | Rest |\n| --- | --- | --- | --- |\n| Push-up | 2 | 8-12 | 60 |\n| Squat | 2 | 8-12 | 60 |');
    startWorkout('truth-session');
  });
}
async function set(page,reps=null) {
  if(reps!==null)await page.locator('#wo-reps-in').fill(String(reps));
  await page.locator('button[onclick="completeSet()"]').click();
  if(await page.locator('button[onclick="endRest()"]').count())await page.locator('button[onclick="endRest()"]').click();
}
async function posted(page){return page.evaluate(()=>executionPosts);}

test('execution: prescribed reps never prefill this or the next set',async({page})=>{
  await start(page);await expect(page.locator('#wo-reps-in')).toHaveValue('');
  await set(page,10);await expect(page.locator('#wo-reps-in')).toHaveValue('');
  await page.locator('#wo-quit-btn').click();
});
test('execution: fully observed sets produce completed canonical evidence',async({page})=>{
  await start(page);for(const reps of [8,10,12,8])await set(page,reps);
  const [body]=await posted(page);
  expect(body.session).toMatchObject({execution_state:'completed',completion:100,execution_schema:'workout-execution-v1'});
  expect(body.workout_completion.exercises).toHaveLength(2);
  expect(body.workout_completion.exercises[0]).toMatchObject({completed_sets:2,actual_repetitions:8,completed_repetitions:8,execution_state:'completed'});
  expect(body.workout_completion.exercises[0]).not.toHaveProperty('name');
  await page.locator('#wo-quit-btn').click();expect(await posted(page)).toHaveLength(1);
});
test('execution: all skipped stays skipped and zero percent',async({page})=>{
  await start(page);
  await page.locator('button[onclick="skipExercise()"]').click();
  await page.locator('button[onclick="skipExercise()"]').click();
  const [body]=await posted(page);
  expect(body.session).toMatchObject({execution_state:'skipped',completion:0});
  expect(body.workout_completion.exercises.every(e=>e.execution_state==='skipped'&&e.completed_sets===0&&e.actual_repetitions===null)).toBe(true);
  await expect(page.locator('#wo-ptop-r')).toHaveText('0%');
});
test('execution: partial exercise and skipped exercise cannot become completed',async({page})=>{
  await start(page);await set(page,8);
  await page.locator('button[onclick="skipExercise()"]').click();
  await page.locator('button[onclick="skipExercise()"]').click();
  const [body]=await posted(page);
  expect(body.session).toMatchObject({execution_state:'partial',completion:25});
  expect(body.workout_completion.exercises.map(e=>e.execution_state)).toEqual(['partial','skipped']);
});
test('execution: final screen with missing reps stays unknown',async({page})=>{
  await start(page);for(let i=0;i<4;i++)await set(page);
  const [body]=await posted(page);
  expect(body.session).toMatchObject({execution_state:'unknown',completion:null});
  expect(body.workout_completion.exercises.every(e=>e.actual_repetitions===null&&e.completed_repetitions===null)).toBe(true);
  await expect(page.locator('#wo-ptop-r')).toHaveText('—');
  expect(await page.evaluate(()=>buildWorkoutContext(true))).not.toContain('POST-WORKOUT');
});
test('execution: invoking finish without work does not manufacture completion',async({page})=>{
  await start(page);await page.evaluate(()=>finishWorkout());
  const [body]=await posted(page);expect(body.session).toMatchObject({execution_state:'unknown',completion:null});
  expect(body).not.toHaveProperty('workout_completion');
});
test('execution: explicit exit logs abandonment exactly once',async({page})=>{
  await start(page);await set(page,8);await page.locator('#wo-quit-btn').click();
  await page.evaluate(()=>quitWorkout());
  const posts=await posted(page);expect(posts).toHaveLength(1);
  expect(posts[0].session).toMatchObject({execution_state:'abandoned',completion:25});
  expect(posts[0].workout_completion.execution_state).toBe('abandoned');
  expect(await page.evaluate(()=>workoutMemoryLog().at(-1).execution_state)).toBe('abandoned');
});
test('execution: offline/background/unload events and refresh do not infer abandonment',async({page})=>{
  await start(page);await set(page,8);
  await page.evaluate(()=>{window.dispatchEvent(new Event('offline'));document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('pagehide'));window.dispatchEvent(new Event('beforeunload'));});
  expect(await posted(page)).toEqual([]);
  let requests=0;page.on('request',request=>{if(request.url().endsWith('/api/workout'))requests++;});
  await page.reload();expect(requests).toBe(0);
  expect(await page.evaluate(()=>workoutMemoryLog().some(s=>s.execution_state==='abandoned'))).toBe(false);
});
test('execution: legacy local and coach memory cannot claim performed reps',async({page})=>{
  await page.goto('/app?lang=en');
  const result=await page.evaluate(()=>{
    const legacy={completion:100,ts:Date.now(),exercises:[{name:'Squat',sets:3,reps:10,completedRepetitions:10}]};
    ownedStorageSet('apexWorkoutLog',JSON.stringify([legacy]));
    ownedStorageSet('apexCoachMemory',JSON.stringify({lastWorkout:legacy,totalWorkouts:50,exerciseHistory:{Squat:[{sets:3,reps:10}]}}));
    return {log:workoutMemoryLog(),memory:memLoad(),context:buildWorkoutContext(true)};
  });
  expect(result.log[0]).toMatchObject({execution_state:'unknown',completion:null});
  expect(result.log[0].exercises[0]).toMatchObject({completed_sets:null,actual_repetitions:null});
  expect(result.memory.totalWorkouts).toBe(0);expect(result.memory.exerciseHistory.Squat[0].reps).toBeNull();
  expect(result.context).not.toContain('POST-WORKOUT');
});

test('execution: one missing set entry cannot borrow a later observed rep count',async({page})=>{
  await start(page);await set(page);await set(page,8);await set(page,8);await set(page,8);
  const [body]=await posted(page);
  expect(body.session).toMatchObject({execution_state:'partial',completion:50});
  expect(body.workout_completion.exercises[0]).toMatchObject({execution_state:'unknown',actual_repetitions:null,completed_repetitions:null});
});
test('execution: exit before first set is abandoned without fabricated work',async({page})=>{
  await start(page);await page.locator('#wo-quit-btn').click();
  const [body]=await posted(page);
  expect(body.session).toMatchObject({execution_state:'abandoned',completion:null,exercises:[]});
  expect(body).not.toHaveProperty('workout_completion');
});

test('execution: observed work remains partial when every exercise has a missing rep entry',async({page})=>{
  await start(page);await set(page);await set(page,8);await set(page);await set(page,8);
  const [body]=await posted(page);
  expect(body.session.execution_state).toBe('partial');
  expect(body.workout_completion.execution_state).toBe('partial');
  expect(body.workout_completion.exercises.every(e=>e.actual_repetitions===null)).toBe(true);
});
