const { test, expect } = require('@playwright/test');

for (const language of ['bg', 'en']) {
  test(`payment references cannot authenticate an anonymous ${language} browser`, async ({ page }) => {
    await page.goto(`/app?lang=${language}`);
    const result = await page.evaluate(async () => {
      const poll = await fetch('/poll-token?session_id=cs_test_untrusted');
      const refund = await fetch('/withdraw', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: 'cs_test_untrusted', token: 'untrusted' }) });
      const token = await fetch('/verify-token', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token: 'untrusted' }) });
      const identity = await fetch('/auth/me');
      return { poll: poll.status, refund: refund.status,
        token: await token.json(), identity: await identity.json() };
    });
    expect(result.poll).toBe(401);
    expect(result.refund).toBe(401);
    expect(result.token.valid).toBe(false);
    expect(result.identity.authenticated).toBe(false);
    expect(result.identity.plan).toBe('free');
  });
}

test('paid checkout remains disabled while the FREE app is available', async ({ request }) => {
  expect((await request.post('/create-checkout-session', { data: { plan: 'pro' } })).status()).toBe(503);
  for (const route of ['/', '/en', '/app']) {
    expect((await request.get(route)).status()).toBe(200);
  }
});
