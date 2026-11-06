import { expect, type Page } from '@playwright/test';
import { FIXTURE } from './server';

/** Exercise the workspace against generated files in the existing serial smoke test. */
export async function checkWorkspace(page: Page) {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const sidebar = page.getByRole('complementary', { name: 'Library workspace' });
  await expect(sidebar).toBeVisible();
  await sidebar.getByRole('button', { name: 'Folder trips', exact: true }).click();
  await expect(page.getByRole('button', { name: /^Open / })).toHaveCount(FIXTURE.trips);
  await expect(page.getByRole('heading', { level: 1, name: 'trips', exact: true })).toBeVisible();
  await sidebar.getByRole('button', { name: /^All photos/ }).click();
  await expect(page.getByRole('button', { name: /^Open / })).toHaveCount(FIXTURE.images);
  await page.getByRole('button', { name: 'Select', exact: true }).click();
  const tiles = page.locator('.picture');
  await tiles.first().click();
  await expect(tiles.first()).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('dialog', { name: 'Image viewer' })).toHaveCount(0);
  await page.keyboard.press('Control+a');
  await expect(page.locator('.picture[aria-pressed="true"]')).toHaveCount(FIXTURE.images);
  await page.getByRole('button', { name: 'Clear', exact: true }).click();
  await expect(page.locator('.picture[aria-pressed="true"]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Select loaded', exact: true }).click();
  await page.screenshot({ path: 'test-results/workspace-desktop.png' });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Select', exact: true })).toBeVisible();
  await tiles.first().click();
  await expect(page.getByRole('dialog', { name: 'Image viewer' })).toBeVisible();
  await page.keyboard.press('Escape');
  const controls = sidebar.getByRole('region', { name: 'Workspace indexing controls' });
  await controls.getByRole('button', { name: 'Pause indexing', exact: true }).click();
  await page.getByRole('button', { name: /^Info/ }).click();
  const info = page.getByRole('dialog', { name: 'Info', exact: true });
  await expect(info.getByRole('button', { name: 'Resume indexing', exact: true })).toBeVisible();
  await info.getByRole('button', { name: 'Resume indexing', exact: true }).click();
  await info.getByRole('button', { name: 'Close info', exact: true }).click();
  await expect(controls.getByRole('button', { name: 'Pause indexing', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Switch to dark mode', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Select', exact: true })).toHaveCSS('color', 'rgb(235, 235, 229)');
  await page.screenshot({ path: 'test-results/workspace-dark.png' });
  await page.getByRole('button', { name: 'Switch to light mode', exact: true }).click();
  await page.emulateMedia({ reducedMotion: 'reduce' });
  for (const width of [320, 375, 414, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(sidebar).toBeHidden();
    await page.getByRole('button', { name: 'Library', exact: true }).click();
    await expect(sidebar).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await sidebar.getByRole('button', { name: 'Folder trips', exact: true }).click();
    await expect(sidebar).toBeHidden();
    await expect(page.getByRole('button', { name: /^Open / })).toHaveCount(FIXTURE.trips);
    await page.screenshot({ path: `test-results/workspace-${width}.png` });
    await page.getByRole('button', { name: 'Library', exact: true }).click();
    await sidebar.getByRole('button', { name: /^All photos/ }).click();
    await expect(page.getByRole('button', { name: /^Open / })).toHaveCount(FIXTURE.images);
  }
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.setViewportSize({ width: 1280, height: 720 });
}
