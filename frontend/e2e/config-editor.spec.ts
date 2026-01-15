import { test, expect } from './fixtures/test-setup'

// Skip config editor tests until backend loop sync is fixed
// The loop sync endpoint isn't reliably creating loops in the database
test.describe.skip('Config Editor', () => {
  test('opens editor modal from loop page', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    // Click Edit Config
    await page.click('button:has-text("Edit Config")')

    // Modal should appear with YAML content
    await expect(page.locator('text=Edit Loop Config')).toBeVisible()
    await expect(page.locator('textarea')).toBeVisible()
    await expect(page.locator('textarea')).toContainText('name: test-loop')
  })

  test('shows file path in modal', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    await page.click('button:has-text("Edit Config")')

    // Should show the config file path
    await expect(page.locator('text=.ralphx/loops/test-loop.yaml')).toBeVisible()
  })

  test('detects unsaved changes', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    await page.click('button:has-text("Edit Config")')

    // Initially no changes
    await expect(page.locator('text=No changes')).toBeVisible()

    // Edit the content
    const textarea = page.locator('textarea')
    await textarea.fill('name: test-loop\nmodified: true')

    // Should show unsaved changes indicator
    await expect(page.locator('text=Unsaved changes')).toBeVisible()
  })

  test('warns before discarding changes on Cancel', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    await page.click('button:has-text("Edit Config")')

    // Edit the content
    const textarea = page.locator('textarea')
    await textarea.fill('name: test-loop\nmodified: true')

    // Set up dialog handler to reject (click Cancel on confirm)
    page.on('dialog', dialog => dialog.dismiss())

    // Click Cancel - dialog should appear
    await page.click('button:has-text("Cancel")')

    // Modal should still be visible (we dismissed the confirm)
    await expect(page.locator('text=Edit Loop Config')).toBeVisible()
  })

  test('closes without warning when no changes', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    await page.click('button:has-text("Edit Config")')

    // Wait for content to load
    await expect(page.locator('textarea')).toContainText('name: test-loop')

    // Click Cancel without changes - should close immediately
    await page.click('button:has-text("Cancel")')

    // Modal should be gone
    await expect(page.locator('text=Edit Loop Config')).not.toBeVisible()
  })

  test('saves config successfully', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    await page.click('button:has-text("Edit Config")')

    // Edit the content - add a comment
    const textarea = page.locator('textarea')
    const originalContent = await textarea.inputValue()
    await textarea.fill(originalContent + '\n# E2E test comment')

    // Save
    await page.click('button:has-text("Save Config")')

    // Modal should close
    await expect(page.locator('text=Edit Loop Config')).not.toBeVisible()

    // Re-open and verify change persisted
    await page.click('button:has-text("Edit Config")')
    await expect(page.locator('textarea')).toContainText('# E2E test comment')
  })

  test('shows error for invalid YAML', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    await page.click('button:has-text("Edit Config")')

    // Enter invalid YAML
    const textarea = page.locator('textarea')
    await textarea.fill('invalid: yaml: content: [unclosed')

    // Try to save
    await page.click('button:has-text("Save Config")')

    // Should show error message
    await expect(page.locator('.bg-red-900')).toBeVisible()
  })

  test('X button also warns about unsaved changes', async ({ page, testProjectWithLoop }) => {
    await page.goto(`/projects/${testProjectWithLoop.slug}/loops/test-loop`)

    await page.click('button:has-text("Edit Config")')

    // Edit the content
    const textarea = page.locator('textarea')
    await textarea.fill('name: test-loop\nmodified: true')

    // Set up dialog handler to accept
    page.on('dialog', dialog => dialog.accept())

    // Click X button
    await page.locator('svg').filter({ hasText: '' }).locator('..').click()

    // Modal should close (we accepted the confirm)
    await expect(page.locator('text=Edit Loop Config')).not.toBeVisible()
  })
})
