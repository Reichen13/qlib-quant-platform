// 全局状态管理
import { create } from "zustand"
import { persist } from "zustand/middleware"

interface AppState {
  // 侧边栏状态
  sidebarOpen: boolean
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void

  // 主题状态
  theme: "light" | "dark"
  toggleTheme: () => void
  setTheme: (theme: "light" | "dark") => void

  // 搜索状态
  searchQuery: string
  setSearchQuery: (query: string) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // 侧边栏
      sidebarOpen: true,
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),

      // 主题
      theme: "light",
      toggleTheme: () => set((state) => {
        const newTheme = state.theme === "light" ? "dark" : "light"
        // 更新 DOM
        if (newTheme === "dark") {
          document.documentElement.classList.add("dark")
        } else {
          document.documentElement.classList.remove("dark")
        }
        return { theme: newTheme }
      }),
      setTheme: (theme) => set(() => {
        // 更新 DOM
        if (theme === "dark") {
          document.documentElement.classList.add("dark")
        } else {
          document.documentElement.classList.remove("dark")
        }
        return { theme }
      }),

      // 搜索
      searchQuery: "",
      setSearchQuery: (query) => set({ searchQuery: query }),
    }),
    {
      name: "qlib-app-store",
      partialize: (state) => ({
        theme: state.theme,
        sidebarOpen: state.sidebarOpen,
      }),
    }
  )
)

// 初始化主题
if (typeof window !== "undefined") {
  const storedTheme = localStorage.getItem("qlib-app-store")
  if (storedTheme) {
    try {
      const parsed = JSON.parse(storedTheme)
      if (parsed.state?.theme === "dark") {
        document.documentElement.classList.add("dark")
      }
    } catch {
      // ignore
    }
  }
}
