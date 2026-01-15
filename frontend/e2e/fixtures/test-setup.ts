import { test as base, expect } from '@playwright/test'
import { randomUUID } from 'crypto'
import * as fs from 'fs'
import * as path from 'path'
import * as os from 'os'

interface TestProject {
  slug: string
  name: string
  path: string
}

interface TestFixtures {
  testProject: TestProject
  testProjectWithLoop: TestProject
}

export const test = base.extend<TestFixtures>({
  testProject: async ({ request }, use) => {
    // Create a unique temp directory for this test
    const projectName = `e2e-test-${randomUUID().slice(0, 8)}`
    const projectPath = path.join(os.tmpdir(), projectName)

    // Create project directory with .ralphx structure
    fs.mkdirSync(path.join(projectPath, '.ralphx', 'loops'), { recursive: true })
    fs.mkdirSync(path.join(projectPath, '.ralphx', 'resources', 'design_doc'), { recursive: true })

    // Create test files for file browser tests
    fs.writeFileSync(
      path.join(projectPath, 'README.md'),
      '# Test Project\n\nThis is a test project for E2E tests.\n'
    )

    // Create a docs directory with design doc
    fs.mkdirSync(path.join(projectPath, 'docs'), { recursive: true })
    fs.writeFileSync(
      path.join(projectPath, 'docs', 'design.md'),
      '# Design Document\n\n## Overview\n\nThis is the system design for the test project.\n\n## Architecture\n\nDetails here...\n'
    )

    // Create a sample source file
    fs.writeFileSync(
      path.join(projectPath, 'main.py'),
      '#!/usr/bin/env python3\n"""Main entry point."""\n\ndef main():\n    print("Hello, World!")\n\nif __name__ == "__main__":\n    main()\n'
    )

    // Register project via API
    const response = await request.post('/api/projects', {
      data: { path: projectPath, name: projectName }
    })
    expect(response.ok()).toBeTruthy()
    const project = await response.json()

    await use({
      slug: project.slug,
      name: project.name,
      path: projectPath,
    })

    // Cleanup: Delete project from API and filesystem
    await request.delete(`/api/projects/${project.slug}`)
    fs.rmSync(projectPath, { recursive: true, force: true })
  },

  testProjectWithLoop: async ({ request }, use) => {
    // Create project with a loop config
    const projectName = `e2e-loop-${randomUUID().slice(0, 8)}`
    const projectPath = path.join(os.tmpdir(), projectName)

    // Create project directory with loop config
    fs.mkdirSync(path.join(projectPath, '.ralphx', 'loops'), { recursive: true })

    // Write a test loop config
    const loopConfig = `name: test-loop
display_name: Test Loop
type: generation

modes:
  default:
    model: claude-3-haiku
    timeout: 60
    prompt_template: "Test prompt"

limits:
  max_iterations: 10
  max_runtime_seconds: 300
`
    fs.writeFileSync(
      path.join(projectPath, '.ralphx', 'loops', 'test-loop.yaml'),
      loopConfig
    )

    // Register project via API
    const response = await request.post('/api/projects', {
      data: { path: projectPath, name: projectName }
    })
    expect(response.ok()).toBeTruthy()
    const project = await response.json()

    // Sync loops and wait for it to complete
    const syncResponse = await request.post(`/api/projects/${project.slug}/loops/sync`)
    expect(syncResponse.ok()).toBeTruthy()

    // Verify the loop was synced by fetching it
    let loopFound = false
    for (let i = 0; i < 5; i++) {
      const loopResponse = await request.get(`/api/projects/${project.slug}/loops/test-loop`)
      if (loopResponse.ok()) {
        loopFound = true
        break
      }
      // Wait a bit before retrying
      await new Promise(r => setTimeout(r, 200))
    }
    expect(loopFound).toBeTruthy()

    await use({
      slug: project.slug,
      name: project.name,
      path: projectPath,
    })

    // Cleanup
    await request.delete(`/api/projects/${project.slug}`)
    fs.rmSync(projectPath, { recursive: true, force: true })
  },
})

export { expect }
