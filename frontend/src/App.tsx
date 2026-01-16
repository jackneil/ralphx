import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import ProjectDetail from './pages/ProjectDetail'
import LoopDetail from './pages/LoopDetail'
import WorkItems from './pages/WorkItems'
import RunHistory from './pages/RunHistory'
import Settings from './pages/Settings'
import Logs from './pages/Logs'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="projects/:slug" element={<ProjectDetail />} />
        <Route path="projects/:slug/items" element={<WorkItems />} />
        <Route path="projects/:slug/runs" element={<RunHistory />} />
        <Route path="projects/:slug/loops/:loopName" element={<LoopDetail />} />
        <Route path="logs" element={<Logs />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
