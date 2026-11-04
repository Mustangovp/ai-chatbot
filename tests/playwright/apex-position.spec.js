const { test, expect } = require('@playwright/test');

const completeProfile = {
  goal:'fat_loss', age:'30', weight:'75', height:'178', gender:'male', level:'beginner', equipment:'gym',
  sleepQuality:'average', stressLevel:'moderate', recoveryFeel:'ok', activityLevel:'moderate', frequency:'3',
};

const seed = ({ profile, workouts=[] }) => {
  const owner='apex-position-test';
  localStorage.setItem('apexAnonymousOwnerV1',owner);
  const prefix=`apexOwnedV1:anonymous:${owner}:`;
  if(profile)localStorage.setItem(`${prefix}apexProfile`,JSON.stringify(profile));
  localStorage.setItem(`${prefix}apexWorkoutLog`,JSON.stringify(workouts));
};

function completedWorkout(ts=Date.now(), id=1){
  return {ts,workout_id:`00000000-0000-4000-8000-${String(id).padStart(12,'0')}`,
    execution_schema:'workout-execution-v1',execution_state:'completed',completion:100,
    exercises:[{prescription_id:`push-${id}`,exercise_id:'bodyweight.push_up',exercise_version:'1.0.0',
      execution_state:'completed',completed_sets:2,actual_repetitions:8,completed_repetitions:8},
    {prescription_id:`hold-${id}`,exercise_id:'bodyweight.plank',exercise_version:'1.0.0',prescription_type:'duration',
      execution_state:'completed',completed_sets:2,actual_repetitions:null,actual_duration_seconds:30}]};
}

function accountRow(record=completedWorkout()){
  return {id:'server-'+record.workout_id,occurred_at:new Date().toISOString(),type:'Training',
    execution_state:record.execution_state,completion:record.completion,exercises:record.exercises,
    completion_evidence:{workout_id:record.workout_id,plan_id:'fixture-plan',plan_version:'1.0.0',session_id:'session-1',
      completion_timestamp:new Date(record.ts).toISOString(),execution_state:record.execution_state,exercises:record.exercises}};
}

async function accountPage(page,language,rows){
  await page.route('**/auth/me',route=>route.fulfill({json:{authenticated:true,email:'position-owner@example.test',plan:'free',status:'free'}}));
  await page.route('**/api/profile',route=>route.fulfill({json:{profile:{...completeProfile,language},training_constraint_records:[]}}));
  await page.route('**/api/history',route=>route.fulfill({json:{workouts:rows,nutrition:[],timeline:[]}}));
  await page.route('**/api/conversations?*',route=>route.fulfill({json:{messages:[]}}));
  await page.route('**/api/athlete-model',route=>route.fulfill({json:{}}));
  await page.goto('/app?lang='+language);
  await expect.poll(()=>page.evaluate(()=>DATA_OWNER.kind)).toBe('account');
  await expect.poll(()=>page.evaluate(()=>historyCache().length)).toBe(rows.length);
  await page.evaluate(()=>applyReadout());
}

async function positionFor(page, profile, workouts=[]){
  await page.evaluate(({profile,workouts})=>{
    ownedStorageSet('apexProfile',JSON.stringify(profile));
    ownedStorageSet('apexWorkoutLog',JSON.stringify(workouts));
    applyReadout();
  },{profile,workouts});
  return Number(await page.locator('#position-value').textContent());
}

