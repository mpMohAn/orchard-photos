import { expect, type Page } from '@playwright/test';
import { FIXTURE } from './server';

export async function checkSearches(page: Page) {
  const box = page.getByRole('textbox', { name: 'Search images', exact: true });
  const pictures = page.locator('.picture');
  await box.fill('year:2020 type:png'); await box.press('Enter');
  await expect(pictures).toHaveCount(FIXTURE.trips);
  const tools = page.locator('.search-tools');
  await tools.getByText('Search tools', { exact: true }).click();
  await tools.getByLabel('Saved search name', { exact: true }).fill('Trips in 2020');
  await tools.getByRole('button', { name: 'Save search', exact: true }).click();
  await expect(tools.getByRole('button', { name: 'Trips in 2020', exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/search-tools.png' });
  await tools.getByText('Search tools', { exact: true }).click();
  await page.getByRole('button', { name: 'Clear search', exact: true }).click();
  await expect(pictures).toHaveCount(FIXTURE.images);
  await page.reload();
  await tools.getByText('Search tools', { exact: true }).click();
  await tools.getByRole('button', { name: 'Trips in 2020', exact: true }).click();
  await expect(box).toHaveValue('year:2020 type:png');
  await expect(pictures).toHaveCount(FIXTURE.trips);
  await box.fill('bea');
  await tools.getByText('Search tools', { exact: true }).click();
  await tools.getByRole('button', { name: /beach.png.*filename/ }).click();
  await expect(pictures).toHaveCount(1);
  await expect(box).toHaveValue('name:"beach.png"');
  await tools.getByText('Search tools', { exact: true }).click();
  await tools.getByRole('button', { name: 'Remove saved search Trips in 2020', exact: true }).click();
  await expect(tools.getByRole('button', { name: 'Trips in 2020', exact: true })).toHaveCount(0);
  await tools.getByText('Search tools', { exact: true }).click();
  await page.getByRole('button', { name: 'Clear search', exact: true }).click();
  await expect(pictures).toHaveCount(FIXTURE.images);
}
