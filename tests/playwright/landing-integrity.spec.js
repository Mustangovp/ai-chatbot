const { test, expect } = require('@playwright/test');

const athlete = {goal:'strength',age:'33',weight:'76',height:'178',gender:'male',
  level:'intermediate',equipment:'home',frequency:'3'};
const paths = {bg:'/',en:'/en'};
const headings = {bg:'Личен треньор, който мисли, преди да ти даде план.',
  en:'A coach that thinks before giving you a plan.'};

async function prepare(page, language, kind='visitor') {
  const state = {profile:kind==='visitor'?{}:{...athlete,language}, chats:[], navigation:null};
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.route(/googletagmanager\.com|google-analytics\.com/,route=>route.abort());
  await page.addInitScript(({language,kind,athlete})=>{
    localStorage.setItem('apexLang',language);
    localStorage.setItem('apexConsent','denied');
    if(kind==='anonymous-athlete') {
      localStorage.setItem('apexAnonymousOwnerV1','landing-integrity');
      localStorage.setItem('apexOwnedV1:anonymous:landing-integrity:apexProfile',JSON.stringify(athlete));
    }
  },{language,kind,athlete});
  await page.route('**/auth/me',route=>route.fulfill({json:{authenticated:kind==='account',
    email:kind==='account'?'synthetic-landing@example.test':null,plan:'free',status:'free'}}));
  await page.route('**/api/profile',route=>{
    if(route.request().method()==='PUT')state.profile={...state.profile,...route.request().postDataJSON().profile};
    return route.fulfill({json:{ok:true,profile:state.profile,training_constraint_records:[],training_constraint_load_state:'ready'}});
  });
  await page.route('**/api/history',route=>route.fulfill({json:{workouts:[],nutrition:[]}}));
  await page.route('**/api/conversations?*',route=>route.fulfill({json:{messages:[]}}));
  await page.route('**/api/athlete-model',route=>route.fulfill({json:{}}));
  await page.route('**/speak',route=>route.abort());
  await page.route('**/chat',route=>{
    state.chats.push(route.request().postDataJSON());
    return route.fulfill({contentType:'text/event-stream',body:'data: {"t":"Let us review your context first."}\n\ndata: {"done":true}\n\n'});
  });
  page.on('request',request=>{
    if(request.isNavigationRequest()&&new URL(request.url()).pathname==='/app')state.navigation=new URL(request.url());
  });
  await page.goto(paths[language]);
  return state;
}

