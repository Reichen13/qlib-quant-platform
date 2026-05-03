// 顶部栏组件 — 无黑线分隔 + 响应式
import { useState, useRef, useEffect } from "react"
import { Search, Moon, Sun, Menu } from "lucide-react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useAppStore } from "@/stores/app-store"

interface SearchResult {
  code: string
  name: string
  market: string
}

export function Header() {
  const navigate = useNavigate()
  const theme = useAppStore((s) => s.theme)
  const toggleTheme = useAppStore((s) => s.toggleTheme)
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)
  const [localSearch, setLocalSearch] = useState("")
  const [results, setResults] = useState<SearchResult[]>([])
  const [showResults, setShowResults] = useState(false)
  const [searching, setSearching] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowResults(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  const handleInputChange = (value: string) => {
    setLocalSearch(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (!value.trim()) {
      setResults([])
      setShowResults(false)
      return
    }

    setSearching(true)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(
          `${import.meta.env.DEV ? "http://localhost:8000" : ""}/api/stocks/search?q=${encodeURIComponent(value)}`
        )
        const data = await res.json()
        setResults(data.results || [])
        setShowResults(true)
      } catch {
        setResults([])
      } finally {
        setSearching(false)
      }
    }, 300)
  }

  const selectStock = (code: string) => {
    setShowResults(false)
    setLocalSearch("")
    navigate(`/quote?stock=${encodeURIComponent(code)}`)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (results.length > 0) {
      selectStock(results[0].code)
    }
  }

  return (
    <header className="flex h-14 items-center gap-3 bg-background/80 backdrop-blur-md px-4 md:px-6 shrink-0">
      {/* 移动端菜单按钮 */}
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden shrink-0 size-8"
        onClick={toggleSidebar}
      >
        <Menu className="size-5" />
      </Button>

      {/* 搜索框 */}
      <div ref={searchRef} className="flex-1 max-w-sm relative">
        <form onSubmit={handleSubmit}>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="search"
              placeholder="搜索股票..."
              className="pl-8 h-8 bg-muted/50 border-0 focus-visible:bg-background focus-visible:ring-1 focus-visible:ring-ring/30 text-sm"
              value={localSearch}
              onChange={(e) => handleInputChange(e.target.value)}
              onFocus={() => results.length > 0 && setShowResults(true)}
            />
          </div>
        </form>

        {/* 搜索结果下拉 */}
        {showResults && (
          <div className="absolute top-full left-0 right-0 mt-1.5 bg-popover rounded-xl shadow-lg z-50 max-h-64 overflow-y-auto py-1 border border-border/60">
            {searching ? (
              <div className="px-3 py-2.5 text-sm text-muted-foreground">搜索中...</div>
            ) : results.length > 0 ? (
              results.map((r) => (
                <button
                  key={r.code}
                  className="w-full flex items-center justify-between px-3 py-2 hover:bg-accent text-left transition-colors"
                  onClick={() => selectStock(r.code)}
                >
                  <span className="text-sm font-medium">{r.name}</span>
                  <span className="text-xs text-muted-foreground font-mono">{r.code}</span>
                </button>
              ))
            ) : (
              <div className="px-3 py-2.5 text-sm text-muted-foreground">未找到匹配的股票</div>
            )}
          </div>
        )}
      </div>

      {/* 右侧操作 */}
      <div className="flex items-center gap-1 ml-auto">
        <Button variant="ghost" size="icon" className="size-8" onClick={toggleTheme}>
          {theme === "dark" ? (
            <Sun className="size-3.5" />
          ) : (
            <Moon className="size-3.5" />
          )}
        </Button>
      </div>
    </header>
  )
}
