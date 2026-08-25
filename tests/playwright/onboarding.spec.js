const { test, expect } = require('@playwright/test');
const complete = { goal:'fat_loss',age:'30',weight:'75',height:'178',gender:'male',level:'beginner',equipment:'gym',sleepQuality:'average',stressLevel:'moderate',recoveryFeel:'ok',activityLevel:'moderate',frequency:'3' };
const seed = (profile) => { const owner='onboarding-test'; localStorage.setItem('apexAnonymousOwnerV1',owner); if(profile)localStorage.setItem(`apexOwnedV1:anonymous:${owner}:apexProfile`,JSON.stringify(profile)); };

test.describe('first-session calibration clarity', () => {
  test.use({ viewport:{width:390,height:844}, isMobile:true, hasTouch:true });
  test('new user sees calibration, opens the existing profile, and does not see fake metrics', async ({page}) => {
    await page.addInitScript(seed, null); await page.goto('/app?lang=en');
    await expect(page.locator('#read-state')).toContainText('calibrate APEX');
    await expect(page.locator('.metrics')).toBeHidden();
    await page.locator('.cta').first().click(); await expect(page.locator('#profile-modal')).toHaveClass(/on/);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await expect(page.locator('#core')).toBeVisible();
  });
  test('completed returning profile exposes only saved facts and keeps training action', async ({page}) => {
    await page.addInitScript(seed, complete); await page.goto('/app?lang=en');
    await expect(page.locator('#profile-modal')).not.toHaveClass(/on/);
    await expect(page.locator('#calibration-facts')).toContainText(/Lose fat/);
    await expect(page.locator('#calibration-facts')).toContainText(/Beginner/);
    await expect(page.locator('.cta').first()).toContainText('Start training');
  });
  test('brand tagline follows the active locale without affecting the Core', async ({page}) => {
    await page.addInitScript(seed, null); await page.goto('/app?lang=en');
    await expect(page.locator('#brand-tagline')).toHaveText('Your peak. Your pulse.');
    await expect(page.locator('#core')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await page.goto('/app?lang=bg');
    await expect(page.locator('#brand-tagline')).toHaveText('Твоят връх. Твоят пулс.');
    await expect(page.locator('#brand-tagline')).not.toContainText('Your peak. Your pulse.');
    await expect(page.locator('#core')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  });
  test('Bulgarian calibration is localized', async ({page}) => {
    await page.addInitScript(seed, null); await page.goto('/app?lang=bg');
    await expect(page.locator('#read-state')).toContainText('калибрираме APEX');
    await expect(page.locator('.cta').first()).toContainText('Завърши калибрацията');
  });
  test('active training constraints remain visible through calibration save', async ({page}) => {
    await page.addInitScript(seed, complete); await page.goto('/app?lang=en');
    await page.evaluate(() => { renderTrainingConstraints([{id:'constraint-1',pattern:'vertical_push',removable:true}]); openProfile(0); saveProfile(); openProfile(0); });
    await expect(page.locator('#training-constraints')).toBeVisible();
    await expect(page.locator('#training-constraints')).toContainText(/overhead pressing/i);
  });
});
