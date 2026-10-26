const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const off=process.env.H1_BASE_URL||'http://127.0.0.1:5007';
const on=process.env.H1_NEXT_MOVE_URL||'http://127.0.0.1:5017';
const shots=process.env.H1_SCREENSHOTS||'C:/tmp/apex-h1-screenshots';
const profile={goal:'strength',level:'intermediate',equipment:'home',frequency:'3',age:'30',weight:'75',height:'178',gender:'male',sleepQuality:'good',stressLevel:'low',recoveryFeel:'fresh',activityLevel:'moderate'};
async function mount(page,language='en',url=off){
  await page.route('https://**/*',route=>/fonts\.(?:googleapis|gstatic)\.com/.test(new URL(route.request().url()).hostname)?route.continue():route.abort());
  await page.route('**/api/profile',route=>route.fulfill({json:{profile:{...profile,language},training_constraint_records:[]}}));
  await page.goto(url+'/app?lang='+language);
  await page.evaluate(async()=>{await loadSession();document.getElementById('profile-modal').classList.remove('on');exitConsult();document.getElementById('ui').scrollTop=0;});
  await page.evaluate(()=>document.fonts.ready);
}
for(const language of ['bg','en'])for(const width of [390,1440])test(`H1 ${language} ${width}: factual overview, geometry and keyboard`,async({page})=>{
  await page.setViewportSize({width,height:width===390?844:900});
  let nextReads=0;page.on('request',request=>{if(new URL(request.url()).pathname==='/api/next-move')nextReads++;});
  await mount(page,language);
  await expect(page.locator('#hud-level')).toHaveText(language==='bg'?'Среден':'Intermediate');
  await expect(page.locator('#hud-frequency')).toHaveText(language==='bg'?'3 / седмица':'3 / week');
  await expect(page.locator('#hud-source')).toContainText('DEMO');
  await expect(page.locator('#hud-data-note')).toContainText(language==='bg'?'Няма проверено измерване':'No verified readiness measurement');
  await expect(page.locator('#holo-readouts')).toHaveAttribute('aria-describedby','hud-data-note');
  await expect(page.locator('#holo-readouts')).toHaveAccessibleDescription(language==='bg'?/Няма проверено измерване/:/No verified readiness measurement/);
  await expect(page.locator('#hud-data-note')).not.toBeVisible();
  await page.locator('#overview-context > summary').focus();await page.keyboard.press('Enter');
  await expect(page.locator('#hud-data-note')).toBeVisible();
  await page.keyboard.press('Enter');await expect(page.locator('#hud-data-note')).not.toBeVisible();
  await expect(page.locator('#apex-position-readout')).not.toBeVisible();
  await expect(page.locator('.cta:not(.ghost)')).toBeInViewport();
  expect(nextReads).toBe(0);
  const bounds=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,
    boxes:['#read-state','#read-sub','#holo-readouts','.cta:not(.ghost)','#overview-context'].map(selector=>{
      const r=document.querySelector(selector).getBoundingClientRect();return{left:r.left,right:r.right,top:r.top,bottom:r.bottom};})}));
  expect(bounds.overflow).toBe(false);expect(bounds.boxes.every(r=>r.left>=0&&r.right<=width)).toBe(true);
  expect(bounds.boxes.every(r=>r.top>=0&&r.bottom<=(width===390?844:900))).toBe(true);
  expect(bounds.boxes[0].bottom<=bounds.boxes[1].top).toBe(true);
  expect(bounds.boxes[1].bottom<=bounds.boxes[2].top).toBe(true);
  expect(bounds.boxes[2].bottom<=bounds.boxes[3].top).toBe(true);
  expect(bounds.boxes[3].bottom<=bounds.boxes[4].top).toBe(true);
  const coversCenter=await page.evaluate(()=>{
    const radius=Math.min(innerWidth,innerHeight)*.136,cx=innerWidth/2,cy=innerHeight*.46;
    return ['.holo-heading','#holo-readouts','.cta-row','.holo-provenance','#overview-context'].some(selector=>{
      const el=document.querySelector(selector);if(el.hidden)return false;const r=el.getBoundingClientRect();
      return r.left<cx+radius&&r.right>cx-radius&&r.top<cy+radius&&r.bottom>cy-radius;
    });
  });expect(coversCenter).toBe(false);
  await page.locator('.cta:not(.ghost)').focus();await expect(page.locator('.cta:not(.ghost)')).toBeFocused();
  expect(await page.locator('.cta:not(.ghost)').evaluate(el=>getComputedStyle(el).outlineStyle)).not.toBe('none');
  await page.evaluate(()=>document.activeElement.blur());
  fs.mkdirSync(shots,{recursive:true});await page.screenshot({path:shots+`/h1-${language}-${width}.png`});
  await page.locator('.cta.ghost').click();await expect(page.locator('#consult')).toBeVisible();
  await expect(page.locator('#holo-instrument')).toHaveCount(0);
  expect(await page.locator('#core').evaluate(el=>getComputedStyle(el).filter)).toBe('none');
});