for (const language of ['bg','en']) {
  test(`${language}: every weight/timeline pair is screened without rewriting the selection`,async({page})=>{
    await prepare(page,language);
    for (const kg of ['3','5','8','10','15','20'])for(const [time,days] of [['2w',14],['1m',30],['2m',60],['3m',90]]) {
      await page.locator('#gl-kg').selectOption(kg);
      await page.locator('#gl-time').selectOption(time);
      const aggressive=Number(kg)*7>days*.9;
      await expect(page.locator('#gl-guidance')).toBeVisible({visible:aggressive});
      await expect(page.locator('#gl-kg')).toHaveValue(kg);
      await expect(page.locator('#gl-time')).toHaveValue(time);
      if(aggressive)await expect(page.locator('#gl-kg')).toHaveAttribute('aria-describedby','gl-guidance');
      else await expect(page.locator('#gl-kg')).not.toHaveAttribute('aria-describedby');
      if(aggressive)await expect(page.locator('.goal-line .gl-btn')).toContainText(language==='bg'?'по-безопасен срок':'safer timeline');
    }
    await page.locator('[data-goal="growth"]').click();
    await expect(page.locator('#gl-guidance')).toBeHidden();
    await expect(page.locator('#gl-other')).toBeVisible();
    await page.locator('[data-goal="burn"]').click();
    await expect(page.locator('#gl-guidance')).toBeVisible();
  });

  for(const kind of ['visitor','anonymous-athlete','account'])for(const aggressive of [true,false]) {
    test(`${language}: ${kind} ${aggressive?'aggressive':'normal'} goal reaches the real app safely`,async({page})=>{
      const state=await prepare(page,language,kind);
      await page.locator('#gl-kg').selectOption(aggressive?'20':'3');
      await page.locator('#gl-time').selectOption(aggressive?'2w':'1m');
      await page.locator('.goal-line .gl-btn').focus();
      await page.keyboard.press('Enter');
      await expect.poll(()=>state.chats.length).toBe(1);
      expect(state.navigation.searchParams.get('lang')).toBe(language);
      expect(state.navigation.searchParams.get('goal')).toBe('burn');
      const turn=state.chats[0];
      expect(turn.lang).toBe(language);
      expect(turn.message).toBe(state.navigation.searchParams.get('q'));
      expect(turn.message).toContain(aggressive?'20+':'3');
      if(aggressive) {
        expect(turn.message).toContain(language==='bg'?'Не създавай план за този срок.':'Do not create a plan for this timeline.');
        expect(turn.message).toContain(language==='bg'?'по-безопасен, персонален срок':'safer, personalized timeline');
        expect(turn.message).not.toContain(language==='bg'?'Дай ми реалистичен план':'Give me a realistic nutrition');
      } else expect(turn.message).toContain(language==='bg'?'Дай ми реалистичен план':'Give me a realistic nutrition');
      if(kind!=='visitor')expect(turn.profile.goal).toBe('strength');
      if(kind==='account')expect(state.profile.goal).toBe('strength');
      await expect(page.locator('#consult')).toHaveClass(/\bon\b/);
      await expect(page.locator('html')).toHaveAttribute('lang',language);
    });
  }

  test(`${language}: the other three goal workflows are unchanged`,async({page})=>{
    for(const goal of ['growth','build','zero']) {
      const state=await prepare(page,language,'account');
      await page.locator(`[data-goal="${goal}"]`).click();
      await page.locator('.goal-line .gl-btn').click();
      await expect.poll(()=>state.chats.length).toBe(1);
      expect(state.navigation.searchParams.get('goal')).toBe(goal);
      expect(state.chats[0].message).not.toContain(language==='bg'?'Не създавай план за този срок.':'Do not create a plan for this timeline.');
      expect(state.profile.goal).toBe('strength');
      await page.unrouteAll({behavior:'wait'});
    }
  });

  for(const width of [1440,390,360]) {
    test(`${language} ${width}: semantic H1, available actions and truthful tier copy`,async({page})=>{
      await page.setViewportSize({width,height:width===1440?900:width===390?844:800});
      await prepare(page,language);
      await page.evaluate(()=>document.fonts.ready);
      const h1=page.locator('h1');
      expect((await h1.textContent()).replace(/\s+/g,' ').trim()).toBe(headings[language]);
      await expect(h1).toHaveAccessibleName(headings[language]);
      await expect(h1.locator('.h1-line')).toHaveCount(3);
      expect(await h1.locator('.h1-line').evaluateAll(lines=>lines.every((line,index)=>
        !index||line.getBoundingClientRect().top>=lines[index-1].getBoundingClientRect().bottom-1))).toBe(true);
      await expect(page.locator('#gl-guidance')).toHaveAttribute('role','status');
      await expect(page.locator('#gl-kg')).toHaveAttribute('aria-describedby','gl-guidance');
      await expect(page.locator('#gl-time')).toHaveAttribute('aria-describedby','gl-guidance');
      await page.locator('.goal-line .gl-btn').focus();
      expect(await page.locator('.goal-line .gl-btn').evaluate(el=>parseFloat(getComputedStyle(el).outlineWidth))).toBeGreaterThanOrEqual(2);
      const layout=await page.locator('.goal-line .gl-btn').evaluate(el=>({right:el.getBoundingClientRect().right,
        bottom:el.getBoundingClientRect().bottom,width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth}));
      expect(layout.overflow).toBe(false);
      expect(layout.right).toBeLessThanOrEqual(layout.width);
      expect(layout.bottom).toBeLessThanOrEqual(layout.height);
      const pricing=page.locator('#pricing');
      await expect(pricing.locator('.plan--core')).toContainText(language==='bg'?'дневния лимит на FREE':'FREE daily message limit');
      await expect(pricing.locator('.plan--core')).toContainText(language==='bg'?'По-дълги съобщения':'Longer messages');
      await expect(pricing.locator('.plan--pro')).toContainText(language==='bg'?'По-дълъг разговор':'Longer conversations');
      await expect(pricing.locator('.plan--pro')).toContainText(language==='bg'?'подробни треньорски отговори':'detailed coaching answers');
      await expect(pricing.locator('[data-paid-unavailable]')).toHaveText(language==='bg'?['Очаквайте скоро','Очаквайте скоро']:['Coming soon','Coming soon']);
      await expect(pricing.locator('a')).toHaveCount(1);
      await expect(pricing).not.toContainText(/exclusive|ексклузив|PDF|priority support|приоритетна поддръжка/i);
      await expect(pricing).toContainText(language==='bg'?'без автоматично подновяване':'no automatic renewal');
    });
  }
}
