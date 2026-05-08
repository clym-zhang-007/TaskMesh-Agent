import { useState, useRef, useEffect } from 'react'

const API_BASE = '/api'

// LocalStorage 键名
const STORAGE_KEY = 'agent_conversations'
const ACTIVE_CONVERSATION_KEY = 'active_conversation_id'

function ScrollToBottom({ onClick }) {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const el = document.querySelector('.chat-area')
    if (!el) return
    const handleScroll = () => setVisible(el.scrollHeight - el.scrollTop - el.clientHeight > 200)
    el.addEventListener('scroll', handleScroll)
    return () => el.removeEventListener('scroll', handleScroll)
  }, [])
  if (!visible) return null
  return (
    <button className="scroll-bottom" onClick={onClick}>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}

function App() {
  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [running, setRunning] = useState(false)
  const [apiStatus, setApiStatus] = useState('checking')
  const chatRef = useRef(null)
  const abortControllerRef = useRef(null)  // 用于停止请求

  const scrollToBottom = () => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: 'smooth' })
  }

  useEffect(() => { scrollToBottom() }, [messages])

  // 检查 API 健康状态
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`, { timeout: 5000 })
        if (res.ok) {
          const data = await res.json()
          console.log('[Health Check] API is healthy:', data)
          setApiStatus('ok')
        } else {
          setApiStatus('error')
        }
      } catch (err) {
        console.error('[Health Check] Failed:', err)
        setApiStatus('error')
      }
    }
    checkHealth()
  }, [])

  // 加载对话列表
  useEffect(() => {
    loadConversations()
  }, [])

  // 清理无效的 active conversation
  useEffect(() => {
    const activeId = localStorage.getItem(ACTIVE_CONVERSATION_KEY)
    if (activeId && conversations.length > 0) {
      // 检查 activeId 是否在对话列表中
      const exists = conversations.some(c => c.id === activeId)
      if (!exists) {
        // 不存在，清理
        localStorage.removeItem(ACTIVE_CONVERSATION_KEY)
        setActiveConversationId(null)
        setMessages([])
      }
    }
  }, [conversations])

  // 清理无效的 active conversation
  useEffect(() => {
    const activeId = localStorage.getItem(ACTIVE_CONVERSATION_KEY)
    if (activeId && conversations.length > 0) {
      // 检查 activeId 是否在对话列表中
      const exists = conversations.some(c => c.id === activeId)
      if (!exists) {
        // 不存在，清理
        localStorage.removeItem(ACTIVE_CONVERSATION_KEY)
        setActiveConversationId(null)
        setMessages([])
      }
    }
  }, [conversations])

  // 加载对话列表（混合策略：优先本地，后台同步服务器）
  const loadConversations = async () => {
    // 从服务器加载
    try {
      const res = await fetch(`${API_BASE}/conversations`)
      if (res.ok) {
        const serverConversations = await res.json()
        setConversations(serverConversations)
        // 同步到 localStorage
        localStorage.setItem(STORAGE_KEY, JSON.stringify(serverConversations))
      } else {
        // 如果服务器请求失败，清空本地缓存
        localStorage.removeItem(STORAGE_KEY)
        setConversations([])
      }
    } catch (err) {
      console.error('Failed to load conversations from server:', err)
      // 网络错误时，尝试使用本地缓存
      const localData = localStorage.getItem(STORAGE_KEY)
      if (localData) {
        try {
          const local = JSON.parse(localData)
          setConversations(local)
        } catch (e) {
          console.error('Failed to parse local conversations:', e)
          localStorage.removeItem(STORAGE_KEY)
          setConversations([])
        }
      }
    }
  }

  // 加载对话详情
  const loadConversation = async (conversationId) => {
    try {
      const res = await fetch(`${API_BASE}/conversations/${conversationId}`)
      if (res.ok) {
        const conversation = await res.json()
        
        // 转换消息格式，保留标记
        const formattedMessages = conversation.messages.map(msg => ({
          role: msg.role,
          content: msg.content,
          isToolCall: msg.is_tool_call || false,
          isToolOutput: msg.is_tool_output || false,
          isError: msg.is_error || false,
          toolName: msg.tool_name || null,
          fullOutput: msg.full_output || null,
        }))
        
        setMessages(formattedMessages)
        setActiveConversationId(conversationId)
        localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId)
      } else if (res.status === 404 || res.status === 500) {
        // 对话不存在，重新加载对话列表
        console.warn(`Conversation ${conversationId} not found, reloading list`)
        await loadConversations()
        setMessages([])
        setActiveConversationId(null)
        localStorage.removeItem(ACTIVE_CONVERSATION_KEY)
      }
    } catch (err) {
      console.error('Failed to load conversation:', err)
      // 加载失败，清空当前对话
      setMessages([])
      setActiveConversationId(null)
      localStorage.removeItem(ACTIVE_CONVERSATION_KEY)
    }
  }

  // 创建新对话
  const createNewConversation = () => {
    setMessages([])
    setActiveConversationId(null)
    setInput('')
    localStorage.removeItem(ACTIVE_CONVERSATION_KEY)
  }

  // 删除对话
  const deleteConversation = async (conversationId, e) => {
    e.stopPropagation()
    
    if (!confirm('确定要删除这个对话吗？')) return

    try {
      const res = await fetch(`${API_BASE}/conversations/${conversationId}`, {
        method: 'DELETE'
      })
      
      if (res.ok) {
        // 从列表中移除
        setConversations(prev => prev.filter(c => c.id !== conversationId))
        
        // 如果删除的是当前对话，清空消息
        if (conversationId === activeConversationId) {
          createNewConversation()
        }
        
        // 重新加载列表
        loadConversations()
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
    }
  }

  // 停止执行
  const stopExecution = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setRunning(false)
  }

  // 发送消息（流式）
  const sendMessage = async () => {
    const trimmed = input.trim()
    if (!trimmed || running) return

    setInput('')
    const userMsg = { role: 'user', content: trimmed }
    setMessages(prev => [...prev, userMsg])
    setRunning(true)

    // 创建 AbortController
    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message: trimmed,
          conversation_id: activeConversationId 
        }),
        signal: abortControllerRef.current.signal  // 添加信号
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      // 使用 EventSource 接收流式数据
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const handleSseData = (data) => {
        if (data.type === 'conversation_id') {
          if (!activeConversationId) {
            setActiveConversationId(data.conversation_id)
            localStorage.setItem(ACTIVE_CONVERSATION_KEY, data.conversation_id)
          }
        }
        else if (data.type === 'tool_start') {
          const toolName = data.tool_name
          const toolInput = data.tool_input

          let displayCmd = ''
          if (toolName === 'bash') {
            displayCmd = `$ ${toolInput.command}`
          } else if (toolName === 'todo') {
            displayCmd = '正在更新任务清单...'
          } else {
            displayCmd = `${toolName}(${Object.entries(toolInput).map(([k, v]) => `${k}=${JSON.stringify(v).slice(0, 50)}`).join(', ')})`
          }

          setMessages(prev => [...prev, {
            role: 'assistant',
            content: displayCmd,
            isToolCall: true,
            toolName: toolName,
          }])
        }
        else if (data.type === 'tool_result') {
          const toolName = data.tool_name
          const output = data.output
          if (output && output !== '(no output)') {
            const isTodo = toolName === 'todo'
            const displayOutput = isTodo
              ? output
              : (output.length > 200 ? output.substring(0, 200) + '...' : output)
            setMessages(prev => [...prev, {
              role: 'assistant',
              content: displayOutput,
              isToolOutput: true,
              isTodoOutput: isTodo,
              toolName: toolName,
              fullOutput: output,
            }])
          }
        }
        else if (data.type === 'text') {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: data.text,
          }])
        }
        else if (data.type === 'done') {
          loadConversations()
        }
        else if (data.type === 'error') {
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: `❌ Error: ${data.message}`,
            isError: true,
          }])
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          buffer += decoder.decode()
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''

        for (const eventText of events) {
          const dataLines = eventText
            .split('\n')
            .filter(line => line.startsWith('data: '))
            .map(line => line.slice(6))

          if (dataLines.length === 0) continue

          const payload = dataLines.join('\n')
          const data = JSON.parse(payload)
          handleSseData(data)
        }
      }

      if (buffer.trim()) {
        const dataLines = buffer
          .split('\n')
          .filter(line => line.startsWith('data: '))
          .map(line => line.slice(6))

        if (dataLines.length > 0) {
          const payload = dataLines.join('\n')
          const data = JSON.parse(payload)
          handleSseData(data)
        }
      }
    } catch (err) {
      console.error('Chat error:', err)
      if (err.name === 'AbortError') {
        setMessages(prev => [...prev, {
          role: 'assistant', 
          content: '⏹️ 执行已停止',
          isError: true,
        }])
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant', 
          content: `❌ Error: ${err.message}`,
          isError: true,
        }])
      }
    } finally {
      setRunning(false)
      abortControllerRef.current = null
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      console.log('Copied to clipboard')
    }).catch(err => {
      console.error('Failed to copy:', err)
    })
  }

  const emptyState = messages.length === 0

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
              <rect width="22" height="22" rx="6" fill="#2563eb" />
              <path d="M7 11h8M11 7v8" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span className="sidebar-title">Agent</span>
          </div>
          <div className="sidebar-model">
            <span>DeepSeek</span>
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M3 5l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
        </div>
        
        <button className="new-chat-btn" onClick={createNewConversation}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          新对话
        </button>
        
        <div className="sidebar-label">最近对话</div>
        
        <div className="conversation-list">
          {conversations.length === 0 ? (
            <div className="conversation-empty">暂无对话历史</div>
          ) : (
            conversations.map(c => (
              <div 
                key={c.id} 
                className={`conversation-item${c.id === activeConversationId ? ' active' : ''}`}
                onClick={() => loadConversation(c.id)}
              >
                <span className="conversation-title">{c.title}</span>
                <span className="conversation-more" onClick={(e) => deleteConversation(c.id, e)}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor">
                    <path d="M4 6h8M6 6V4h4v2M7 10v-3M9 10v-3M5 6v7a1 1 0 001 1h4a1 1 0 001-1V6" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                </span>
              </div>
            ))
          )}
        </div>
        
        <div className="sidebar-footer">
          <div className={`api-status api-status-${apiStatus}`}>
            <span className="status-dot"></span>
            <span className="status-text">
              {apiStatus === 'checking' && 'Checking API...'}
              {apiStatus === 'ok' && 'API Connected'}
              {apiStatus === 'error' && 'API Disconnected'}
            </span>
          </div>
        </div>
      </aside>

      <main className="chat-main">
        <div className="chat-area" ref={chatRef}>
          {emptyState ? (
            <div className="empty-state">
              <h2>有什么可以帮你的？</h2>
              <p className="empty-hint">发送消息开始与 Agent 对话</p>
              
              <div className="example-prompts">
                <button className="example-prompt" onClick={() => setInput('列出当前目录的文件')}>
                  📁 列出当前目录的文件
                </button>
                <button className="example-prompt" onClick={() => setInput('显示系统信息')}>
                  💻 显示系统信息
                </button>
                <button className="example-prompt" onClick={() => setInput('查看 Python 版本')}>
                  🐍 查看 Python 版本
                </button>
                <button className="example-prompt" onClick={() => setInput('创建一个测试文件')}>
                  ✨ 创建一个测试文件
                </button>
              </div>
            </div>
          ) : (
            messages.map((msg, i) => {
              if (msg.role === 'user') {
                return (
                  <div key={i} className="msg-row msg-user">
                    <div className="msg-bubble"><p>{msg.content}</p></div>
                  </div>
                )
              }
              return (
                <div key={i} className={`msg-row msg-assistant${msg.isToolCall ? ' msg-command' : ''}${msg.isToolOutput ? ' msg-output' : ''}${msg.isError ? ' msg-error' : ''}${msg.isTodoOutput ? ' msg-todo-output' : ''}`}>
                  <p className="msg-text" style={{ whiteSpace: msg.isTodoOutput ? 'pre-wrap' : 'normal' }}>{msg.content}</p>
                  {!msg.isToolCall && !msg.isToolOutput && (
                    <div className="msg-actions">
                      <button title="Copy" onClick={() => copyToClipboard(msg.content)}>
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="1.2" />
                          <path d="M2 10V2h8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              )
            })
          )}
          {running && (
            <div className="msg-row msg-assistant">
              <div className="thinking-indicator">
                <span className="thinking-dot" /><span className="thinking-dot" /><span className="thinking-dot" />
              </div>
            </div>
          )}
          <ScrollToBottom onClick={scrollToBottom} />
        </div>

        <div className="input-area">
          <div className="input-wrapper">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
              placeholder="向 Agent 提问"
              disabled={running}
              rows={1}
            />
            <div className="input-actions">
              {running ? (
                <button className="stop-btn" onClick={stopExecution}>
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <rect x="5" y="5" width="8" height="8" rx="1" fill="currentColor" />
                  </svg>
                </button>
              ) : (
                <button className="send-btn" onClick={sendMessage} disabled={!input.trim()}>
                  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                    <path d="M3 9h12M12 6l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              )}
            </div>
          </div>
          <p className="input-hint">Agent 可能会出错，请核对重要信息。</p>
        </div>
      </main>
    </div>
  )
}

export default App
