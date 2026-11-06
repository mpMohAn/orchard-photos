import { writeFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('large library stays virtualized and responds while scrolling', async ({ page }) => {
  test.skip(process.env.ORCHARD_UI_LARGE !== '1', 'Opt-in generated 10,000-image workload');
  test.setTimeout(180000);
  await page.goto('/');
  await page.getByRole('checkbox', { name: /Set up visual search too/ }).uncheck();
  await page.getByPlaceholder('~/Pictures').fill(process.env.ORCHARD_UI_PHOTOS!);
  const opened = performance.now();
  await page.getByRole('button', { name: 'Open', exact: true }).click();
  await expect(page.getByRole('button', { name: /^Open / }).first()).toBeVisible({ timeout: 120000 });
  const firstImageMs = performance.now() - opened;
  await expect.poll(async () => {
    const response = await page.request.get('/api/status');
    const status = await response.json();
    return status.library?.scan.state === 'ready' && status.library?.counts.images;
  }, { timeout: 120000 }).toBe(10000);
  await expect(page.locator('.library-meta > p')).toHaveText('10,000 images', { timeout: 10000 });
  const frames = await page.evaluate(async () => {
    const gaps: number[] = [];
    let previous = performance.now();
    for (let i = 0; i < 120; i++) {
      window.scrollBy(0, 100);
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      const now = performance.now(); gaps.push(now - previous); previous = now;
    }
    const sorted = [...gaps].sort((a, b) => a - b);
    return { samples: gaps.length, medianMs: sorted[60], p95Ms: sorted[114], maxMs: sorted.at(-1), over50ms: gaps.filter(n => n > 50).length };
  });
  const mounted = await page.locator('.picture').count();
  expect(mounted).toBeGreaterThan(0);
  expect(mounted).toBeLessThan(250);
  await page.getByRole('button', { name: /^Open / }).first().click();
  await expect(page.getByRole('dialog', { name: 'Image viewer' })).toBeVisible();
  await page.keyboard.press('Escape');
  const report = { generatedImages: 10000, fixturePixels: [48, 48], firstImageMs, frames, mountedTilesAfterScroll: mounted,
    viewerOpenedAfterScroll: true, limitations: ['Tiny generated PNGs; not personal-library acceptance.',
      'Headless Chromium animation-frame intervals, not physical display FPS.', 'No model inference in this UI workload.'] };
  writeFileSync(process.env.ORCHARD_UI_REPORT || 'test-results/large-library-metrics.json', JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report));
});
