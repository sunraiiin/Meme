import { Avatar, Badge, Button, Drawer, Dropdown, Input, Layout, Menu, Space, message } from 'antd'
import {
  AppstoreOutlined,
  BookOutlined,
  CommentOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  HddOutlined,
  HistoryOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PictureOutlined,
  PlusOutlined,
  RobotOutlined,
  SearchOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useEffect, useState, type ReactNode } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useChatHeaderStore } from '@/stores/chatHeaderStore'
import { agentTaskApi } from '@/api/agentTask'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'
import { isFeatureVisibleInNavigation, type FeatureKey } from '@/config/features'
import logo from '@/images/logo.png'

const { Sider, Content, Header } = Layout

// 首版导航只呈现产品主线；高级和待删除能力仍由功能开关控制。
type ProductMenuGroup = {
  type: 'group'
  label: string
  children: Array<{
    key: string
    icon: ReactNode
    label: string
    feature: FeatureKey
  }>
}

const menuItems: ProductMenuGroup[] = [
  {
    type: 'group' as const,
    label: '核心体验',
    children: [
      { key: '/', icon: <AppstoreOutlined />, label: '首页', feature: 'dashboard' },
      { key: '/chat', icon: <CommentOutlined />, label: '对话', feature: 'chat' },
    ],
  },
  {
    type: 'group' as const,
    label: '知识与记忆',
    children: [
      { key: '/knowledge', icon: <BookOutlined />, label: '知识库', feature: 'knowledge' },
      { key: '/memory', icon: <HddOutlined />, label: '记忆', feature: 'memory' },
      { key: '/graph', icon: <DeploymentUnitOutlined />, label: '记忆图谱', feature: 'memoryGraph' },
      { key: '/search', icon: <SearchOutlined />, label: '搜索', feature: 'search' },
      { key: '/images', icon: <PictureOutlined />, label: '图片库', feature: 'imageLibrary' },
    ],
  },
  {
    type: 'group' as const,
    label: '质量与观察',
    children: [
      { key: '/traces', icon: <HistoryOutlined />, label: '调用追踪', feature: 'traces' },
      { key: '/research', icon: <FileSearchOutlined />, label: '深度研究', feature: 'research' },
      { key: '/agent-tasks', icon: <ClockCircleOutlined />, label: '定时任务', feature: 'scheduledTasks' },
    ],
  },
  {
    type: 'group' as const,
    label: '设置',
    children: [
      { key: '/settings/models', icon: <SettingOutlined />, label: '模型', feature: 'modelConfig' },
      { key: '/settings/agent', icon: <RobotOutlined />, label: 'AI 助手', feature: 'agentConfig' },
      { key: '/settings/skills', icon: <ThunderboltOutlined />, label: '技能', feature: 'skills' },
      { key: '/settings/tools', icon: <ToolOutlined />, label: '工具配置', feature: 'mcp' },
    ],
  },
]

// 小屏（手机/窄平板）检测：≤768px 走抽屉式侧边栏
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.innerWidth <= 768,
  )
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return isMobile
}

