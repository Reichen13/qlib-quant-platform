// 主布局组件
import { Outlet } from "react-router-dom"
import { Sidebar } from "./sidebar"
import { Header } from "./header"

export function MainLayout() {
  return (
    <div className="flex h-svh overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        <Header />
        <main className="flex-1 overflow-y-auto scroll-smooth">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
