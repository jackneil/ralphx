import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import ProjectWorkflowDashboard from './pages/ProjectWorkflowDashboard'
import LoopDetail from './pages/LoopDetail'
import WorkflowItems from './pages/WorkflowItems'
import WorkflowResources from './pages/WorkflowResources'
import WorkflowEdit from './pages/WorkflowEdit'
import ProjectSettings from './pages/ProjectSettings'
import RunHistory from './pages/RunHistory'
import Settings from './pages/Settings'
import Logs from './pages/Logs'
import WorkflowDetail from './pages/WorkflowDetail'
import ProjectDashboard from './pages/ProjectDashboard'
import Wiki from './pages/Wiki'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        {/* Main project page - workflow-first dashboard */}
        <Route path="projects/:slug" element={<ProjectWorkflowDashboard />} />
        {/* Cross-workflow dashboard for PM view */}
        <Route path="projects/:slug/dashboard" element={<ProjectDashboard />} />
        {/* Project settings (auth + shared resource library) */}
        <Route path="projects/:slug/settings" element={<ProjectSettings />} />
        {/* Legacy project-level work items (redirect to project dashboard) */}
        <Route path="projects/:slug/items" element={<Navigate to=".." replace />} />
        {/* Project-level run history */}
        <Route path="projects/:slug/runs" element={<RunHistory />} />
        {/* Loop detail page */}
        <Route path="projects/:slug/loops/:loopName" element={<LoopDetail />} />
        {/* Workflow pages */}
        <Route path="projects/:slug/workflows" element={<Navigate to=".." replace />} />
        <Route path="projects/:slug/workflows/:workflowId" element={<WorkflowDetail />} />
        <Route path="projects/:slug/workflows/:workflowId/edit" element={<WorkflowEdit />} />
        <Route path="projects/:slug/workflows/:workflowId/items" element={<WorkflowItems />} />
        <Route path="projects/:slug/workflows/:workflowId/resources" element={<WorkflowResources />} />
        <Route path="projects/:slug/workflows/:workflowId/runs" element={<RunHistory />} />
        {/* Global pages */}
        <Route path="wiki" element={<Wiki />} />
        <Route path="logs" element={<Logs />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
