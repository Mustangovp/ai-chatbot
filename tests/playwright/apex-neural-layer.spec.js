const { test, expect } = require('@playwright/test');

const completeProfile = {
  goal:'fat_loss', age:'30', weight:'75', height:'178', gender:'male', level:'beginner', equipment:'gym',
  sleepQuality:'average', stressLevel:'moderate', recoveryFeel:'ok', activityLevel:'moderate', frequency:'3',
};

const seed = ({ profile }) => {
  const owner='apex-neural-layer-test';
  localStorage.setItem('apexAnonymousOwnerV1',owner);
  const prefix=`apexOwnedV1:anonymous:${owner}:`;
  if(profile)localStorage.setItem(`${prefix}apexProfile`,JSON.stringify(profile));
};

async function appSource(page){
  return page.evaluate(async()=>fetch('/app?lang=en').then(response=>response.text()));
}

test.describe('APEX Neural Layer', () => {
  let errors=[];

  test.beforeEach(async ({ page }) => {
    errors=[];
    page.on('pageerror', error=>errors.push(error.message||String(error)));
  });

  test('is a LivingCore canvas presentation layer with no second animation or state authority', async ({ page }) => {
    await page.addInitScript(seed,{profile:completeProfile});
    await page.setViewportSize({width:1440,height:900});
    await page.goto('/app?lang=en');

    await expect(page.locator('#core[data-neural-layer="living-core"]')).toBeVisible();
    expect(await page.locator('canvas').count()).toBe(1);
    await expect(page.locator('#apex-position-readout')).toBeVisible();

    const source=await appSource(page);
    const neural=source.slice(source.indexOf('drawNeuralLayer('),source.indexOf('  step(now){',source.indexOf('drawNeuralLayer(')));
    expect(neural).toContain('this.presence.base');
    expect(neural).toContain('NEURAL_STATE_STYLE');
    expect(neural).toContain('this.neuralRoutes');
    expect(source).toContain('const breath=this.presence.breath.value');
    expect(source).toContain('this.drawNeuralLayer(g,{c1,c2},ps,breath');
    expect(source).toContain('this.buildNeuralRoutes();');
    expect(neural).toContain('this.presence.touchInfluence');
    expect(neural).toContain('this.presence.reduced');
    expect(neural).toContain("const mobileWaiting=mobile&&base==='waiting'");
    expect(neural).toContain("const mobileAnswering=mobile&&base==='answering'");
    expect(neural).toContain('mobileAnswering?3:style.routes');
    expect(neural).toContain('mobileAnswering?0:style.links');
    expect(neural).toContain('mobile&&(mobileWaiting||mobileAnswering)&&i===2?3:i');
    expect(neural).not.toContain('requestAnimationFrame');
    expect(neural).not.toContain('const routes=[');
    expect(neural).not.toContain('createLinearGradient');
    expect(neural).not.toContain('createRadialGradient');
    expect(neural).not.toContain('new PresenceEngine');
    expect(neural).not.toContain('new BreathEngine');
    for(const state of ['waiting','listening','thinking','answering','resting','recovering','goodbye']){
      expect(source).toContain(`${state}:`);
    }
    expect(errors).toEqual([]);
  });

  test('keeps the incomplete calibration state intact on mobile', async ({ page }) => {
    await page.setViewportSize({width:390,height:844});
    await page.addInitScript(seed,{profile:{goal:'fat_loss'}});
    await page.goto('/app?lang=en');
    await expect(page.locator('#apex-position-readout')).toBeHidden();
    await expect(page.locator('#core')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

    expect(errors).toEqual([]);
  });

  test('keeps the Bulgarian position/readout contract intact on mobile', async ({ page }) => {
    await page.setViewportSize({width:390,height:844});
    await page.addInitScript(seed,{profile:completeProfile});
    await page.goto('/app?lang=bg');
    await expect(page.locator('#apex-position-readout')).toBeVisible();
    await expect(page.locator('#position-label')).toHaveText('APEX ПОЗИЦИЯ');
    await expect(page.locator('#brand-tagline')).toHaveText('Твоят връх. Твоят пулс.');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    expect(errors).toEqual([]);
  });

  test('uses the existing reduced-motion flag and retains continuous pointer input without errors', async ({ page }) => {
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.addInitScript(seed,{profile:completeProfile});
    await page.setViewportSize({width:390,height:844});
    await page.goto('/app?lang=en');
    await expect(page.locator('#core')).toBeVisible();
    const source=await appSource(page);
    expect(source).toContain("matchMedia('(prefers-reduced-motion: reduce)')");
    expect(source).toContain('window.addEventListener(\'pointermove\'');
    await page.mouse.move(195,330);
    await page.mouse.down();
    await page.mouse.up();
    await page.waitForTimeout(80);
    await expect(page.locator('#core')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    expect(errors).toEqual([]);
  });
});
