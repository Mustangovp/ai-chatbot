const { test, expect } = require('@playwright/test');
const { PNG } = require('playwright-core/lib/utilsBundle');
const fs = require('fs');
const path = require('path');

const views = [[1440, 900], [390, 844], [360, 800]];
const badgeLinks = [
  'https://www.producthunt.com/posts/apex-pulse-pro',
  'https://www.shipit.buzz/products/apex-pulse-pro?ref=badge',
  'https://www.saashub.com/apex-pulse-pro?utm_source=badge&utm_campaign=badge&utm_content=apex-pulse-pro&badge_variant=color&badge_kind=approved',
  'https://launchbuff.com/',
];

async function settle(page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(document.getAnimations().filter(a => Number.isFinite(a.effect.getComputedTiming().endTime)).map(a => a.finished.catch(() => {})));
  });
}

async function anonymous(page) {
  await page.route('**/auth/me', route => route.fulfill({ json: { authenticated: false, plan: 'free', status: 'free' } }));
}

async function app(page, language) {
  await anonymous(page);
  await page.goto(`/app?lang=${language}`);
  await expect(page.locator('#brief-context')).toContainText(language === 'bg' ? 'ПРОФИЛ' : 'PROFILE');
  await expect(page.locator('#profile-modal')).toHaveClass(/on/);
  await page.evaluate(() => { if (document.getElementById('profile-modal').classList.contains('on')) closeProfile(); });
  await settle(page);
}

async function capture(page, name) {
  if (!process.env.APEX_BRAND_QA_DIR) return;
  fs.mkdirSync(process.env.APEX_BRAND_QA_DIR, { recursive: true });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.screenshot({ path: path.join(process.env.APEX_BRAND_QA_DIR, name + '.png') });
}

function contrast(hex) {
  const rgb = hex.match(/[\da-f]{2}/gi).map(v => parseInt(v, 16) / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 1.05 / (rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722 + 0.05);
}

async function actionContrast(page, selector) {
  const style = await page.locator(selector).evaluate(el => {
    const s = getComputedStyle(el);
    return { color: s.color.match(/[\d.]+/g).slice(0, 3).map(Number),
      stops: Array.from(s.backgroundImage.matchAll(/rgb\(([^)]+)\)/g), m => m[1].match(/[\d.]+/g).map(Number)) };
  });
  const luminance = rgb => {
    const c = rgb.map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
    return c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722;
  };
  expect(style.stops).toHaveLength(2);
  style.stops.forEach(bg => expect((luminance(style.color) + 0.05) / (luminance(bg) + 0.05)).toBeGreaterThanOrEqual(4.5));
}

