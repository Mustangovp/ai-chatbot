const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const cp = require('child_process');

const evidence = process.env.APEX_PRICING_EVIDENCE || 'C:/tmp/apex-pricing-review';
const base = 'd3f3da818ea2ef32272aed50135fad6ceed5b053';

async function openPricing(page, language) {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.route(/googletagmanager\.com|google-analytics\.com/, route => route.abort());
  await page.addInitScript(language => {
    localStorage.setItem('apexLang', language);
    localStorage.setItem('apexConsent', 'denied');
  }, language);
  const response = await page.goto(language === 'bg' ? '/' : '/en');
  expect(response.status()).toBe(200);
  await page.evaluate(() => document.fonts.ready);
  const section = page.locator('#pricing');
  await section.scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo({
    top: document.querySelector('#pricing').getBoundingClientRect().top + scrollY - 120,
    behavior: 'instant',
  }));
  return section;
}

async function assertLayout(section) {
  const layout = await section.evaluate(section => {
    const cards = [...section.querySelectorAll('.plan')];
    const targets = [...section.querySelectorAll('.plan,.p-price,li,.p-btn,.pricing-shared')];
    return {
      overflow: targets.filter(el => el.scrollWidth > el.clientWidth + 1).map(el => el.className || el.tagName),
      heights: cards.map(el => el.getBoundingClientRect().height),
      bounds: cards.map(el => ({ left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right })),
      viewport: document.documentElement.clientWidth,
      fontSizes: [...section.querySelectorAll('.p-name,.p-price,.p-day,li,.p-btn,.pricing-shared')]
        .map(el => Number.parseFloat(getComputedStyle(el).fontSize)),
    };
  });
  expect(layout.overflow).toEqual([]);
  expect(Math.max(...layout.heights) - Math.min(...layout.heights)).toBeLessThanOrEqual(1);
  expect(Math.min(...layout.fontSizes)).toBeGreaterThanOrEqual(13);
  for (const rect of layout.bounds) {
    expect(rect.left).toBeGreaterThanOrEqual(0);
    expect(rect.right).toBeLessThanOrEqual(layout.viewport);
  }
}

async function assertTruth(section, language) {
  await expect(section.locator('.p-name')).toHaveText(['FREE', 'CORE', 'PRO']);
  await expect(section.locator('.p-price')).toHaveText(['€0', language === 'bg' ? '€9.99/30 дни' : '€9.99/30 days',
    language === 'bg' ? '€14.99/30 дни' : '€14.99/30 days']);
  await expect(section.locator('.plan--free')).toContainText('GPT-6 Luna');
  await expect(section.locator('.plan--free')).toContainText('10');
  await expect(section.locator('.plan--free')).toContainText('24');
  await expect(section.locator('.plan--core li').first()).toContainText('FREE');
  await expect(section.locator('.plan--core')).toContainText('GPT-6 Luna');
  await expect(section.locator('.plan--pro li').first()).toHaveText('GPT-6.1 Sol');
  await expect(section.locator('li')).toHaveCount(12);
  await expect(section.locator('.pricing-shared')).toContainText(language === 'bg' ? 'във всеки план' : 'in every plan');
  await expect(section).toContainText(language === 'bg' ? 'без автоматично подновяване' : 'no automatic renewal');
  await expect(section).not.toContainText(/PDF|priority|приоритет|6×|exclusive|ексклузив|€24.99|Live Voice|€9.99.*60 min/i);
  await expect(section.locator('a')).toHaveCount(1);
  await expect(section.locator('a')).toHaveAttribute('href', '/app?lang=' + language);
  await expect(section.locator('[data-paid-unavailable]')).toHaveCount(2);
  expect(await section.locator('[data-paid-unavailable]').evaluateAll(els => els.every(el =>
    el.tagName === 'SPAN' && !el.hasAttribute('href') && !el.hasAttribute('onclick') && el.tabIndex === -1))).toBe(true);
}