function selectedMenuKey(pathname: string): string {
  if (pathname.startsWith('/knowledge-bases/')) return '/knowledge'
  return pathname
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const isMobile = useIsMobile()
  // 聊天页注册的顶栏操作（手机端聊天页用它替代搜索框，合并成一行）
  const chatHeaderActive = useChatHeaderStore((s) => s.active)
  const chatOpenHistory = useChatHeaderStore((s) => s.openHistory)
  const chatNewChat = useChatHeaderStore((s) => s.newChat)
  const showChatHeader = isMobile && chatHeaderActive && location.pathname === '/chat'

  // 桌面端：侧边栏折叠（窄条）；移动端：抽屉开关
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  // 切换路由后自动关闭移动端抽屉
  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  // 定时任务未读红点：轮询 + 路由切换时刷新（离开任务页 mark-seen 后归零）
  const [unreadTasks, setUnreadTasks] = useState(0)
  useEffect(() => {
    if (!isFeatureVisibleInNavigation('scheduledTasks')) {
      setUnreadTasks(0)
      return
    }

    let alive = true
    const fetchUnread = () => {
      agentTaskApi
        .unreadCount()
        .then(({ data }) => {
          if (alive) setUnreadTasks(data.count)
        })
        .catch(() => {})
    }
    fetchUnread()
    const timer = window.setInterval(fetchUnread, 60000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [location.pathname])

  // 主壳挂载时锁死 html/body 滚动（比 :has 更稳），卸载后恢复登录/分享页整页滚动
  useEffect(() => {
    const root = document.documentElement
    root.classList.add('app-shell-active')
    return () => root.classList.remove('app-shell-active')
  }, [])

  const onLogout = async () => {
    await logout()
    message.success('已退出登录')
    navigate('/login', { replace: true })
  }

  // logo 头部（桌面 Sider 与移动抽屉共用）
  const brand = (mini: boolean) => (
    <div
      style={{
        height: 64,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        paddingInline: mini ? 0 : 20,
        justifyContent: mini ? 'center' : 'flex-start',
        color: '#171719',
        overflow: 'hidden',
      }}
    >
      <img
        src={logo}
        alt="Meme"
        style={{ width: 36, height: 36, borderRadius: 9, objectFit: 'cover', flexShrink: 0 }}
      />
      {!mini && (
        <span style={{ fontWeight: 600, fontSize: 19, whiteSpace: 'nowrap' }}>Meme</span>
      )}
    </div>
  )

  const navMenu = (mini: boolean) => {
    // 给「定时任务」注入未读红点（不改全局静态 menuItems）
    const items = menuItems
      .map((group) => ({
        ...group,
        children: group.children
          .filter((item) => isFeatureVisibleInNavigation(item.feature))
          .map((item) => {
            const menuItem = { key: item.key, icon: item.icon, label: item.label }
            return item.key === '/agent-tasks' && unreadTasks > 0 && !mini
              ? {
                  ...menuItem,
                  label: (
                    <Badge count={unreadTasks} size="small" offset={[10, 0]}>
                      <span>{item.label}</span>
                    </Badge>
                  ),
                }
              : menuItem
          }),
      }))
      .filter((group) => group.children.length > 0)
    return (
      <Menu
        mode="inline"
        theme="light"
        inlineCollapsed={mini}
        selectedKeys={[selectedMenuKey(location.pathname)]}
        items={items}
        onClick={({ key }) => navigate(key)}
        style={{ borderInlineEnd: 'none', background: 'transparent' }}
      />
    )
  }

  return (
    <Layout style={{ height: '100%', overflow: 'hidden' }} className="app-shell">
      {/* 桌面端：常驻可折叠侧边栏 */}
      {!isMobile && (
        <Sider
          width={236}
          collapsible
          collapsed={collapsed}
          trigger={null}
          collapsedWidth={72}
          style={{
            borderInlineEnd: '1px solid #f0f0f0',
            transition: 'background 0.4s',
          }}
        >
          {brand(collapsed)}
          <div className="app-shell-sider-menu" style={{ paddingBottom: 12 }}>
            {navMenu(collapsed)}
          </div>
        </Sider>
      )}

      {/* 移动端：抽屉式侧边栏 */}
      {isMobile && (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={236}
          closable={false}
          styles={{
            body: { padding: 0, display: 'flex', flexDirection: 'column', height: '100%' },
          }}
        >
          {brand(false)}
          <div className="app-shell-sider-menu" style={{ paddingBottom: 12 }}>
            {navMenu(false)}
          </div>
        </Drawer>
      )}

      <Layout className="app-shell-main">
        <Header
          style={{
            flexShrink: 0,
            paddingInline: isMobile ? 12 : 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center' }}>
            <Button
              type="text"
              aria-label="菜单"
              icon={
                isMobile ? (
                  <MenuUnfoldOutlined />
                ) : collapsed ? (
                  <MenuUnfoldOutlined />
                ) : (
                  <MenuFoldOutlined />
                )
              }
              onClick={() =>
                isMobile ? setDrawerOpen(true) : setCollapsed((c) => !c)
              }
              style={{ fontSize: 18 }}
            />
          </div>

          {/* 中间区：手机端聊天页显示「会话 / 新对话」，其余页面显示搜索框 */}
          {showChatHeader ? (
            <div
              style={{
                flex: 1,
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                gap: 8,
                minWidth: 0,
                padding: '0 8px',
              }}
            >
              <Button
                type="text"
                icon={<HistoryOutlined />}
                onClick={() => chatOpenHistory?.()}
              >
                会话
              </Button>
              <Button
                type="text"
                icon={<PlusOutlined />}
                onClick={() => chatNewChat?.()}
              >
                新对话
              </Button>
            </div>
          ) : (
            <div
              style={{
                flex: 1,
                display: 'flex',
                justifyContent: 'center',
                minWidth: 0,
                padding: isMobile ? '0 8px' : '0 16px',
              }}
            >
              <Input
                className="top-search"
                prefix={<SearchOutlined style={{ color: '#98A2B3' }} />}
                placeholder={isMobile ? '搜索…' : '搜索文档、图片、记忆…'}
                allowClear
                style={{ width: '100%', maxWidth: 560 }}
                onPressEnter={(e) => {
                  const q = (e.target as HTMLInputElement).value.trim()
                  if (q) navigate(`/search?q=${encodeURIComponent(q)}`)
                }}
              />
            </div>
          )}

          <Dropdown
            menu={{
              items: [
                {
                  key: 'profile',
                  icon: <UserOutlined />,
                  label: '个人中心',
                  onClick: () => navigate('/profile'),
                },
                { type: 'divider' },
                {
                  key: 'logout',
                  icon: <LogoutOutlined />,
                  label: '退出登录',
                  onClick: onLogout,
                },
              ],
            }}
          >
            <Space align="center" style={{ cursor: 'pointer', flexShrink: 0 }}>
              {user?.avatar ? (
                <AuthenticatedImage
                    src={user.avatar}
                    alt="头像"
                    style={{
                      width: 30,
                      height: 30,
                      borderRadius: '50%',
                      objectFit: 'cover',
                      display: 'block',
                    }}
                  />
                ) : (
                  <Avatar size={30} style={{ background: '#155EEF' }}>
                    {user?.username?.[0]?.toUpperCase() ?? <UserOutlined />}
                  </Avatar>
                )}
                {!isMobile && (
                  <span style={{ fontWeight: 500 }}>
                    {user?.nickname || user?.username || '用户'}
                  </span>
                )}
              </Space>
            </Dropdown>
          </Header>
          <Content
            className="app-shell-content"
            style={{ padding: isMobile ? 14 : 24 }}
          >
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    )
  }
