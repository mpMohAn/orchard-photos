import { expect, type Page } from '@playwright/test';

/** Uses the already-open generated library in the serial smoke scenario. */
export async function checkIndexingControls(page: Page) {
  try {
    await page.getByRole('button', { name: /^Info/ }).click();
    const panel = page.getByRole('dialog', { name: 'Info', exact: true });
    // Simulate the login setting. Never modify the Mac's real login configuration.
    let loginEnabled = false;
    await page.route('**/api/login', async route => {
      if (route.request().method() === 'POST') loginEnabled = route.request().postDataJSON().enabled;
      await route.fulfill({ json: { available: true, enabled: loginEnabled } });
    });
    await page.reload();
    await page.getByRole('button', { name: /^Info/ }).click();
    const login = panel.getByRole('checkbox', { name: 'Launch Orchard at login' });
    await expect(login).not.toBeChecked();
    await login.click();
    await expect(login).toBeChecked();
    await page.reload();
    await page.getByRole('button', { name: /^Info/ }).click();
    await expect(login).toBeChecked();
    await login.click();
    await expect(login).not.toBeChecked();
    await panel.getByRole('button', { name: 'Pause indexing', exact: true }).click();
    await expect(panel.getByRole('button', { name: 'Resume indexing', exact: true })).toBeVisible();
    await panel.getByLabel('CPU threads', { exact: true }).selectOption('2');
    await expect(panel.getByRole('region', { name: 'Indexing controls' }).getByRole('status')).toHaveText('CPU thread change saved. Restart Orchard to apply it.');
    await page.reload();
    await page.getByRole('button', { name: /^Info/ }).click();
    await expect(panel.getByRole('button', { name: 'Resume indexing', exact: true })).toBeVisible();
    await expect(panel.getByLabel('CPU threads', { exact: true })).toHaveValue('2');
    await panel.getByRole('button', { name: 'Resume indexing', exact: true }).click();
    await expect(panel.getByRole('button', { name: 'Pause indexing', exact: true })).toBeVisible();
    await panel.getByLabel('CPU threads', { exact: true }).scrollIntoViewIfNeeded();
    await expect(panel.getByLabel('CPU threads', { exact: true })).toBeInViewport();
    await page.screenshot({ path: 'test-results/indexing-controls.png' });
    await panel.getByRole('button', { name: 'Close info', exact: true }).click();
  } finally {
    await page.unroute('**/api/login');
    await page.request.post('/api/indexing', { data: { paused: false, threads: 0 } });
  }
}
