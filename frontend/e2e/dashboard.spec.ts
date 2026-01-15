import { test, expect } from './fixtures/test-setup'

test.describe('Dashboard', () => {
  test('shows API health status', async ({ page }) => {
    await page.goto('/')

    // Should show healthy status
    await expect(page.locator('text=healthy')).toBeVisible()
  })

  test('shows Add Project button', async ({ page }) => {
    await page.goto('/')

    // Should have Add Project button
    await expect(page.locator('button:has-text("Add Project")')).toBeVisible()
  })

  test('opens Add Project dialog', async ({ page }) => {
    await page.goto('/')

    // Click Add Project
    await page.click('button:has-text("Add Project")')

    // Dialog should appear with path input
    await expect(page.locator('text=Add Project').first()).toBeVisible()
    await expect(page.locator('input[placeholder*="path"]')).toBeVisible()
  })

  test('can add project via dialog', async ({ page, request }) => {
    // Create temp directory for test
    const projectName = `e2e-add-${Date.now()}`
    const projectPath = `/tmp/${projectName}`

    // Create directory via API (simulating filesystem)
    const fs = await import('fs')
    fs.mkdirSync(`${projectPath}/.ralphx/loops`, { recursive: true })

    try {
      await page.goto('/')

      // Open dialog
      await page.click('button:has-text("Add Project")')

      // Fill form - path placeholder is "/home/user/my-project", name is "Auto-generated from path"
      await page.fill('input[placeholder*="my-project"]', projectPath)
      await page.fill('input[placeholder*="Auto-generated"]', projectName)

      // Submit - click the Add Project button inside the form (not the header button)
      await page.locator('form button:has-text("Add Project")').click()

      // Wait for dialog to close and project to appear (use heading to be specific)
      await expect(page.locator(`h3:has-text("${projectName}")`)).toBeVisible({ timeout: 5000 })

      // Should appear in sidebar too (use the name div in sidebar)
      await expect(page.locator(`aside .font-medium:has-text("${projectName}")`)).toBeVisible()
    } finally {
      // Cleanup
      await request.delete(`/api/projects/${projectName.toLowerCase()}`)
      fs.rmSync(projectPath, { recursive: true, force: true })
    }
  })

  test('navigates to project on click', async ({ page, testProject }) => {
    await page.goto('/')

    // Click project card
    await page.click(`text=${testProject.name}`)

    // Should navigate to project detail
    await expect(page).toHaveURL(new RegExp(`/projects/${testProject.slug}`))
  })

  test('displays project count in stats', async ({ page, testProject }) => {
    await page.goto('/')

    // Should show at least 1 project in stats
    const projectCount = page.locator('.card:has-text("Total Projects") >> .text-primary-400')
    await expect(projectCount).toBeVisible()
  })
})