for (const language of ['bg', 'en']) {
  const landing = language === 'bg' ? '/' : '/en';
  for (const [width, height] of views) {
    test(`brand unity landing ${language} ${width}: action, consent, badges and truthful preview`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await page.goto(landing);
      await settle(page);
      await expect(page.locator('#gl-other')).toBeHidden();
      await expect(page.locator('.cookiebar')).toHaveClass(/show/);
      const boxes = await page.evaluate(() => {
        const box = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
        return { action: box('.goal-line .gl-btn'), reassurance: box('header .micro'), cookie: box('.cookiebar'),
          logoRight: document.querySelector('.logo').getBoundingClientRect().right,
          controlsLeft: document.querySelector('.nav-right').getBoundingClientRect().left,
          selects: Array.from(document.querySelectorAll('.goal-line select')).map(el => el.getBoundingClientRect().height),
          overflow: document.documentElement.scrollWidth - innerWidth };
      });
      expect(boxes.action.bottom).toBeLessThan(height);
      expect(boxes.reassurance.bottom).toBeLessThanOrEqual(boxes.cookie.top);
      expect(boxes.overflow).toBeLessThanOrEqual(1);
      expect(boxes.logoRight).toBeLessThanOrEqual(boxes.controlsLeft);
      boxes.selects.forEach(value => expect(value).toBeGreaterThanOrEqual(44));
      await expect(page.locator('header .micro')).toContainText(language === 'bg' ? '10 безплатни съобщения' : '10 free messages');
      await expect(page.locator('.tc-live')).not.toContainText(/live|на живо/);
      await expect(page.locator('.preview-caption')).toContainText(language === 'bg' ? 'Пример' : 'Example');
      const preview = page.locator('.app-preview');
      await preview.scrollIntoViewIfNeeded();
      await expect.poll(() => preview.evaluate(img => img.complete && img.naturalWidth === 390 && img.naturalHeight === 844)).toBe(true);
      await preview.evaluate(img => img.decode());
      expect(await page.locator('header .ph-badge a').evaluateAll(links => links.map(a => a.href))).toEqual(badgeLinks);
      for (const link of await page.locator('header .ph-badge a').all()) await expect(link).toHaveAttribute('target', '_blank');
      const tokens = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--action-pulse'));
      tokens.match(/#[\da-f]{6}/gi).forEach(value => expect(contrast(value)).toBeGreaterThanOrEqual(4.5));
      await actionContrast(page, '.goal-line .gl-btn');
      await actionContrast(page, '.lang-toggle .active');
      await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
      await capture(page, `landing-${language}-${width}`);
      await preview.evaluate(img => img.scrollIntoView({ block: 'center', behavior: 'instant' }));
      await capture(page, `landing-preview-${language}-${width}`);
    });

    test(`brand unity app ${language} ${width}: real Core, stable wordmark and locale home`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await app(page, language);
      await expect(page.locator('#status-pill')).toHaveAttribute('role', 'status');
      expect(await page.locator('#status-pill').evaluate(el => el.tagName)).toBe('SPAN');
      await expect(page.locator('.brand')).toHaveAttribute('href', language === 'bg' ? '/' : '/en');
      const geometry = await page.evaluate(() => {
        const brand = document.querySelector('.brand .bt'), range = document.createRange();
        range.setStartBefore(brand.querySelector('.rd')); range.setEndAfter(brand.childNodes[1]);
        return { lines: new Set(Array.from(range.getClientRects()).map(r => Math.round(r.top))).size,
          right: document.querySelector('.brand').getBoundingClientRect().right,
          statusLeft: document.querySelector('#status-pill').getBoundingClientRect().left,
          overflow: document.documentElement.scrollWidth - innerWidth };
      });
      expect(geometry.lines).toBe(1);
      expect(geometry.right).toBeLessThan(geometry.statusLeft);
      expect(geometry.overflow).toBeLessThanOrEqual(1);
      await actionContrast(page, '.cta:not(.ghost)');
      const pixels = () => page.locator('#core').evaluate(canvas => canvas.toDataURL('image/png').split(',')[1]);
      const shot = Buffer.from(await pixels(), 'base64');
      const image = PNG.sync.read(shot);
      const colors = new Set();
      for (let i = 0; i < image.data.length; i += 16) colors.add(`${image.data[i]},${image.data[i + 1]},${image.data[i + 2]}`);
      expect(colors.size).toBeGreaterThan(100);
      await page.evaluate(() => new Promise(resolve => { let frames = 30; function tick() { if (--frames) requestAnimationFrame(tick); else resolve(); } requestAnimationFrame(tick); }));
      expect(Buffer.from(await pixels(), 'base64').equals(shot)).toBe(false);
      await capture(page, `app-incomplete-${language}-${width}`);
      await page.locator('.brand').click();
      await expect(page).toHaveURL(new RegExp(language === 'bg' ? '/$' : '/en$'));
    });
  }

  test(`brand unity ${language}: native language keyboard and existing seeded consultation`, async ({ page }) => {
    await anonymous(page);
    await page.goto(landing);
    const opposite = language === 'bg' ? 'en' : 'bg';
    const languageLink = page.locator(`.lang-toggle a[data-lang="${opposite}"]`);
    await languageLink.focus(); await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp(opposite === 'en' ? '/en$' : '/$'));
    await page.goto(landing);
    await page.locator('.goal-line .gl-btn').click();
    const url = new URL(page.url());
    expect(url.pathname).toBe('/app'); expect(url.searchParams.get('lang')).toBe(language);
    expect(url.searchParams.get('goal')).toBe('burn');
    await expect(page.locator('#consult')).toHaveClass(/on/);
    await expect(page.locator('#user-in')).not.toHaveValue('');
  });

  test(`brand unity ${language}: drawer modal focus, Escape and restoration`, async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 });
    await app(page, language);
    await page.locator('#menu-btn').focus(); await page.keyboard.press('Enter');
    await expect(page.locator('.drawer-close')).toBeFocused();
    await expect(page.locator('#menu-btn')).toHaveAttribute('aria-expanded', 'true');
    expect(await page.locator('#ui').evaluate(el => el.inert)).toBe(true);
    await page.keyboard.press('Shift+Tab');
    await expect(page.locator('#drawer-nav button').last()).toBeFocused();
    await page.keyboard.press('Tab'); await expect(page.locator('.drawer-close')).toBeFocused();
    for (let i = 0; i < 20; i++) {
      await page.keyboard.press('Tab');
      expect(await page.evaluate(() => !!document.activeElement.closest('#drawer'))).toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(page.locator('#menu-btn')).toBeFocused();
    expect(await page.locator('#ui').evaluate(el => el.inert)).toBe(false);
    await expect(page.locator('#drawer')).toHaveAttribute('aria-hidden', 'true');
    await expect(page.locator('#menu-btn')).toHaveAttribute('aria-expanded', 'false');
  });

  test(`brand unity ${language}: 200 percent reflow and reduced-motion decoration`, async ({ page }) => {
    // A 720x450 CSS viewport represents 200% browser zoom from 1440x900.
    await page.setViewportSize({ width: 720, height: 450 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(landing);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
    for (const selector of ['.ring', '.aurora i', '.marquee-track', 'h1 .grad']) {
      expect(await page.locator(selector).first().evaluate(el => getComputedStyle(el).animationName)).toBe('none');
    }
    await app(page, language);
    await expect(page.locator('meta[name="viewport"]')).not.toHaveAttribute('content', /maximum-scale|user-scalable=no/);
    expect(await page.locator('#ui').evaluate(el => getComputedStyle(el).overflowY)).toBe('auto');
    await page.locator('.cta').first().scrollIntoViewIfNeeded();
    const action = await page.locator('.cta').first().boundingBox();
    expect(action.y).toBeGreaterThanOrEqual(0); expect(action.y + action.height).toBeLessThanOrEqual(450);
    await capture(page, `app-zoom-${language}`);
  });

  test(`brand unity ${language}: privacy reflects passwordless accounts and server history`, async ({ page }) => {
    await page.goto(landing);
    await page.evaluate(() => showLegal('privacy'));
    await expect(page.locator('#legal-content')).toContainText(language === 'bg' ? 'вход без парола' : 'passwordless sign-in');
    await expect(page.locator('#legal-content')).toContainText(language === 'bg' ? 'между сесии и устройства' : 'across sessions and devices');
    await expect(page.locator('#legal-content')).not.toContainText(/only upon payment|само при плащане|does not leave your device/);
  });
}
