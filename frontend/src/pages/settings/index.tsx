// LLM 设置页面 — 用户自主配置 API Key
import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { useAppStore } from "@/stores/app-store"
import { api } from "@/lib/api"
import { Settings, Key, Globe, Zap, Brain, CheckCircle, XCircle, Loader2, Eye, EyeOff } from "lucide-react"

const PROVIDER_PRESETS = [
  { name: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", quickModel: "deepseek-chat", deepModel: "deepseek-reasoner" },
  { name: "OpenAI", baseUrl: "https://api.openai.com/v1", quickModel: "gpt-4o-mini", deepModel: "gpt-4o" },
  { name: "Qwen (通义千问)", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", quickModel: "qwen-turbo", deepModel: "qwen-plus" },
  { name: "GLM (智谱)", baseUrl: "https://open.bigmodel.cn/api/paas/v4", quickModel: "glm-4-flash", deepModel: "glm-4" },
  { name: "自定义", baseUrl: "", quickModel: "", deepModel: "" },
]

export function SettingsPage() {
  // 从 Zustand store 读取持久化的 LLM 配置
  const {
    llmApiKey, llmBaseUrl, llmQuickModel, llmDeepModel,
    setLlmApiKey, setLlmBaseUrl, setLlmQuickModel, setLlmDeepModel,
  } = useAppStore()

  const [showKey, setShowKey] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)
  const [serverStatus, setServerStatus] = useState<{ configured: boolean; message: string } | null>(null)

  // 检查服务器 LLM 状态
  useEffect(() => {
    api.llm.status().then(s => {
      setServerStatus({ configured: s.server_configured, message: s.message })
    }).catch(() => {
      setServerStatus({ configured: false, message: "无法获取服务器状态" })
    })
  }, [])

  // 保存到 localStorage（同步写入，确保 api.ts 能立即读取）
  const saveToLocalStorage = (key: string, value: string) => {
    if (value) {
      localStorage.setItem(key, value)
    } else {
      localStorage.removeItem(key)
    }
  }

  const handleTest = async () => {
    if (!llmApiKey) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.llm.testConnection(llmApiKey, llmBaseUrl, llmQuickModel, llmDeepModel)
      setTestResult(result)
    } catch (e: any) {
      setTestResult({ ok: false, message: e.message || "连接测试失败" })
    } finally {
      setTesting(false)
    }
  }

  const applyPreset = (preset: typeof PROVIDER_PRESETS[number]) => {
    setLlmBaseUrl(preset.baseUrl)
    setLlmQuickModel(preset.quickModel)
    setLlmDeepModel(preset.deepModel)
    saveToLocalStorage("qlib-llm-base-url", preset.baseUrl)
    saveToLocalStorage("qlib-llm-quick-model", preset.quickModel)
    saveToLocalStorage("qlib-llm-deep-model", preset.deepModel)
  }

  const isConfigured = !!llmApiKey

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-6 max-w-[900px] mx-auto">
      <div className="space-y-0.5">
        <h1 className="text-xl md:text-2xl font-bold tracking-tight flex items-center gap-2">
          <Settings className="h-8 w-8 text-slate-600" />
          LLM 设置
        </h1>
        <p className="text-muted-foreground">配置您的 LLM API Key，解锁 AI 策略、智能体辩论、新闻分析等功能</p>
      </div>

      {/* 服务器状态 */}
      {serverStatus && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              {serverStatus.configured ? (
                <CheckCircle className="h-4 w-4 text-emerald-500" />
              ) : (
                <XCircle className="h-4 w-4 text-amber-500" />
              )}
              服务器默认 LLM
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{serverStatus.message}</p>
            {!serverStatus.configured && (
              <p className="text-sm text-muted-foreground mt-1">
                请在下方输入您的 API Key，所有 AI 功能将通过您的账户调用。
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* API Key 输入 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Key className="h-4 w-4" />
            API Key
          </CardTitle>
          <CardDescription>支持 OpenAI-compatible API（DeepSeek / OpenAI / Qwen / GLM 等）</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                type={showKey ? "text" : "password"}
                placeholder="sk-your-api-key"
                value={llmApiKey}
                onChange={(e) => {
                  setLlmApiKey(e.target.value)
                  saveToLocalStorage("qlib-api-key", e.target.value)
                }}
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <Button onClick={handleTest} disabled={testing || !llmApiKey} variant="outline">
              {testing ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
              测试连接
            </Button>
          </div>

          {/* 测试结果 */}
          {testResult && (
            <div className={`p-3 rounded-lg flex items-start gap-2 ${
              testResult.ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
            }`}>
              {testResult.ok ? (
                <CheckCircle className="h-4 w-4 mt-0.5 shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
              )}
              <p className="text-sm">{testResult.message}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 提供商预设 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Globe className="h-4 w-4" />
            提供商预设
          </CardTitle>
          <CardDescription>选择一个提供商自动填入 Base URL 和模型名称</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {PROVIDER_PRESETS.map((preset) => (
              <Button
                key={preset.name}
                variant="outline"
                size="sm"
                onClick={() => applyPreset(preset)}
              >
                {preset.name}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 高级配置 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">高级配置</CardTitle>
          <CardDescription>自定义 Base URL 和模型名称（可选）</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium flex items-center gap-1">
              <Globe className="h-3 w-3" /> Base URL
            </label>
            <Input
              placeholder="https://api.deepseek.com/v1"
              value={llmBaseUrl}
              onChange={(e) => {
                setLlmBaseUrl(e.target.value)
                saveToLocalStorage("qlib-llm-base-url", e.target.value)
              }}
            />
            <p className="text-xs text-muted-foreground">OpenAI-compatible API 地址</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium flex items-center gap-1">
                <Zap className="h-3 w-3" /> 快速模型
              </label>
              <Input
                placeholder="deepseek-chat"
                value={llmQuickModel}
                onChange={(e) => {
                  setLlmQuickModel(e.target.value)
                  saveToLocalStorage("qlib-llm-quick-model", e.target.value)
                }}
              />
              <p className="text-xs text-muted-foreground">用于数据采集、情感分析</p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium flex items-center gap-1">
                <Brain className="h-3 w-3" /> 深度模型
              </label>
              <Input
                placeholder="deepseek-reasoner"
                value={llmDeepModel}
                onChange={(e) => {
                  setLlmDeepModel(e.target.value)
                  saveToLocalStorage("qlib-llm-deep-model", e.target.value)
                }}
              />
              <p className="text-xs text-muted-foreground">用于策略分析、辩论裁判</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 状态总览 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">连接状态</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm">API Key</span>
              <Badge variant={isConfigured ? "default" : "outline"}>
                {isConfigured ? "已配置" : "未配置"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">服务器默认 LLM</span>
              <Badge variant={serverStatus?.configured ? "default" : "outline"}>
                {serverStatus?.configured ? "可用" : "未配置"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">AI 功能状态</span>
              <Badge variant={isConfigured || serverStatus?.configured ? "default" : "destructive"}>
                {isConfigured || serverStatus?.configured ? "可用" : "不可用"}
              </Badge>
            </div>
          </div>
          {!isConfigured && !serverStatus?.configured && (
            <p className="text-sm text-muted-foreground mt-4">
              配置 API Key 后即可使用：AI 策略生成、多智能体辩论、新闻智能分析等功能。
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