for(const language of ['bg','en'])test(`H1 ${language}: incomplete profile keeps its data disclaimer accessible`,async({page})=>{
  await mount(page,language);
  await page.evaluate(()=>{ownedStorageSet('apexProfile','{}');applyReadout();});
  await expect(page.locator('#hud-level,#hud-frequency')).toHaveText(language==='bg'?['Непосочено','Непосочено']:['Not provided','Not provided']);
  await expect(page.locator('#overview-context > summary')).toBeVisible();
  await expect(page.locator('#hud-data-note')).not.toBeVisible();
  const before=await page.evaluate(()=>JSON.stringify(pfLoad()));
  await page.locator('#overview-context > summary').focus();await page.keyboard.press('Enter');
  await expect(page.locator('#hud-data-note')).toBeVisible();await expect(page.locator('#calibration-facts')).not.toBeVisible();
  expect(await page.evaluate(()=>JSON.stringify(pfLoad()))).toBe(before);
  expect(await page.locator('#core').evaluate(el=>getComputedStyle(el).filter)).toBe('none');
});
test('H1 unavailable values, stale physiology and owner clear never manufacture a number',async({page})=>{
  await mount(page);
  await page.evaluate(()=>{
    ownedStorageSet('apexProfile',JSON.stringify({level:'ELITE',frequency:99,recoveryFeel:'fresh',readiness:100,updated_at:'2000-01-01'}));applyReadout();
  });
  await expect(page.locator('#hud-level,#hud-frequency')).toHaveText(['Not provided','Not provided']);
  await expect(page.locator('#holo-readouts')).not.toContainText('99');
  await expect(page.locator('#holo-readouts')).not.toContainText('100');
  await page.evaluate(()=>ApexHolographicHud.clear('bg'));
  await expect(page.locator('#hud-level,#hud-frequency')).toHaveText(['Непосочено','Непосочено']);
});
for(const language of ['bg','en'])test(`H1 Next Move ON keeps one approval and its existing workflow in ${language}`,async({page})=>{
  let approvals=0,chats=0;
  await page.route('**/api/next-move?*',route=>route.fulfill({json:{recommendation:{decision_id:'h1-owned-evidence',kind:'checkin',known:{goal:'strength',equipment:'home'},constraints:[],completed_at:null,
    title:language==='bg'?'Как си възстановен днес?':'How recovered do you feel today?',why:language==='bg'?'Профилът не е днешна оценка.':'A profile is not a fresh recovery check.',action_label:language==='bg'?'Отговори за днес':"Answer today's check-in"}}}));
  await page.route('**/api/next-move/approve?*',route=>{approvals++;return route.fulfill({json:{workflow:'checkin'}});});
  page.on('request',request=>{if(new URL(request.url()).pathname==='/chat')chats++;});
  await mount(page,language,on);
  await expect(page.locator('#cta-train')).toHaveText(language==='bg'?'Отговори за днес':"Answer today's check-in");
  await page.locator('.cta:not(.ghost)').click();await expect(page.locator('#next-move-checkin')).toBeVisible();
  expect(approvals).toBe(1);expect(chats).toBe(0);
});
test('H1 HUD is transparent to original Core touch; motion and breathing keep advancing',async({page})=>{
  await page.setViewportSize({width:390,height:844});await mount(page);
  await page.evaluate(()=>{window.h1Contacts=0;const original=witness;window.witness=(fact,payload)=>{if(fact==='contact')h1Contacts++;original(fact,payload);};});
  const before=await page.evaluate(()=>core.t);
  const breath=await page.evaluate(()=>core.presence.breath.phase);
  await expect.poll(()=>page.evaluate(()=>core.t)).toBeGreaterThan(before);
  await expect.poll(()=>page.evaluate(()=>core.presence.breath.phase)).not.toBe(breath);
  expect(await page.locator('#holo-readouts').evaluate(el=>getComputedStyle(el).pointerEvents)).toBe('none');
  expect(await page.locator('#core').evaluate(el=>getComputedStyle(el).filter)).toBe('none');
  await page.mouse.click(195,350);expect(await page.evaluate(()=>h1Contacts)).toBe(1);
  await page.locator('#overview-context > summary').click();expect(await page.evaluate(()=>h1Contacts)).toBe(1);
  await expect.poll(()=>page.evaluate(()=>{const c=document.getElementById('core');return c.getContext('2d').getImageData(0,0,c.width,c.height).data.some(n=>n>0);})).toBe(true);
});
test('H1 reduced motion has no decorative animation and short screens remain scrollable',async({page})=>{
  await page.emulateMedia({reducedMotion:'reduce'});await page.setViewportSize({width:360,height:560});await mount(page,'bg');
  await expect(page.locator('#holo-instrument,.holo-sweep')).toHaveCount(0);
  expect(await page.locator('.cta:not(.ghost)').evaluate(el=>getComputedStyle(el).transitionDuration)).toBe('0s');
  await page.locator('.cta:not(.ghost)').scrollIntoViewIfNeeded();await expect(page.locator('.cta:not(.ghost)')).toBeInViewport();
  await page.locator('#overview-context > summary').scrollIntoViewIfNeeded();await expect(page.locator('#overview-context > summary')).toBeInViewport();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('H1 account rotation clears prior profile readouts',async({page})=>{
  await mount(page);
  await expect(page.locator('#hud-frequency')).toHaveText('3 / week');
  await page.evaluate(()=>{SESSION.authenticated=false;rotateAnonymousOwner();applyReadout();});
  await expect(page.locator('#hud-level,#hud-frequency')).toHaveText(['Not provided','Not provided']);
  await expect(page.locator('#hud-source')).toHaveText('DEMO profile');
});
test('H1 200 percent text zoom retains readable action and contrast',async({page})=>{
  await page.setViewportSize({width:390,height:844});await mount(page,'en');
  for(const hovered of [false,true]){
    if(hovered)await page.locator('.cta:not(.ghost)').hover();
    const ratio=await page.locator('.cta:not(.ghost)').evaluate(el=>{
      const style=getComputedStyle(el),luminance=color=>{
        const rgb=color.match(/\d+(?:\.\d+)?/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});
        return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722;
      };
      const a=luminance(style.color),b=luminance(style.backgroundColor);return(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    });expect(ratio).toBeGreaterThanOrEqual(4.5);
  }
  await page.evaluate(()=>{document.body.style.zoom='2';});
  await page.locator('.cta:not(.ghost)').scrollIntoViewIfNeeded();await expect(page.locator('.cta:not(.ghost)')).toBeVisible();
  const actionBounds=await page.locator('.cta:not(.ghost)').evaluate(el=>{const r=el.getBoundingClientRect();return{left:r.left,right:r.right,width:innerWidth};});
  expect(actionBounds.left>=0&&actionBounds.right<=actionBounds.width).toBe(true);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});
test('H1 matched untouched-base screenshots',async({page})=>{
  test.skip(!process.env.H1_BEFORE_URL,'Optional local baseline screenshot server.');
  fs.mkdirSync(shots,{recursive:true});
  for(const language of ['bg','en'])for(const width of [390,1440]){
    await page.setViewportSize({width,height:width===390?844:900});await mount(page,language,process.env.H1_BEFORE_URL);
    await page.screenshot({path:shots+`/before-${language}-${width}.png`});
  }
});