for (const language of ['bg', 'en']) for (const width of [1440, 390, 360]) {
  test(`${language} pricing ${width}: truth, geometry, readable type and screenshot`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 1440 ? 900 : width === 390 ? 844 : 800 });
    const section = await openPricing(page, language);
    await assertLayout(section); await assertTruth(section, language);
    await expect(section).toHaveAttribute('aria-labelledby', 'pricing-title');
    await expect(section.getByRole('heading', { level: 3 })).toHaveCount(3);
    fs.mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `after-${language}-${width}.png`) });
    // Fit the whole section before element capture; avoid smooth-scroll clipping.
    const sectionHeight = await section.evaluate(el => Math.ceil(el.getBoundingClientRect().height));
    await page.setViewportSize({ width, height: Math.max(page.viewportSize().height, sectionHeight + 240) });
    await page.evaluate(() => window.scrollTo({
      top: document.querySelector('#pricing').getBoundingClientRect().top + scrollY - 120,
      behavior: 'instant',
    }));
    await section.screenshot({ path: path.join(evidence, `after-${language}-${width}-section.png`), animations: 'disabled' });
  });
}

for (const language of ['bg', 'en']) {
  test(`${language}: 200% desktop zoom-equivalent reflow`, async ({ browser }) => {
    // A 1440x900 desktop at 200% has a 720x450 CSS viewport and a 2x raster scale.
    const context = await browser.newContext({ viewport: { width: 720, height: 450 }, deviceScaleFactor: 2 });
    try {
      const page = await context.newPage(), section = await openPricing(page, language);
      await assertLayout(section); await assertTruth(section, language);
      await page.screenshot({ path: path.join(evidence, `after-${language}-zoom-200.png`) });
    } finally { await context.close(); }
  });

  test(`${language}: keyboard FREE CTA works and paid statuses are not actions`, async ({ page }) => {
    const section = await openPricing(page, language), action = section.locator('a.p-btn');
    await action.focus(); await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab');
    await expect(action).toBeFocused();
    expect(await action.evaluate(el => Number.parseFloat(getComputedStyle(el).outlineWidth))).toBeGreaterThanOrEqual(2);
    expect(await action.evaluate(el => el.getBoundingClientRect().height)).toBeGreaterThanOrEqual(44);
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp('/app\\?lang=' + language + '$'));
  });

  test(`${language}: pricing text and FREE action meet AA contrast`, async ({ page }) => {
    const section = await openPricing(page, language);
    const ratios = await section.evaluate(section => {
      const rgb = value => (value.match(/[\d.]+/g) || []).map(Number);
      const luminance = color => color.slice(0, 3).map(n => {
        const value = n / 255; return value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
      }).reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
      return [...section.querySelectorAll('.sec-label,h2,.sec-sub,.p-name,.p-price,.p-day,li,.p-btn,.pricing-shared')].map(el => {
        let parent = el, background;
        while (parent) {
          const color = rgb(getComputedStyle(parent).backgroundColor);
          if (color.length === 3 || color[3] === 1) { background = color; break; }
          parent = parent.parentElement;
        }
        const foreground = luminance(rgb(getComputedStyle(el).color)), back = luminance(background || [11, 14, 20]);
        return { text: el.textContent.trim(), ratio: (Math.max(foreground, back) + .05) / (Math.min(foreground, back) + .05) };
      });
    });
    for (const item of ratios) expect(item.ratio, item.text).toBeGreaterThanOrEqual(4.5);
  });
}

test('pricing-only diff preserves landing code, badges, dependencies and all other surfaces', () => {
  const root = path.resolve(__dirname, '../..');
  const outsidePricing = text => text.replace(/\r\n/g, '\n')
    .replace(/\/\* PRICING \*\/[\s\S]*?(?=\/\* (?:TRUST BLOCK|FAQ) \*\/)/, '')
    .replace(/<section\b[^>]*id="pricing"[^>]*>[\s\S]*?<\/section>/, '')
    .split('\n').filter(line => !line.trim().startsWith("'pr-")).join('\n');
  for (const file of ['templates/landing.html', 'templates/landing_en.html']) {
    const original = cp.execFileSync('git', ['show', `${base}:${file}`], { cwd: root, encoding: 'utf8' });
    expect(outsidePricing(fs.readFileSync(path.join(root, file), 'utf8'))).toBe(outsidePricing(original));
  }
  for (const file of ['templates/apex.html', 'app.py', 'db.py', 'llm_policy.py']) {
    const original = cp.execFileSync('git', ['show', `${base}:${file}`], { cwd: root, encoding: 'utf8' });
    expect(fs.readFileSync(path.join(root, file), 'utf8').replace(/\r\n/g, '\n')).toBe(original.replace(/\r\n/g, '\n'));
  }
});
