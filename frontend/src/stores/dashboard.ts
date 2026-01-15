import { create } from 'zustand'
import { listProjects, Item } from '../api'

export interface Project {
  id: string
  slug: string
  name: string
  path: string
  design_doc?: string
  created_at: string
  stats?: {
    total_items: number
    pending_items: number
    completed_items: number
    loops: number
    active_runs: number
  }
}

export interface Loop {
  name: string
  display_name: string
  type: string
  modes: string[]
  is_running: boolean
  current_iteration?: number
  current_mode?: string
}

// Re-export Item from api.ts for backward compatibility
export type { Item }
// Keep WorkItem alias for backward compatibility
export type WorkItem = Item

interface DashboardState {
  // Projects
  projects: Project[]
  selectedProject: Project | null
  projectsLoading: boolean
  projectsError: string | null

  // Loops
  loops: Loop[]
  selectedLoop: Loop | null
  loopsLoading: boolean

  // Items
  items: Item[]
  itemsLoading: boolean
  itemsTotal: number

  // Actions
  setProjects: (projects: Project[]) => void
  setSelectedProject: (project: Project | null) => void
  setProjectsLoading: (loading: boolean) => void
  setProjectsError: (error: string | null) => void
  setLoops: (loops: Loop[]) => void
  setSelectedLoop: (loop: Loop | null) => void
  setLoopsLoading: (loading: boolean) => void
  setItems: (items: Item[], total: number) => void
  setItemsLoading: (loading: boolean) => void
  updateLoop: (name: string, updates: Partial<Loop>) => void
  addItem: (item: Item) => void
  loadProjects: () => Promise<void>
}

export const useDashboardStore = create<DashboardState>((set) => ({
  // Initial state
  projects: [],
  selectedProject: null,
  projectsLoading: false,
  projectsError: null,
  loops: [],
  selectedLoop: null,
  loopsLoading: false,
  items: [],
  itemsLoading: false,
  itemsTotal: 0,

  // Actions
  setProjects: (projects) => set({ projects }),
  setSelectedProject: (project) => set({ selectedProject: project }),
  setProjectsLoading: (loading) => set({ projectsLoading: loading }),
  setProjectsError: (error) => set({ projectsError: error }),
  setLoops: (loops) => set({ loops }),
  setSelectedLoop: (loop) => set({ selectedLoop: loop }),
  setLoopsLoading: (loading) => set({ loopsLoading: loading }),
  setItems: (items, total) => set({ items, itemsTotal: total }),
  setItemsLoading: (loading) => set({ itemsLoading: loading }),

  updateLoop: (name, updates) =>
    set((state) => ({
      loops: state.loops.map((loop) =>
        loop.name === name ? { ...loop, ...updates } : loop
      ),
      selectedLoop:
        state.selectedLoop?.name === name
          ? { ...state.selectedLoop, ...updates }
          : state.selectedLoop,
    })),

  addItem: (item) =>
    set((state) => ({
      items: [item, ...state.items],
      itemsTotal: state.itemsTotal + 1,
    })),

  loadProjects: async () => {
    set({ projectsLoading: true, projectsError: null })
    try {
      const projects = await listProjects()
      set({ projects, projectsLoading: false })
    } catch (err) {
      set({
        projectsError: err instanceof Error ? err.message : 'Failed to load projects',
        projectsLoading: false,
      })
    }
  },
}))
