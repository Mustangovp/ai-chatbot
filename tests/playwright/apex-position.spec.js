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
    await expect(page.locator('#apex-position-readout')).toBeVisible();
    await expect(page.locator('#position-label')).toHaveText('APEX POSITION');
    await expect(page.locator('#position-zone')).toHaveText(/REBUILD|UNDER LOAD|BUILDING|STRONG|PEAK RANGE/);
    await expect(page.locator('#position-signals')).toContainText('Sleep: Average');
    await expect(page.locator('#position-note')).toContainText('Not a medical measurement');
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
    const strong=await positionFor(page,{...completeProfile,sleepQuality:'good',stressLevel:'low',recoveryFeel:'fresh'});
    const poor=await positionFor(page,{...completeProfile,sleepQuality:'poor',stressLevel:'high',recoveryFeel:'tired'});
    const baseline=await positionFor(page,completeProfile);
    const recent=await positionFor(page,completeProfile,[{ts:Date.now()},{ts:Date.now()}]);
    expect(strong).toBeGreaterThan(poor);
    expect(recent).toBeLessThan(baseline);
    await expect(page.locator('#position-signals')).toContainText('2 recent completed workouts');
  });

  test('localizes the readout and retains Core visibility without horizontal overflow', async ({page}) => {
    await page.addInitScript(seed,{profile:completeProfile});
    await page.goto('/app?lang=bg');
    await expect(page.locator('#apex-position-readout')).toBeVisible();
    await expect(page.locator('#position-label')).toHaveText('APEX ПОЗИЦИЯ');
    await expect(page.locator('#position-note')).toContainText('Не е медицинско измерване');
    await expect(page.locator('#core')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });
});
