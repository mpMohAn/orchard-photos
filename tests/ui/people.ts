import { expect, type Page, type Route } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { PYTHON } from './server';

/** Exercise real People actions using synthetic faces in the generated test catalog. */
export async function checkPeople(page: Page) {
  const status = await (await page.request.get('/api/status')).json();
  const pictures = (await (await page.request.get('/api/images')).json()).items;
  const directory = join(dirname(process.env.ORCHARD_UI_PHOTOS!), 'data', 'libraries', status.folder.id);
  execFileSync(PYTHON, ['-c', `
import json, sqlite3, sys
from pathlib import Path
ids = json.loads(sys.argv[2])
db = sqlite3.connect(Path(sys.argv[1]) / 'library.sqlite')
with db:
    for table in ('faces', 'people', 'faces_processed'):
        db.execute('DELETE FROM ' + table)
    for person, name in [('a', ''), ('b', 'Zoe'), ('c', 'Amy')]:
        db.execute('INSERT INTO people(id,name) VALUES (?,?)', (person * 16, name))
    for index, person in enumerate(['a', 'a', 'b', 'c']):
        db.execute('INSERT INTO faces VALUES (?,?,?,?,?,?,0)', (str(index + 1) * 24, ids[index], person * 16, '[0,0,1,1]', bytes(512), b'crop'))
    db.executemany('INSERT INTO faces_processed VALUES (?)', [(value,) for value in ids])
db.close()
`, directory, JSON.stringify(pictures.map((picture: { id: string }) => picture.id))]);
  const portrait = '<svg xmlns="http://www.w3.org/2000/svg" width="112" height="112"><rect width="112" height="112" fill="#dce8fb"/><circle cx="56" cy="42" r="22" fill="#8094b3"/><ellipse cx="56" cy="102" rx="40" ry="35" fill="#8094b3"/></svg>';
  await page.route('**/api/people/face/*', route => route.fulfill({ body: portrait, contentType: 'image/svg+xml' }));
  await page.getByRole('button', { name: 'People', exact: true }).click();
  const view = page.getByRole('region', { name: 'People', exact: true });
  await expect(view.getByRole('button', { name: 'Enable People', exact: true })).toBeDisabled();
  await view.getByRole('checkbox').check();
  await view.getByRole('button', { name: 'Enable People', exact: true }).click();
  await expect(page.locator('.people-grid .person-card strong')).toHaveText(['Amy', 'Zoe', 'Add a name']);
  await page.screenshot({ path: 'test-results/people-grid.png' });
  await view.getByRole('button', { name: 'Pause', exact: true }).click();
  await view.getByRole('button', { name: 'Resume', exact: true }).click();
  await page.locator('.people-grid .person-card').filter({ hasText: 'Add a name' }).click();
  await page.locator('.face-corrections summary').click();
  await view.getByRole('button', { name: 'Name or match person', exact: true }).first().click();
  const picker = page.getByRole('dialog', { name: 'Name or match person', exact: true });
  await expect(picker.locator('.person-card strong')).toHaveText(['Amy', 'Zoe', 'Unnamed person']);
  await expect(picker.locator('.person-card').last()).toHaveAttribute('aria-pressed', 'true');
  await expect(picker.getByLabel('Apply to all 2 photos in this group')).toBeChecked();
  const staleStatus = await (await page.request.get('/api/people')).json();
  let releasePoll!: () => void;
  let pollDelivered!: () => void;
  const deliveredPoll = new Promise<void>(resolve => { pollDelivered = resolve; });
  let pollHeld = false;
  const pendingPoll = new Promise<void>(resolve => { releasePoll = resolve; });
  const holdPoll = async (route: Route) => {
    if (route.request().method() === 'GET' && !pollHeld) {
      pollHeld = true;
      await pendingPoll;
      await route.fulfill({ json: staleStatus });
      pollDelivered();
    } else await route.continue();
  };
  await page.route('**/api/people', holdPoll);
  await expect.poll(() => pollHeld).toBe(true);
  await picker.getByLabel('Or create a person').fill('Mom');
  await picker.getByRole('button', { name: 'Save person', exact: true }).click();
  await expect(picker).not.toBeVisible();
  await expect(view.getByRole('heading', { level: 1 })).toHaveText('Mom');
  await expect(page.locator('.face-assignment')).toHaveText(['Mom', 'Mom']);
  releasePoll();
  await deliveredPoll;
  await page.unroute('**/api/people', holdPoll);
  await page.waitForTimeout(100);
  await expect(view.getByRole('heading', { level: 1 })).toHaveText('Mom');
  await view.getByRole('button', { name: 'Change person', exact: true }).first().click();
  await expect(picker.locator('.person-card strong')).toHaveText(['Amy', 'Mom', 'Zoe']);
  await expect(picker.getByRole('button', { name: /Mom/ })).toHaveAttribute('aria-pressed', 'true');
  await expect(picker.getByText('Current person', { exact: true })).toBeVisible();
  await expect(picker.getByLabel('Apply to all 2 photos in this group')).not.toBeChecked();
  await page.screenshot({ path: 'test-results/people-person-picker.png' });
  await picker.getByRole('button', { name: /Amy/ }).click();
  await expect(picker).not.toBeVisible();
  await expect(view.getByRole('heading', { level: 1 })).toHaveText('Amy');
  await expect(page.locator('.face-assignment')).toHaveText(['Amy', 'Amy']);
  await view.getByRole('button', { name: 'People', exact: true }).click();
  await page.locator('.people-grid .person-card').filter({ hasText: 'Zoe' }).click();
  await view.getByLabel('Name', { exact: true }).fill(' mom ');
  await view.getByRole('button', { name: 'Save name', exact: true }).click();
  await expect(view.getByRole('heading', { level: 1 })).toHaveText('Mom');
  await expect(page.locator('.picture')).toHaveCount(2);
  await page.locator('.face-corrections summary').click();
  await expect(page.locator('.face-assignment')).toHaveText(['Mom', 'Mom']);
  await view.getByRole('button', { name: 'Same person? Merge groups', exact: true }).click();
  const merge = page.getByRole('dialog', { name: 'Merge person groups' });
  await expect(merge.locator('.person-card strong')).toHaveText(['Amy']);
  await merge.getByRole('button', { name: 'Close', exact: true }).click();
  await page.screenshot({ path: 'test-results/people-detail.png' });
  for (const width of [320, 375, 414, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width === 375) await page.screenshot({ path: 'test-results/people-mobile.png' });
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.locator('.people-settings summary').click();
  await view.getByLabel('Clear this library’s face data.').check();
  await view.getByRole('button', { name: 'Clear face data', exact: true }).click();
  await expect(view.getByRole('button', { name: 'Enable People', exact: true })).toBeVisible();
  await page.getByRole('button', { name: /^All photos/ }).click();
  await page.unrouteAll({ behavior: 'wait' });
  await expect(page.locator('.picture')).toHaveCount(6);
}
