import { expect, type Page } from '@playwright/test';

/** Uses the already-open generated library in the serial smoke scenario. */
export async function checkIndexingControls(page: Page) {
  try {
    await page.getByRole('button', { name: /^Info/ }).click();
    const panel = page.getByRole('dialog', { name: 'Info', exact: true });
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
    await page.request.post('/api/indexing', { data: { paused: false, threads: 0 } });
  }
}
