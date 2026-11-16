import { expect, type Page } from '@playwright/test';
import { writeFileSync } from 'node:fs';

export async function checkExplorePerformance(page: Page) {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    const original = CanvasRenderingContext2D.prototype.drawImage;
    Object.assign(window, { exploreDraws: 0 });
    CanvasRenderingContext2D.prototype.drawImage = function (image: CanvasImageSource, ...coordinates: number[]) {
      (window as unknown as { exploreDraws: number }).exploreDraws++;
      return Reflect.apply(original, this, [image, ...coordinates]);
    };
  });
  await page.reload();
  await expect(page.locator('.picture')).toHaveCount(6);
  const response = await page.request.get('/api/images');
  const { items } = await response.json();
  const thumbnail = await (await page.request.get(`/api/images/${items[0].id}/thumbnail`)).body();
  await page.route('**/api/status', async route => {
    const response = await route.fetch(); const status = await response.json();
    status.library.search = { state: 'ready', indexed: 3000, total: 3000, downloaded: true };
    await route.fulfill({ json: status });
  });
  const points = Array.from({ length: 3000 }, (_, n) => ({ ...items[0], id: n.toString(16).padStart(64, '0'), slot: 0, x: (n % 60) / 30 - 1, y: Math.floor(n / 60) / 25 - 1 }));
  await page.route('**/api/map?*', route => route.fulfill({ json: { points, pending: 0, omitted: 0, sheets: ['test'], layout: { state: 'ready' } } }));
  await page.route('**/api/atlas/*', route => route.fulfill({ body: thumbnail, contentType: 'image/png' }));
  // Hold thumbnail requests until the measurement is complete. No server/model workload is involved.
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/images/*/thumbnail', async route => { await pending; await route.fulfill({ body: thumbnail, contentType: 'image/png' }); });
  await page.reload();
  await page.getByRole('button', { name: 'Visual Explore', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Zoom in', exact: true })).toBeVisible();
  for (let n = 0; n < 5; n++) await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  // Let the immediate camera update settle, then measure two idle windows.
  await page.waitForTimeout(350);
  const read = () => page.evaluate(() => (window as unknown as { exploreDraws: number }).exploreDraws);
  const before = await read();
  await page.waitForTimeout(300);
  const after = await read();
  release();
  expect(before).toBeGreaterThan(0);
  expect(after - before).toBeLessThan(100);
  writeFileSync('test-results/explore-performance.json', JSON.stringify({ generatedPoints: 3000, idleWindowMs: 300, idleDrawCalls: after - before, limitations: 'Synthetic points and held network requests; not a representative library benchmark.' }, null, 2));
  await page.getByRole('button', { name: 'Back to photos', exact: true }).click();
  await expect(page.locator('.picture')).toHaveCount(6);
  await page.unrouteAll({ behavior: 'wait' });
  await page.reload();
}