test.describe('APEX Position', () => {
  test.use({ viewport:{width:390,height:844}, isMobile:true, hasTouch:true });

  test('is absent until the profile assessment is complete', async ({page}) => {
    await page.addInitScript(seed,{profile:{goal:'fat_loss'}});
    await page.goto('/app?lang=en');
    await expect(page.locator('#apex-position-readout')).toBeHidden();
    await expect(page.locator('#position-value')).toBeHidden();
  });

  test('is bounded, deterministic, explained, and does not restore percentage labels', async ({page}) => {
    await page.addInitScript(seed,{profile:completeProfile});
    await page.goto('/app?lang=en');
    await page.locator('#overview-context > summary').click();
    await expect(page.locator('#apex-position-readout')).toBeVisible();
    await expect(page.locator('#position-label')).toHaveText('APEX POSITION');
    await expect(page.locator('#position-zone')).toHaveText(/REBUILD|UNDER LOAD|BUILDING|STRONG|PEAK RANGE/);
    await expect(page.locator('#position-signals')).toContainText('Sleep: Average');
    await expect(page.locator('#position-note')).toContainText('Not a measured biometric or clinical readiness score');
    const first=Number(await page.locator('#position-value').textContent());
    await page.reload();
    expect(Number(await page.locator('#position-value').textContent())).toBe(first);
    expect(first).toBeGreaterThanOrEqual(0); expect(first).toBeLessThanOrEqual(100);
    await expect(page.locator('body')).not.toContainText(/Recovery\s*%|Fatigue\s*%|Stress\s*%/);
    await expect(page.locator('#core')).toBeVisible();
  });

  test('responds consistently to better inputs and recent completed training load', async ({page}) => {
    await page.addInitScript(seed,{profile:completeProfile});
    await page.goto('/app?lang=en');
    await page.locator('#overview-context > summary').click();
    const strong=await positionFor(page,{...completeProfile,sleepQuality:'good',stressLevel:'low',recoveryFeel:'fresh'});
    const poor=await positionFor(page,{...completeProfile,sleepQuality:'poor',stressLevel:'high',recoveryFeel:'tired'});
    const baseline=await positionFor(page,completeProfile);
    const recent=await positionFor(page,completeProfile,[completedWorkout(Date.now(),1),completedWorkout(Date.now(),2)]);
    expect(strong).toBeGreaterThan(poor);
    expect(recent).toBeLessThan(baseline);
    await expect(page.locator('#position-signals')).toContainText('2 recent completed workouts');
  });

  test('localizes the readout and retains Core visibility without horizontal overflow', async ({page}) => {
    await page.addInitScript(seed,{profile:completeProfile});
    await page.goto('/app?lang=bg');
    await page.locator('#overview-context > summary').click();
    await expect(page.locator('#apex-position-readout')).toBeVisible();
    await expect(page.locator('#position-label')).toHaveText('APEX ПОЗИЦИЯ');
    await expect(page.locator('#position-note')).toContainText('Не е измерен биометричен показател или клинична оценка за готовност');
    await expect(page.locator('#core')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });

  for(const state of ['partial','skipped','abandoned','unknown']){
    test(`P0: ${state} execution contributes no completed load or fatigue`,async({page})=>{
      await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang=en');
      const baseline=await positionFor(page,completeProfile);
      const record={...completedWorkout(),execution_state:state,completion:state==='partial'?50:null};
      expect(await positionFor(page,completeProfile,[record])).toBe(baseline);
      expect(await page.evaluate(()=>physiologyInputs().recentWorkouts)).toBe(0);
    });
  }

  test('P0: legacy, contradictory, missing and malformed execution cannot become verified load',async({page})=>{
    await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang=en');
    const baseline=await positionFor(page,completeProfile),valid=completedWorkout();
    const noActual=structuredClone(valid);delete noActual.exercises[0].actual_repetitions;
    const wrongDose=structuredClone(valid);wrongDose.exercises[1].actual_repetitions=30;wrongDose.exercises[1].actual_duration_seconds=null;
    const partialExercise=structuredClone(valid);partialExercise.exercises[0].execution_state='partial';
    const cases=[{ts:Date.now()},{...valid,execution_schema:null},{...valid,completion:50},
      {...valid,completion:'100'},{...valid,exercises:[]},{...valid,exercises:[null]},
      {...valid,workout_id:null},noActual,wrongDose,partialExercise,null,'legacy',{}];
    expect(await positionFor(page,completeProfile,cases)).toBe(baseline);
    expect(await page.evaluate(()=>physiologyInputs().recentWorkouts)).toBe(0);
    expect(await positionFor(page,completeProfile,{not:'an array'})).toBe(baseline);
  });

  test('P0: timestamp types, future dates and exact 48-hour boundary fail closed',async({page})=>{
    await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang=en');
    const records=[completedWorkout(),completedWorkout(),completedWorkout()];
    const result=await page.evaluate(({records,profile})=>{
      const original=Date.now,now=original();Date.now=()=>now;
      try{
        ownedStorageSet('apexProfile',JSON.stringify(profile));
        const count=values=>{ownedStorageSet('apexWorkoutLog',JSON.stringify(values));return physiologyInputs().recentWorkouts;};
        const invalid=[null,false,'not-a-date',String(now),-1,0,now+1,now+86400000,now-48*3600000];
        const invalidCount=count(invalid.map((ts,i)=>({...records[0],ts,workout_id:'invalid-'+i})));
        const boundaryCount=count(records.map((r,i)=>({...r,workout_id:'boundary-'+i,ts:[now,now-48*3600000+1,now-48*3600000][i]})));
        return {invalidCount,boundaryCount};
      }finally{Date.now=original;}
    },{records,profile:completeProfile});
    expect(result).toEqual({invalidCount:0,boundaryCount:2});
  });

  test('P0: repeated cache/account evidence counts one workout, not two',async({page})=>{
    await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang=en');
    const record=completedWorkout();
    const one=await positionFor(page,completeProfile,[record]);
    expect(await positionFor(page,completeProfile,[record,{...record,serverId:'saved'}])).toBe(one);
    expect(await page.evaluate(()=>physiologyInputs().recentWorkouts)).toBe(1);
  });

  test('P0: account completion timestamps preserve timezone and reject normalized impossible dates',async({page})=>{
    await page.goto('/app?lang=en');
    const result=await page.evaluate(()=>({
      utc:workoutCompletionTimestamp('2026-11-03T10:00:00Z'),
      offset:workoutCompletionTimestamp('2026-11-03T12:00:00+02:00'),
      fractions:workoutCompletionTimestamp('2026-11-03T10:00:00.123456+00:00'),
      invalid:[null,123,'2026-02-30T10:00:00Z','2026-11-03T24:00:00Z','2026-11-03T10:00:00','invalid'].map(workoutCompletionTimestamp)
    }));
    expect(result.utc).toBe(Date.parse('2026-11-03T10:00:00Z'));
    expect(result.offset).toBe(result.utc);expect(result.fractions).toBe(result.utc+123);
    expect(result.invalid).toEqual([null,null,null,null,null,null]);
  });

  test('P0: actual execution contract produces a countable completed repetition/duration session',async({page})=>{
    await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang=en');
    const evidence=await page.evaluate(()=>{
      const previous=WO;
      try{
        WO={contract:{plan_id:'fixture',plan_version:'1.0.0',session_id:'s1'},ex:[
          {name:'Push-Up',observedReps:[8,9],completion:{prescription_id:'push',exercise_id:'bodyweight.push_up',exercise_version:'1.0.0',prescription_type:'repetitions',prescribed_sets:2,rep_min:8}},
          {name:'Plank',observedSeconds:[20,25],completion:{prescription_id:'hold',exercise_id:'bodyweight.plank',exercise_version:'1.0.0',prescription_type:'duration',prescribed_sets:2,duration_min_seconds:20}}]};
        const result=workoutExecutionEvidence();ownedStorageSet('apexWorkoutLog',JSON.stringify([result.session]));
        return {state:result.session.execution_state,completion:result.session.completion,count:physiologyInputs().recentWorkouts};
      }finally{WO=previous;}
    });
    expect(evidence).toEqual({state:'completed',completion:100,count:1});
  });

  test('P0: account sync uses completion time, rejects legacy/future/invalid time and preserves partial history',async({page})=>{
    const now=Date.now(),valid=accountRow(completedWorkout(now-3600000,1));
    const old=accountRow(completedWorkout(now-49*3600000,2));
    const future=accountRow(completedWorkout(now+3600000,3));
    const invalid=accountRow(completedWorkout(now,4));invalid.completion_evidence.completion_timestamp='not-a-date';
    const missing=accountRow(completedWorkout(now,5));delete missing.completion_evidence.completion_timestamp;
    const partial=accountRow({...completedWorkout(now,6),execution_state:'partial',completion:50});
    const calendar=accountRow(completedWorkout(now,7));calendar.completion_evidence.completion_timestamp='2026-02-30T10:00:00Z';
    await accountPage(page,'en',[valid,old,future,invalid,missing,partial,calendar]);
    expect(await page.evaluate(()=>physiologyInputs().recentWorkouts)).toBe(1);
    const counts=await page.evaluate(async()=>{
      const before=historyCache().length;await syncFromAccount();
      return {before,after:historyCache().length,count:physiologyInputs().recentWorkouts,partial:historyCache().some(s=>s.execution_state==='partial')};
    });
    expect(counts).toEqual({before:7,after:7,count:1,partial:true});
  });

  for(const language of ['bg','en']){
    test(`${language}: estimate explanation identifies self-report and verified 48-hour evidence`,async({page})=>{
      await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang='+language);
      await page.locator('#overview-context > summary').click();
      const note=page.locator('#position-note');
      await expect(note).toContainText(language==='en'?'self-reported':'самооценката');
      await expect(note).toContainText('48');
      await expect(note).toContainText(language==='en'?'verified completed workouts':'потвърдени завършени тренировки');
      await expect(page.locator('#position-signals')).toContainText(language==='en'?'No recent completed workouts':'Няма скорошни завършени тренировки');
      await expect(page.locator('#core')).toBeVisible();
    });
    for(const authenticated of [false,true]){
      test(`${language} ${authenticated?'account':'anonymous'}: privacy distinguishes storage, cache and AI processing`,async({page})=>{
        if(authenticated)await accountPage(page,language,[]);
        else{await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang='+language);}
        await page.evaluate(()=>menuAction('privacy'));
        const panel=page.locator('#panel-modal .info-body');
        await expect(panel.locator('h4')).toHaveCount(3);
        for(const phrase of language==='en'?['Without sign-in','local cache','server-side account records','AI provider','across sessions and devices']:
          ['Без вход','локален кеш','сървърните записи в акаунта','AI доставчика','между сесии и устройства'])await expect(panel).toContainText(phrase);
        await expect(panel).not.toContainText(/only in (?:your |the )?browser|not sold|не се продават|единствено в браузъра/i);
        await expect(panel).toContainText(language==='en'?'It does not diagnose, prescribe, or replace medical professionals.':'Не диагностицира, не предписва и не замества медицински специалисти.');
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      });
    }
    for(const width of [360,1440]){
      test(`${language} ${width}: explanation and privacy remain accessible without obscuring the Core`,async({page})=>{
        await page.setViewportSize({width,height:width===360?800:900});
        await page.addInitScript(seed,{profile:completeProfile});await page.goto('/app?lang='+language);
        await page.locator('#overview-context > summary').click();
        await page.locator('#position-note').scrollIntoViewIfNeeded();
        await expect(page.locator('#position-note')).toBeVisible();
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
        await expect.poll(()=>page.evaluate(()=>{
          const canvas=document.getElementById('core');
          return canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data.some(value=>value>0);
        })).toBe(true);
        await page.evaluate(()=>menuAction('privacy'));
        await page.locator('#panel-close').scrollIntoViewIfNeeded();
        await expect(page.locator('#panel-close')).toBeInViewport();
        await page.locator('#panel-close').focus();await page.keyboard.press('Enter');
        await expect(page.locator('#panel-modal')).not.toHaveClass(/on/);
        await expect(page.locator('#core')).toBeVisible();
      });
    }
  }
});
