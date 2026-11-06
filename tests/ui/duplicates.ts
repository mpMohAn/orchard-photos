import { copyFileSync, existsSync, readFileSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { expect, type Page } from '@playwright/test';

/** Generated fixture only. Native Trash is intercepted for this browser interaction test. */
export async function checkDuplicates(page: Page) {
  const copy = join(process.env.ORCHARD_UI_PHOTOS!, 'red-review-copy.png');
  const original = join(process.env.ORCHARD_UI_PHOTOS!, 'red.png');
  copyFileSync(original, copy);
  let trashRequests = 0;
  await page.route('**/api/duplicates?*', async route => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, trashAvailable: true } });
  });
  await page.route('**/api/duplicates/plan', async route => {
    const body = route.request().postDataJSON();
    const files = body.paths.map((path: string) => ({ id: body.group, path, original: join(process.env.ORCHARD_UI_PHOTOS!, path), size: readFileSync(copy).length }));
    await route.fulfill({ json: { token: 'browser-simulated-plan', files, kept: [{ path: 'red.png', original, size: readFileSync(original).length }], bytes: files[0].size } });
  });
  await page.route('**/api/duplicates/trash', async route => {
    trashRequests++;
    expect(route.request().postDataJSON()).toEqual({ token: 'browser-simulated-plan', confirmed: true });
    await route.fulfill({ json: { token: 'browser-simulated-plan', state: 'complete', moved: 1,
      files: [{ id: '', path: 'red-review-copy.png', original: copy, state: 'moved' }], recovery: 'Simulated browser operation. Generated files remain in their fixture.' } });
  });
  try {
    await page.request.post('/api/scan', { data: {} });
    await expect.poll(async () => {
      const status = await (await page.request.get('/api/status')).json();
      if (status.library.scan.state === 'error') throw new Error(JSON.stringify(status.library));
      return status.library.counts;
    }).toMatchObject({ duplicates: 1, files: 7, images: 6 });
    await page.getByRole('button', { name: 'Duplicates', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Duplicate review', exact: true });
    await expect(dialog.getByRole('heading', { name: 'Identical file contents', exact: true })).toBeVisible();
    const comparison = dialog.getByRole('region', { name: 'Side-by-side comparison' });
    await expect(comparison.locator('img')).toHaveCount(2);
    await expect(dialog.getByRole('button', { name: 'Review selected files', exact: true })).toBeDisabled();
    await dialog.getByRole('checkbox', { name: 'Move red-review-copy.png to Trash', exact: true }).check();
    await dialog.getByRole('checkbox', { name: 'Move red.png to Trash', exact: true }).check();
    await expect(dialog.getByRole('button', { name: 'Review selected files', exact: true })).toBeDisabled();
    await dialog.getByRole('checkbox', { name: 'Move red.png to Trash', exact: true }).uncheck();
    await dialog.getByRole('button', { name: 'Review selected files', exact: true }).click();
    const confirm = dialog.getByRole('region', { name: 'Confirm Trash move', exact: true });
    await expect(confirm.getByRole('button', { name: 'Confirm move to Trash', exact: true })).toBeDisabled();
    await expect(confirm.getByText(copy, { exact: true })).toBeVisible();
    await confirm.getByRole('button', { name: 'Cancel review', exact: true }).click();
    expect(trashRequests).toBe(0);
    await dialog.getByRole('button', { name: 'Similar photos', exact: true }).click();
    await expect(dialog.getByRole('heading', { name: 'No similar groups', exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: 'Exact copies', exact: true }).click();
    await dialog.getByRole('checkbox', { name: 'Move red-review-copy.png to Trash', exact: true }).check();
    await page.screenshot({ path: 'test-results/duplicates-desktop.png' });
    await dialog.getByRole('button', { name: 'Review selected files', exact: true }).click();
    await confirm.getByRole('checkbox', { name: 'I reviewed these files and want to move them to Trash', exact: true }).check();
    await confirm.getByRole('button', { name: 'Confirm move to Trash', exact: true }).click();
    await expect(dialog.getByRole('status', { name: 'Trash operation result' })).toContainText('1 file moved to Trash.');
    expect(trashRequests).toBe(1);
    expect(readFileSync(copy).equals(readFileSync(original))).toBe(true);
    await page.setViewportSize({ width: 375, height: 900 });
    expect(await dialog.evaluate(node => node.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: 'test-results/duplicates-mobile.png' });
    await dialog.getByRole('button', { name: 'Close duplicate review', exact: true }).click();
    await expect(dialog).toBeHidden();
  } finally {
    await page.unroute('**/api/duplicates?*');
    await page.unroute('**/api/duplicates/plan');
    await page.unroute('**/api/duplicates/trash');
    if (existsSync(copy)) unlinkSync(copy);
    await page.request.post('/api/scan', { data: {} });
    await page.setViewportSize({ width: 1280, height: 720 });
  }
}
