import { test, expect } from './fixtures/test-setup'

test.describe('Work Items', () => {
  test('shows empty state when no items', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}/items`)

    // Should show no items message
    await expect(page.locator('text=No items found')).toBeVisible()
  })

  test('can add new item', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}/items`)

    // Click Add Item
    await page.click('button:has-text("Add Item")')

    // Fill form
    await page.fill('textarea', 'Test item content from E2E')
    await page.fill('input[placeholder*="bug"]', 'test-category')

    // Submit - click the button inside the form
    await page.locator('form button:has-text("Add Item")').click()

    // Item should appear
    await expect(page.locator('text=Test item content from E2E')).toBeVisible()
    // Check status badge shows pending (use more specific selector to avoid option element)
    await expect(page.locator('.card span:has-text("pending")')).toBeVisible()
  })

  test('can expand and collapse item', async ({ page, testProject, request }) => {
    // Create an item first
    await request.post(`/api/projects/${testProject.slug}/items`, {
      data: { content: 'Expandable test item', category: 'test' }
    })

    await page.goto(`/projects/${testProject.slug}/items`)

    // Item should be collapsed (2 line clamp)
    const card = page.locator('.card:has-text("Expandable test item")')
    await expect(card).toBeVisible()

    // Click to expand
    await card.locator('button').first().click()

    // Should show details now
    await expect(card.locator('text=Created:')).toBeVisible()
    await expect(card.locator('text=ID:')).toBeVisible()
  })

  test('can mark item as completed', async ({ page, testProject, request }) => {
    // Create an item
    await request.post(`/api/projects/${testProject.slug}/items`, {
      data: { content: 'Item to complete' }
    })

    await page.goto(`/projects/${testProject.slug}/items`)

    // Expand item
    const card = page.locator('.card:has-text("Item to complete")')
    await card.locator('button').first().click()

    // Click Mark Complete
    await card.locator('button:has-text("Mark Complete")').click()

    // Status should change
    await expect(card.locator('text=completed')).toBeVisible()
  })

  test('can reject item', async ({ page, testProject, request }) => {
    // Create an item
    await request.post(`/api/projects/${testProject.slug}/items`, {
      data: { content: 'Item to reject' }
    })

    await page.goto(`/projects/${testProject.slug}/items`)

    // Expand item
    const card = page.locator('.card:has-text("Item to reject")')
    await card.locator('button').first().click()

    // Click Reject
    await card.locator('button:has-text("Reject")').click()

    // Status should change
    await expect(card.locator('text=rejected')).toBeVisible()
  })

  test('can delete item', async ({ page, testProject, request }) => {
    // Create an item
    await request.post(`/api/projects/${testProject.slug}/items`, {
      data: { content: 'Item to delete' }
    })

    await page.goto(`/projects/${testProject.slug}/items`)

    // Expand item
    const card = page.locator('.card:has-text("Item to delete")')
    await card.locator('button').first().click()

    // Click Delete and confirm
    page.on('dialog', dialog => dialog.accept())
    await card.locator('button:has-text("Delete")').click()

    // Item should be gone
    await expect(page.locator('text=Item to delete')).not.toBeVisible()
  })

  test('can filter by status', async ({ page, testProject, request }) => {
    // Create items with different statuses
    await request.post(`/api/projects/${testProject.slug}/items`, {
      data: { content: 'Pending item' }
    })
    const completedResp = await request.post(`/api/projects/${testProject.slug}/items`, {
      data: { content: 'Completed item' }
    })
    const completedItem = await completedResp.json()
    await request.patch(`/api/projects/${testProject.slug}/items/${completedItem.id}`, {
      data: { status: 'completed' }
    })

    await page.goto(`/projects/${testProject.slug}/items`)

    // Both should be visible initially
    await expect(page.locator('text=Pending item')).toBeVisible()
    await expect(page.locator('text=Completed item')).toBeVisible()

    // Filter to completed only
    await page.selectOption('select:near(:text("Status"))', 'completed')

    // Only completed should be visible
    await expect(page.locator('text=Completed item')).toBeVisible()
    await expect(page.locator('text=Pending item')).not.toBeVisible()
  })
})
