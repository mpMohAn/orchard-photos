import { expect, type Page } from '@playwright/test';

/** Exercise the People UI with simulated groups, without processing personal photos or downloading models. */
export async function checkPeople(page: Page) {
  const groups = [{ id: 'a'.repeat(16), name: '', photos: 2, cover: '1'.repeat(24) }, { id: 'b'.repeat(16), name: 'Family', photos: 1, cover: '2'.repeat(24) }];
  let enabled = false;
  let paused = false;
  let assigned: { person?: string; name?: string } | undefined;
  const response = await page.request.get('/api/images');
  const pictures = (await response.json()).items;
  const portrait = '<svg xmlns="http://www.w3.org/2000/svg" width="112" height="112"><rect width="112" height="112" fill="#dce8fb"/><circle cx="56" cy="42" r="22" fill="#8094b3"/><ellipse cx="56" cy="102" rx="40" ry="35" fill="#8094b3"/></svg>';
  await page.route('**/api/people/face/*', route => route.fulfill({ body: portrait, contentType: 'image/svg+xml' }));
  await page.route('**/api/people/members?*', route => route.fulfill({ json: [{ id: '1'.repeat(24), image_id: pictures[0].id, box: '[0,0,1,1]' }] }));
  await page.route('**/api/images?person=*', route => route.fulfill({ json: { items: pictures.slice(0, 2), total: 2, offset: 0, hasMore: false } }));
  await page.route('**/api/people', async route => {
    if (route.request().method() === 'POST') {
      const values = route.request().postDataJSON();
      if (values.action === 'enable') { expect(values.consent).toBe(true); enabled = true; }
      if (values.action === 'pause') paused = true;
      if (values.action === 'resume') paused = false;
      if (values.action === 'name') groups[0].name = values.name;
      if (values.action === 'assign') assigned = values;
      if (values.action === 'merge') groups.splice(0, 1);
      if (values.action === 'clear') { expect(values.confirmed).toBe(true); enabled = false; groups.splice(0); }
    }
    await route.fulfill({ json: { enabled, paused, state: 'ready', error: '', processed: enabled ? 6 : 0, total: 6, people: enabled ? groups : [] } });
  });
  await page.getByRole('button', { name: 'People', exact: true }).click();
  const pageView = page.getByRole('region', { name: 'People', exact: true });
  await expect(pageView.getByRole('button', { name: 'Enable People', exact: true })).toBeDisabled();
  await page.screenshot({ path: 'test-results/people-setup.png' });
  await pageView.getByRole('checkbox').check();
  await pageView.getByRole('button', { name: 'Enable People', exact: true }).click();
  await expect(page.locator('.person-card')).toHaveCount(2);
  await expect.poll(() => page.locator('.person-card img').evaluateAll(images => images.every(image => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0))).toBe(true);
  await page.screenshot({ path: 'test-results/people-grid.png' });
  await pageView.getByRole('button', { name: 'Pause', exact: true }).click();
  await pageView.getByRole('button', { name: 'Resume', exact: true }).click();
  await page.locator('.person-card').first().click();
  await pageView.getByLabel('Name', { exact: true }).fill('Mohan');
  await pageView.getByRole('button', { name: 'Save name', exact: true }).click();
  await expect(pageView.getByRole('heading', { level: 1 })).toHaveText('Mohan');
  await page.locator('.face-corrections summary').click();
  await expect(pageView.getByRole('button', { name: 'Separate face', exact: true })).toBeVisible();
  await pageView.getByRole('button', { name: 'Name or match person', exact: true }).click();
  const picker = page.getByRole('dialog', { name: 'Name or match person', exact: true });
  await expect(picker.getByRole('button', { name: /Family/ })).toBeVisible();
  await expect(picker.getByLabel('Or create a person')).toBeVisible();
  await page.screenshot({ path: 'test-results/people-person-picker.png' });
  await picker.getByRole('button', { name: /Family/ }).click();
  await expect(picker).not.toBeVisible();
  expect(assigned?.person).toBe('b'.repeat(16));
  await pageView.getByRole('button', { name: 'Name or match person', exact: true }).click();
  await picker.getByLabel('Or create a person').fill('New person');
  await picker.getByRole('button', { name: 'Save person', exact: true }).click();
  await expect(picker).not.toBeVisible();
  expect(assigned?.name).toBe('New person');
  await pageView.getByRole('button', { name: 'Same person? Merge groups', exact: true }).click();
  const merge = page.getByRole('dialog', { name: 'Merge person groups' });
  await expect(merge.getByRole('button', { name: /Family/ })).toBeVisible();
  await merge.getByRole('button', { name: 'Close', exact: true }).click();
  await page.screenshot({ path: 'test-results/people-detail.png' });
  for (const width of [320, 375, 414, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width === 375) await page.screenshot({ path: 'test-results/people-mobile.png' });
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByRole('button', { name: /^All photos/ }).click();
  await page.unrouteAll({ behavior: 'wait' });
  await expect(page.locator('.picture')).toHaveCount(6);
}
