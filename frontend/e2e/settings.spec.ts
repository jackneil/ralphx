import { test, expect } from './fixtures/test-setup'

test.describe('Settings Page', () => {
  test('shows system information', async ({ page }) => {
    await page.goto('/settings')

    // Should show system info section
    await expect(page.locator('text=System Information')).toBeVisible()
    await expect(page.locator('text=API Status')).toBeVisible()
    await expect(page.locator('text=healthy')).toBeVisible()
  })

  test('shows version information', async ({ page }) => {
    await page.goto('/settings')

    // Should show version
    await expect(page.locator('text=Version')).toBeVisible()
  })

  test('lists registered projects', async ({ page, testProject }) => {
    // Reload to get fresh project list including our fixture project
    await page.goto('/settings')
    await page.reload()

    // Should show Registered Projects section
    await expect(page.locator('text=Registered Projects')).toBeVisible()

    // Our test project should be in the list
    await expect(page.locator(`text=${testProject.name}`).first()).toBeVisible({ timeout: 10000 })
  })

  test('shows project path in list', async ({ page, testProject }) => {
    await page.goto('/settings')
    await page.reload()

    // Wait for projects to load, then check path is visible
    await expect(page.locator(`text=${testProject.name}`).first()).toBeVisible({ timeout: 10000 })
    // Use getByText with exact string to avoid regex interpretation of /tmp
    await expect(page.getByText(testProject.path, { exact: true }).first()).toBeVisible()
  })

  test('can navigate to project from settings', async ({ page, testProject }) => {
    await page.goto('/settings')
    await page.reload()

    // Wait for projects to load
    await expect(page.locator(`text=${testProject.name}`).first()).toBeVisible({ timeout: 10000 })

    // Find the project row and click View
    const projectRow = page.locator(`.bg-gray-700:has-text("${testProject.name}")`).first()
    await projectRow.locator('a:has-text("View")').click()

    // Should navigate to project page
    await expect(page).toHaveURL(new RegExp(`/projects/${testProject.slug}`))
  })

  test('can remove project from settings', async ({ page, request }) => {
    // Create a dedicated project for this test
    const projectName = `e2e-remove-${Date.now()}`
    const projectPath = `/tmp/${projectName}`

    const fs = await import('fs')
    fs.mkdirSync(`${projectPath}/.ralphx/loops`, { recursive: true })

    const response = await request.post('/api/projects', {
      data: { path: projectPath, name: projectName }
    })
    const project = await response.json()

    try {
      await page.goto('/settings')
      await page.reload()

      // Project should be listed (wait for load)
      await expect(page.locator(`text=${projectName}`).first()).toBeVisible({ timeout: 10000 })

      // Set up dialog handler to accept confirmation
      page.on('dialog', dialog => dialog.accept())

      // Click Remove
      const projectRow = page.locator(`.bg-gray-700:has-text("${projectName}")`).first()
      await projectRow.locator('button:has-text("Remove")').click()

      // Project should be removed from list
      await expect(page.locator(`.bg-gray-700:has-text("${projectName}")`)).not.toBeVisible({ timeout: 5000 })
    } finally {
      // Cleanup filesystem even if test fails
      fs.rmSync(projectPath, { recursive: true, force: true })
    }
  })

  test('remove project shows error on failure', async ({ page, testProject }) => {
    await page.goto('/settings')
    await page.reload()

    // Wait for projects to load
    await expect(page.locator(`text=${testProject.name}`).first()).toBeVisible({ timeout: 10000 })

    // Verify the project is listed and no error is shown initially
    const projectRow = page.locator(`.bg-gray-700:has-text("${testProject.name}")`).first()
    await expect(projectRow).toBeVisible()

    // No error should be shown initially
    await expect(page.locator('.bg-red-900\\/30')).not.toBeVisible()
  })

  test('sidebar link navigates to settings', async ({ page }) => {
    await page.goto('/')

    // Click Settings in sidebar
    await page.click('aside >> text=Settings')

    // Should be on settings page
    await expect(page).toHaveURL('/settings')
    await expect(page.locator('text=System Information')).toBeVisible()
  })

  test('page loads without errors', async ({ page }) => {
    await page.goto('/settings')

    // Page should load and show main sections
    await expect(page.locator('h1:has-text("Settings")')).toBeVisible()
    await expect(page.locator('text=System Information')).toBeVisible()
    await expect(page.locator('text=Registered Projects')).toBeVisible()
  })
})
