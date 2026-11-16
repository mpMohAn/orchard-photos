import { expect, type Page } from '@playwright/test';

/** Real reviews of generated originals; the consequential native move is intercepted. */
export async function checkPhotoActions(page: Page) {
  if (process.platform !== 'darwin') {
    await expect(page.getByRole('button', { name: 'Trash selected', exact: true })).toHaveCount(0);
    await page.route('**/api/folder/reveal', route => route.fulfill({ json: { revealed: true } }));
    await page.getByRole('button', { name: 'Show in Finder', exact: true }).click();
    await page.unroute('**/api/folder/reveal');
    return;
  }
  let confirms = 0;
  await page.route('**/api/trash/confirm', async route => {
    confirms++;
    expect(route.request().postDataJSON().confirmed).toBe(true);
    await route.fulfill({ json: { state: 'complete', moved: 1, files: [], recovery: 'Generated-data simulation; no file was moved.' } });
  });
  await page.getByRole('button', { name: 'Select', exact: true }).click();
  await page.locator('.picture').first().click();
  await page.getByRole('button', { name: 'Trash selected', exact: true }).click();
  const review = page.getByRole('dialog', { name: 'Review photos for Trash', exact: true });
  await expect(review).toBeVisible();
  await expect(review.locator('li')).toHaveCount(1);
  await expect(review.getByRole('button', { name: 'Move to Trash', exact: true })).toBeDisabled();
  await review.getByRole('button', { name: 'Cancel', exact: true }).click();
  expect(confirms).toBe(0);
  await page.getByRole('button', { name: 'Trash selected', exact: true }).click();
  await review.getByRole('checkbox').check();
  await review.getByRole('button', { name: 'Move to Trash', exact: true }).click();
  await expect(review.getByRole('status')).toHaveText('1 files moved. ');
  await review.getByRole('button', { name: 'Done', exact: true }).click();
  await page.getByRole('button', { name: 'Done selecting', exact: true }).click();
  await page.locator('.folder-actions > summary').click();
  await page.getByRole('button', { name: 'Select all photos in this folder', exact: true }).click();
  await expect(review).not.toBeVisible();
  await expect(page.getByRole('region', { name: 'Folder selection' })).toContainText('6 originals selected');
  await page.getByRole('button', { name: 'Move selected to Trash', exact: true }).click();
  await expect(review.locator('li')).toHaveCount(6);
  await review.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.unroute('**/api/trash/confirm');
  await page.route('**/api/folder/reveal', route => route.fulfill({ json: { revealed: true } }));
  await page.getByRole('button', { name: 'Show in Finder', exact: true }).click();
  await page.unroute('**/api/folder/reveal');
  await expect(page.locator('.picture')).toHaveCount(6);
}
