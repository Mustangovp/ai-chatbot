const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
const fixtures=JSON.parse(execFileSync(process.env.APEX_TEST_PYTHON||'python',
  [path.join(__dirname,'../canonical_workout_fixture.py')],{encoding:'utf8'}));
const fixture=language=>structuredClone(fixtures.find(item=>item.id==='bodyweight.plank').languages[language]);
const profile={goal:'strength',level:'intermediate',equip:'home',age:'30',weight:'75',height:'178',gender:'male'};
async function setup(page,language){
  await page.route('https://**/*',route=>route.abort());
  await page.route('**/auth/me',route=>route.fulfill({json:{authenticated:true,email:'delivery@example.invalid',plan:'free',status:'free'}}));
  await page.route('**/api/profile',route=>route.fulfill({json:{profile:{...profile,language},training_constraint_records:[]}}));
  await page.route('**/api/history',route=>route.fulfill({json:{workouts:[]}}));
  await page.route('**/api/conversations?*',route=>route.fulfill({json:{messages:[]}}));
  await page.route('**/api/athlete-model',route=>route.fulfill({json:{}}));
  await page.goto('/app?lang='+language);
  await expect.poll(()=>page.evaluate(()=>SESSION.authenticated&&DATA_OWNER.kind==='account')).toBe(true);
  await page.evaluate(profile=>{ownedStorageSet('apexProfile',JSON.stringify(profile));enterConsult('');
    document.getElementById('profile-modal').classList.remove('on');window.__deliveryReplies=[];
    VoiceBus.on('reply',()=>window.__deliveryReplies.push('reply'));},profile);
  const confirmations=[];
  await page.route('**/api/free-activation/confirm',route=>{confirmations.push(route.request().postDataJSON());return route.fulfill({json:{ok:true}});});
  return confirmations;
}
const invalid={
  null:payload=>{payload.metadata=null;},
  missing:payload=>{delete payload.metadata;},
  empty:payload=>{payload.metadata={};},
  'empty sessions':payload=>{payload.metadata.sessions=[];},
  'null session':payload=>{payload.metadata.sessions=[null];},
  'missing plan identity':payload=>{delete payload.metadata.plan_id;},
  'unknown exercise':payload=>{payload.metadata.sessions[0].exercises[0].exercise_id='unknown.exercise';},
  'empty exercise version':payload=>{payload.metadata.sessions[0].exercises[0].exercise_version='';},
  'mismatched exercise':payload=>{payload.metadata.sessions[0].exercises[0].exercise_id='bodyweight.push_up';},
  'mismatched sets':payload=>{payload.metadata.sessions[0].exercises[0].prescribed_sets++;},
  'mismatched duration':payload=>{payload.metadata.sessions[0].exercises[0].duration_max_seconds++;},
  'mismatched rest':payload=>{payload.metadata.sessions[0].exercises[0].rest_seconds++;},
  'wrong duration unit':payload=>{payload.text=payload.text.replace(/20-40\s*(?:sec|сек)/,'20-40 min');},
  'duplicate session':payload=>{payload.metadata.sessions.push(structuredClone(payload.metadata.sessions[0]));},
  'mismatched session rows':payload=>{payload.text+='\n'+payload.text.split('\n').find(line=>line.startsWith('|')&&!line.includes('---')&&line.includes('20-40'));},
};
async function deliver(page,payload,{done=true,classification='training',duplicate=false}={}){
  const events=[{t:'SUCCESS_BEFORE\n\n'+payload.text+'\n\nSUCCESS_AFTER'}];
  if(Object.hasOwn(payload,'metadata'))events.push({training_completion:payload.metadata});
  if(duplicate)events.push({training_completion:payload.metadata});
  events.push({activation_candidate:{activation_type:'training',token:'synthetic-candidate-'.repeat(3)}});
  if(done)events.push({done:true});
  await page.route('**/chat',route=>route.fulfill({contentType:'text/event-stream',headers:classification?{'X-APEX-Delivery':classification}:{},
    body:events.map(event=>'data: '+JSON.stringify(event)+'\n\n').join('')}));
  await page.locator('#user-in').fill('Workout delivery test');
  await page.locator('#user-in').press('Enter');
}
for(const language of ['bg','en']){
  const failure=language==='bg'?'Тренировката не можа да бъде потвърдена безопасно. Опитай отново.':
    'The workout could not be safely verified. Please try again.';
  for(const [name,tamper]of Object.entries(invalid))test(`${name} fails closed in ${language}`,async({page})=>{
    const confirmations=await setup(page,language),payload=fixture(language);tamper(payload);
    await deliver(page,payload,{classification:name==='missing'?null:'training'});
    await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','failed');
    await expect(page.locator('#feed .msg.a .body')).toHaveText(failure);
    await expect(page.locator('#feed .workout-exercise-card,#feed .start-wo')).toHaveCount(0);
    expect(await page.evaluate(()=>getHistory().filter(item=>item.role==='assistant'))).toEqual([]);
    expect(confirmations).toEqual([]);
    expect(await page.evaluate(()=>window.__deliveryReplies)).toEqual([]);
    expect(await page.evaluate(()=>({activation:ChatLifecycle.current.activationCandidate,verified:ChatLifecycle.current.trainingDeliveryVerified})))
      .toEqual({activation:null,verified:false});
  });
  test(`valid canonical workout remains actionable in ${language}`,async({page})=>{
    const confirmations=await setup(page,language);
    await deliver(page,fixture(language));
    await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','completed');
    await expect(page.locator('.workout-exercise-card')).toHaveAttribute('data-exercise-id','bodyweight.plank');
    await expect.poll(()=>confirmations.length).toBe(1);
    expect(await page.evaluate(()=>getHistory().filter(item=>item.role==='assistant').length)).toBe(1);
    await page.locator('.start-wo').click();
    await expect(page.locator('#workout')).toHaveClass(/\bon\b/);
    expect(await page.evaluate(()=>WO.contract.session_id)).toBe(fixture(language).metadata.sessions[0].session_id);
  });
  test(`interruption before done never reveals or records a workout in ${language}`,async({page})=>{
    const confirmations=await setup(page,language);
    await deliver(page,fixture(language),{done:false});
    await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','interrupted');
    await expect(page.locator('#feed .msg.a .body')).toHaveText(failure);
    await expect(page.locator('#feed .workout-exercise-card,#feed .start-wo')).toHaveCount(0);
    expect(await page.evaluate(()=>getHistory().filter(item=>item.role==='assistant'))).toEqual([]);
    expect(confirmations).toEqual([]);
    expect(await page.evaluate(()=>window.__deliveryReplies)).toEqual([]);
  });
}
test('no title, success prose or protocol leaks before done; duplicate metadata is rejected',async({page})=>{
  await setup(page,'en');
  await page.evaluate(payload=>{
    const x=ChatLifecycle.begin('workout',{},[]);x.deliveryClass='training';ChatLifecycle.waiting(x);
    ChatLifecycle.content(x,'SUCCESS_BEFORE\n\n'+payload.text+'\n\nSUCCESS_AFTER');
    ChatLifecycle.metadata(x,{training_completion:payload.metadata});
  },fixture('en'));
  await expect(page.locator('#feed')).not.toContainText('SUCCESS_BEFORE');
  await expect(page.locator('#feed .workout-exercise-card,#feed .start-wo')).toHaveCount(0);
  await page.evaluate(payload=>{const x=ChatLifecycle.current;ChatLifecycle.metadata(x,{training_completion:payload.metadata});ChatLifecycle.complete(x);},fixture('en'));
  await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','failed');
});
test('plain coaching and a generic table do not require workout metadata',async({page})=>{
  await setup(page,'en');
  await page.route('**/chat',route=>route.fulfill({contentType:'text/event-stream',headers:{'X-APEX-Delivery':'conversation'},
    body:'data: {"t":"**Keep going.**\\n\\n| Topic | Note |\\n| --- | --- |\\n| Consistency | Keep it practical |"}\n\ndata: {"done":true}\n\n'}));
  await page.locator('#user-in').fill('Encourage me');await page.locator('#user-in').press('Enter');
  await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','completed');
  await expect(page.locator('#feed table')).toHaveCount(1);
  await expect(page.locator('#feed strong')).toHaveText('Keep going.');
});
test('unverified history tables and legacy start keys cannot create an active workout',async({page})=>{
  await setup(page,'en');
  await page.evaluate(payload=>{
    pendingTrainingCompletion=null;pendingCompletionSessions=[];
    appendCoach().innerHTML=renderMarkdown(payload.text+'\n\nSUCCESS_AFTER');
    pendingWorkouts.forged=[{name:'Plank',sets:'2',reps:'20-40 sec',rest:'60'}];
    pendingWorkoutContracts.forged=null;startWorkout('forged');
  },fixture('en'));
  await expect(page.locator('[data-workout-rejected]')).toHaveCount(1);
  await expect(page.locator('#feed')).not.toContainText('SUCCESS_AFTER');
  await expect(page.locator('#workout')).not.toHaveClass(/\bon\b/);
});
test('late completion metadata after cancellation cannot restore a workout contract',async({page})=>{
  await setup(page,'en');
  const result=await page.evaluate(payload=>{
    const x=ChatLifecycle.begin('workout',{},[]);x.deliveryClass='training';ChatLifecycle.waiting(x);
    ChatLifecycle.cancel(x);ChatLifecycle.metadata(x,{training_completion:payload.metadata});
    return{state:x.state,completion:x.trainingCompletion,pending:pendingTrainingCompletion,queue:pendingCompletionSessions.length};
  },fixture('en'));
  expect(result).toEqual({state:'CANCELLED',completion:null,pending:null,queue:0});
});
test('a cancelled older response cannot overwrite the successful retry',async({page})=>{
  await setup(page,'en');
  await page.evaluate(payload=>{
    const original=window.fetch;window.__oldStarted=false;
    window.fetch=async(url,options)=>{
      if(url!=='/chat')return original(url,options);
      if(!window.__oldStarted){window.__oldStarted=true;return new Promise(resolve=>{window.__releaseOld=()=>resolve(new Response(
        'data: {"training_completion":null}\n\ndata: {"t":"UNTRUSTED_OLD_RESPONSE"}\n\ndata: {"done":true}\n\n',
        {headers:{'content-type':'text/event-stream','X-APEX-Delivery':'training'}}));});}
      return new Response([{t:payload.text},{training_completion:payload.metadata},{done:true}]
        .map(event=>'data: '+JSON.stringify(event)+'\n\n').join(''),
        {headers:{'content-type':'text/event-stream','X-APEX-Delivery':'training'}});
    };
    document.getElementById('user-in').value='Retry workout';window.__oldRequest=send();
  },fixture('en'));
  await expect.poll(()=>page.evaluate(()=>window.__oldStarted)).toBe(true);
  await page.evaluate(async()=>{ChatLifecycle.cancel();await send();window.__releaseOld();await window.__oldRequest;});
  await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','completed');
  await expect(page.locator('.workout-exercise-card')).toHaveCount(1);
  await expect(page.locator('#feed')).not.toContainText('UNTRUSTED_OLD_RESPONSE');
  expect(await page.evaluate(()=>getHistory().filter(item=>item.role==='assistant').length)).toBe(1);
});
test('a later missing contract cannot borrow the previously validated workout metadata',async({page})=>{
  const confirmations=await setup(page,'en');
  await deliver(page,fixture('en'));
  await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','completed');
  await expect.poll(()=>confirmations.length).toBe(1);
  const missing=fixture('en');delete missing.metadata;
  await deliver(page,missing,{classification:null});
  await expect(page.locator('#consult')).toHaveAttribute('data-chat-state','failed');
  const latest=page.locator('#feed .msg.a').last();
  await expect(latest).toHaveText('APEXThe workout could not be safely verified. Please try again.');
  await expect(latest.locator('.workout-exercise-card,.start-wo')).toHaveCount(0);
  expect(await page.evaluate(()=>getHistory().filter(item=>item.role==='assistant').length)).toBe(1);
  expect(confirmations).toHaveLength(1);
});
