import { test, expect } from './fixtures/test-setup'

test.describe('Resources Management', () => {
  test('resources section is visible by default on project page', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)

    // Wait for page to load
    await page.waitForLoadState('networkidle')

    // Resources section should be visible without clicking "Show"
    await expect(page.locator('h2:has-text("Project Resources")')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add Resource' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Import from Project' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sync from Files' })).toBeVisible()
  })

  test('can create a resource manually via Add Resource button', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Click Add Resource button
    await page.getByRole('button', { name: 'Add Resource' }).click()

    // Modal should appear
    await expect(page.locator('h3:has-text("Create Resource")')).toBeVisible()

    // Fill in the form
    await page.fill('input[placeholder*="main"]', 'test-resource')
    await page.selectOption('select', 'custom')
    await page.fill('textarea', '# Test Resource\n\nThis is test content created via the UI.')

    // Click Create button in the modal
    await page.locator('.fixed button:has-text("Create")').click()

    // Wait for modal to close and resource to appear
    await expect(page.locator('h3:has-text("Create Resource")')).not.toBeVisible({ timeout: 10000 })
    await expect(page.locator('button:has-text("test-resource")')).toBeVisible({ timeout: 5000 })
  })

  test('can open file browser via Import from Project button', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Click Import from Project
    await page.getByRole('button', { name: 'Import from Project' }).click()

    // File browser modal should appear
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()
    await expect(page.locator('text=/ (project root)')).toBeVisible()
    await expect(page.locator('text=Files & Folders')).toBeVisible()
    await expect(page.getByText('Preview', { exact: true })).toBeVisible()
  })

  test('file browser shows files created in test fixture', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Open file browser
    await page.getByRole('button', { name: 'Import from Project' }).click()
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()

    // Wait for file list to load
    await page.waitForTimeout(500)

    // Should see the README.md file we created in the fixture
    await expect(page.locator('.fixed button:has-text("README.md")')).toBeVisible({ timeout: 5000 })

    // Should see the docs directory
    await expect(page.locator('.fixed button:has-text("docs")')).toBeVisible()

    // Should see the main.py file
    await expect(page.locator('.fixed button:has-text("main.py")')).toBeVisible()
  })

  test('can navigate into directories in file browser', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Open file browser
    await page.getByRole('button', { name: 'Import from Project' }).click()
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()
    await page.waitForTimeout(500)

    // Click on docs directory
    await page.locator('.fixed button:has-text("docs")').click()

    // Should now show design.md inside docs
    await expect(page.locator('.fixed button:has-text("design.md")')).toBeVisible({ timeout: 5000 })

    // Should be able to go back up
    await expect(page.locator('.fixed button:has-text("..")')).toBeVisible()
  })

  test('can preview a file by clicking on it', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Open file browser
    await page.getByRole('button', { name: 'Import from Project' }).click()
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()
    await page.waitForTimeout(500)

    // Click on README.md to select it
    await page.locator('.fixed button:has-text("README.md")').click()

    // Preview pane should show the content (wait for file to load)
    await expect(page.locator('pre:has-text("# Test Project")')).toBeVisible({ timeout: 5000 })

    // Add as Resource button should be enabled
    await expect(page.getByRole('button', { name: 'Add as Resource' })).toBeEnabled()
  })

  test('can import file as resource via file browser', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Open file browser
    await page.getByRole('button', { name: 'Import from Project' }).click()
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()
    await page.waitForTimeout(500)

    // Navigate to docs and select design.md
    await page.locator('.fixed button:has-text("docs")').click()
    await expect(page.locator('.fixed button:has-text("design.md")')).toBeVisible({ timeout: 5000 })
    await page.locator('.fixed button:has-text("design.md")').click()

    // Verify preview shows content
    await expect(page.locator('pre:has-text("# Design Document")')).toBeVisible({ timeout: 5000 })

    // Click Add as Resource
    await page.getByRole('button', { name: 'Add as Resource' }).click()

    // Create resource dialog should open with pre-filled content
    await expect(page.locator('h3:has-text("Create Resource")')).toBeVisible()

    // Name should be pre-filled (design without extension)
    const nameInput = page.locator('input[placeholder*="main"]')
    await expect(nameInput).toHaveValue('design')

    // Content should be pre-filled
    const textarea = page.locator('textarea')
    await expect(textarea).toContainText('# Design Document')

    // Click Create in the modal
    await page.locator('.fixed button:has-text("Create")').click()

    // Wait for modal to close
    await expect(page.locator('h3:has-text("Create Resource")')).not.toBeVisible({ timeout: 10000 })

    // Resource should appear in the list
    await expect(page.locator('button:has-text("design")')).toBeVisible({ timeout: 5000 })
  })

  test('can close file browser with Cancel', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)

    // Open file browser
    await page.click('button:has-text("Import from Project")')
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()

    // Click Cancel
    await page.click('button:has-text("Cancel")')

    // Modal should close
    await expect(page.locator('h3:has-text("Import File from Project")')).not.toBeVisible()
  })

  test('can close file browser with X button', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)

    // Open file browser
    await page.click('button:has-text("Import from Project")')
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()

    // Click X button (aria-label="Close")
    await page.click('[aria-label="Close"]')

    // Modal should close
    await expect(page.locator('h3:has-text("Import File from Project")')).not.toBeVisible()
  })

  test('can toggle resource enabled status', async ({ page, testProject }) => {
    // First create a resource via the UI
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Add Resource' }).click()
    await page.fill('input[placeholder*="main"]', 'toggle-test')
    await page.selectOption('select', 'custom')
    await page.fill('textarea', '# Toggle Test')
    await page.locator('.fixed button:has-text("Create")').click()
    await expect(page.locator('h3:has-text("Create Resource")')).not.toBeVisible({ timeout: 10000 })

    // Wait for resource to appear
    await expect(page.locator('button:has-text("toggle-test")')).toBeVisible({ timeout: 5000 })

    // Find the resource row and its toggle button (first button in row)
    const resourceSection = page.locator('.bg-gray-800\\/50').filter({ hasText: 'toggle-test' })
    const toggleButton = resourceSection.locator('button').first()
    await toggleButton.click()

    // Verify the change persisted by reloading
    await page.reload()
    await page.waitForLoadState('networkidle')
    await expect(page.locator('button:has-text("toggle-test")')).toBeVisible()
  })

  test('can delete a resource', async ({ page, testProject }) => {
    // First create a resource via the UI
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Add Resource' }).click()
    await page.fill('input[placeholder*="main"]', 'delete-test')
    await page.selectOption('select', 'custom')
    await page.fill('textarea', '# Delete Test')
    await page.locator('.fixed button:has-text("Create")').click()
    await expect(page.locator('h3:has-text("Create Resource")')).not.toBeVisible({ timeout: 10000 })

    // Wait for resource to appear
    await expect(page.locator('button:has-text("delete-test")')).toBeVisible({ timeout: 5000 })

    // Handle the confirmation dialog
    page.on('dialog', dialog => dialog.accept())

    // Find and click the delete button for this resource
    const resourceRow = page.locator('.flex.items-center.justify-between').filter({ hasText: 'delete-test' })
    await resourceRow.getByRole('button', { name: 'Delete', exact: true }).click()

    // Resource should be removed
    await expect(page.locator('button:has-text("delete-test")')).not.toBeVisible({ timeout: 5000 })
  })

  test('can edit a resource', async ({ page, testProject }) => {
    // First create a resource via the UI
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    await page.getByRole('button', { name: 'Add Resource' }).click()
    await page.fill('input[placeholder*="main"]', 'edit-test')
    await page.selectOption('select', 'custom')
    await page.fill('textarea', '# Original Content')
    await page.locator('.fixed button:has-text("Create")').click()
    await expect(page.locator('h3:has-text("Create Resource")')).not.toBeVisible({ timeout: 10000 })

    // Wait for resource to appear
    await expect(page.locator('button:has-text("edit-test")')).toBeVisible({ timeout: 5000 })

    // Find and click the Edit button for this resource
    const resourceRow = page.locator('.flex.items-center.justify-between').filter({ hasText: 'edit-test' })
    await resourceRow.getByRole('button', { name: 'Edit', exact: true }).click()

    // Edit dialog should open
    await expect(page.locator('h3:has-text("Edit:")')).toBeVisible()

    // Modify content
    const textarea = page.locator('.fixed textarea')
    await textarea.fill('# Updated Content\n\nThis has been edited.')

    // Save
    await page.locator('.fixed button:has-text("Save")').click()

    // Dialog should close
    await expect(page.locator('h3:has-text("Edit:")')).not.toBeVisible({ timeout: 5000 })
  })

  test('can sync resources from filesystem', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Click Sync from Files
    await page.getByRole('button', { name: 'Sync from Files' }).click()

    // Button text might change while syncing, then show result
    // Wait a bit for the sync to complete
    await page.waitForTimeout(1000)

    // Should show sync result (even if 0 changes) - text format is "Synced: X added, Y updated, Z removed"
    await expect(page.locator('text=/Synced:.*added.*updated.*removed/')).toBeVisible({ timeout: 5000 })
  })

  test('shows filtered file count when hidden items exist', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)
    await page.waitForLoadState('networkidle')

    // Open file browser
    await page.getByRole('button', { name: 'Import from Project' }).click()
    await expect(page.locator('h3:has-text("Import File from Project")')).toBeVisible()
    await page.waitForTimeout(500)

    // Should show filtering info since .ralphx is hidden
    // The count appears at the bottom of the file list
    await expect(page.locator('text=/\\d+ hidden/')).toBeVisible({ timeout: 5000 })
  })

  test('resource type dropdown has all options', async ({ page, testProject }) => {
    await page.goto(`/projects/${testProject.slug}`)

    // Open create dialog
    await page.click('button:has-text("Add Resource")')

    // Check dropdown has all resource types
    const select = page.locator('select')
    await expect(select.locator('option:has-text("Design Document")')).toBeAttached()
    await expect(select.locator('option:has-text("Architecture")')).toBeAttached()
    await expect(select.locator('option:has-text("Coding Standards")')).toBeAttached()
    await expect(select.locator('option:has-text("Domain Knowledge")')).toBeAttached()
    await expect(select.locator('option:has-text("Custom")')).toBeAttached()
  })
})
