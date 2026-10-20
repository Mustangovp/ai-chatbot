const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

test.use({ baseURL: process.env.LIVE_VOICE_BASE_URL || 'http://127.0.0.1:5001' });
const stage = process.env.APEX_UX_STAGE || 'after';
const screenshots = process.env.APEX_UX_SCREENSHOTS || 'C:/tmp/apex-app-ux';
const viewports = [{ width: 360, height: 780 }, { width: 390, height: 844 },
  { width: 768, height: 1024 }, { width: 1440, height: 900 }];

async function mount(page, language) {
  await page.goto('/app?lang=' + language);
  await page.evaluate(async () => {
    await loadSession(); document.getElementById('profile-modal').classList.remove('on');
    exitConsult(); document.getElementById('ui').scrollTop = 0;
  });
  await page.evaluate(() => document.fonts.ready);
}

async function capture(page, name) {
  fs.mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: path.join(screenshots, `${stage}-${name}.png`) });
}

async function fits(page, selectors) {
  return page.evaluate(selectors => ({
    overflow: document.documentElement.scrollWidth > innerWidth,
    controls: selectors.map(selector => {
      const rect = document.querySelector(selector).getBoundingClientRect();
      return { selector, left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
        visible: rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight };
    }),
  }), selectors);
}

for (const language of ['bg', 'en']) {
  for (const viewport of viewports) {
    test(`${language} ${viewport.width}: overview and conversation hierarchy`, async ({ page }) => {
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      await page.setViewportSize(viewport); await mount(page, language);
      await capture(page, `${language}-${viewport.width}-overview`);
      if (stage === 'before') {
        console.log('BEFORE', language, viewport.width, await fits(page, ['.cta:not(.ghost)', '.cta.ghost']));
      } else {
        expect((await fits(page, ['.cta:not(.ghost)', '.cta.ghost'])).controls.every(item => item.visible)).toBe(true);
        await expect(page.locator('#overview-context')).not.toHaveAttribute('open', '');
        await expect(page.locator('#calibration-facts')).not.toBeVisible();
        await page.locator('#overview-context > summary').focus();
        await page.keyboard.press('Enter');
        await expect(page.locator('#calibration-facts')).toBeVisible();
        await page.locator('#overview-context > summary').press('Enter');
      }
      const before = await page.evaluate(() => JSON.stringify(pfLoad()));
      await page.locator('.cta.ghost').click();
      await expect(page.locator('#consult')).toBeVisible();
      await page.locator('#user-in').fill(language === 'bg' ? 'Как да се фокусирам днес?' : 'What should I focus on today?');
      await page.locator('.send-btn').click();
      await expect(page.locator('#feed')).toContainText(language === 'bg' ? 'mock отговор' : 'mock reply');
      await page.evaluate(() => {
        for (let index = 0; index < 12; index++) appendCoach().textContent =
          'DEMO: A previous coaching exchange remains available in this conversation.';
        hardScroll();
      });
      await capture(page, `${language}-${viewport.width}-conversation`);
      const layout = await fits(page, ['.back-btn', '#user-in', '#mic-btn', '.send-btn']);
      if (stage === 'before') console.log('BEFORE CHAT', language, viewport.width, layout);
      else {
        expect(layout.overflow).toBe(false);
        expect(layout.controls.every(item => item.visible)).toBe(true);
        const scroll = await page.locator('#feed').evaluate(feed => {
          const scrollable = feed.scrollHeight > feed.clientHeight;
          feed.scrollTop = 0;
          return { scrollable, atStart: feed.scrollTop === 0 };
        });
        expect(scroll).toEqual({ scrollable: true, atStart: true });
        await page.locator('#user-in').focus(); await page.keyboard.press('Tab');
        await expect(page.locator('#mic-btn')).toBeFocused();
        await page.keyboard.press('Tab'); await expect(page.locator('.send-btn')).toBeFocused();
        await expect.poll(() => page.evaluate(() => {
          const canvas = document.getElementById('core');
          return canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data.some(value => value > 0);
        })).toBe(true);
        expect(await page.evaluate(() => JSON.stringify(pfLoad()))).toBe(before);
        expect(errors).toEqual([]);
      }
    });
  }
}

test('short visual viewport keeps the composer and drawer reachable', async ({ page }) => {
  test.skip(stage === 'before', 'acceptance check after layout refinement');
  await page.setViewportSize({ width: 390, height: 844 }); await mount(page, 'bg');
  await page.locator('.cta.ghost').click();
  await page.setViewportSize({ width: 390, height: 420 });
  await expect.poll(async () => (await fits(page, ['.back-btn', '#user-in', '#mic-btn', '.send-btn'])).controls.every(item => item.visible)).toBe(true);
  await page.locator('#coach-menu-btn').click();
  await expect(page.locator('#drawer')).toHaveClass('on');
  await page.locator('.drawer-nav').evaluate(nav => { nav.scrollTop = nav.scrollHeight; });
  await expect(page.locator('.drawer-close')).toBeInViewport();
  await page.locator('.drawer-close').click();
  await expect(page.locator('#drawer')).not.toHaveClass('on');
});

test('short overview scrolls to supporting context without clipping the primary action', async ({ page }) => {
  test.skip(stage === 'before', 'short overview acceptance');
  await page.setViewportSize({ width: 360, height: 560 }); await mount(page, 'bg');
  await expect(page.locator('.cta:not(.ghost)')).toBeInViewport();
  await page.locator('#overview-context > summary').scrollIntoViewIfNeeded();
  await expect(page.locator('#overview-context > summary')).toBeInViewport();
  await page.locator('#overview-context > summary').click();
  await page.locator('#calibration-facts').scrollIntoViewIfNeeded();
  await expect(page.locator('#calibration-facts')).toBeInViewport();
});

test('Core contact remains interactive; context disclosure does not become a Core gesture', async ({ page }) => {
  test.skip(stage === 'before', 'new disclosure isolation');
  await page.setViewportSize({ width: 390, height: 844 }); await mount(page, 'en');
  await page.evaluate(() => {
    const original = witness;
    window.contacts = 0;
    window.witness = (fact, payload) => { if (fact === 'contact') contacts++; original(fact, payload); };
  });
  await page.mouse.click(195, 300);
  expect(await page.evaluate(() => contacts)).toBe(1);
  await page.locator('#overview-context > summary').click();
  await expect(page.locator('#overview-context')).toHaveAttribute('open', '');
  expect(await page.evaluate(() => contacts)).toBe(1);
});
