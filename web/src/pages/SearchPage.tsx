import { useEffect, useState, type KeyboardEvent, type ReactNode } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Card, Empty, Input, Spin, Tag, Typography, message } from 'antd'
import {
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  HddOutlined,
  PictureOutlined,
  RightOutlined,
} from '@ant-design/icons'
import { searchApi, type GlobalSearchResult } from '@/api/search'
import SearchResultDrawer, {
  type SearchPreview,
} from '@/components/search/SearchResultDrawer'

const { Text, Paragraph } = Typography

function memoryTrustTone(confidence?: number | null) {
  const value = typeof confidence === 'number' ? confidence : 0.8
  if (value >= 0.85) return 'high'
  if (value >= 0.75) return 'medium'
  return 'low'
}

function MemoryTrustTag({ confidence }: { confidence?: number | null }) {
  const tone = memoryTrustTone(confidence)
  const label = tone === 'high' ? '高置信' : tone === 'medium' ? '中置信' : '待确认'
  const color = tone === 'high' ? 'success' : tone === 'medium' ? 'processing' : 'warning'
  const value = typeof confidence === 'number' ? confidence : 0.8
  return (
    <Tag
      color={color}
      icon={tone === 'low' ? <ExclamationCircleOutlined /> : <CheckCircleOutlined />}
      style={{ margin: 0 }}
    >
      {label} {Math.round(Math.max(0, Math.min(1, value)) * 100)}%
    </Tag>
  )
}

function relevanceLabel(score: number): string {
  return `${Math.round(Math.max(0, Math.min(1, score)) * 100)}% 相关`
}

function SearchResultCard({
  title,
  score,
  meta,
  excerpt,
  onOpen,
}: {
  title: ReactNode
  score: number
  meta?: ReactNode
  excerpt?: string | null
  onOpen: () => void
}) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onOpen()
    }
  }

  return (
    <Card
      size="small"
      hoverable
      role="button"
      tabIndex={0}
      aria-label="打开搜索结果详情"
      onClick={onOpen}
      onKeyDown={onKeyDown}
      styles={{ body: { padding: 13 } }}
      style={{ marginBottom: 10, cursor: 'pointer' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <Text strong ellipsis style={{ maxWidth: '100%' }}>
            {title}
          </Text>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 7 }}>
            {meta}
            <Tag style={{ margin: 0 }}>{relevanceLabel(score)}</Tag>
          </div>
        </div>
        <RightOutlined style={{ color: '#98a2b3', marginTop: 4 }} />
      </div>
      {excerpt && (
        <Paragraph
          type="secondary"
          style={{ margin: '9px 0 0', fontSize: 13, lineHeight: 1.65 }}
          ellipsis={{ rows: 3 }}
        >
          {excerpt}
        </Paragraph>
      )}
    </Card>
  )
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<GlobalSearchResult | null>(null)
  const [selected, setSelected] = useState<SearchPreview | null>(null)

  const doSearch = async (q: string) => {
    const text = q.trim()
    if (!text) return
    setLoading(true)
    setSelected(null)
    setParams({ q: text })
    try {
      const { data } = await searchApi.global(text, 8)
      setResult(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const q = params.get('q')
    if (q) doSearch(q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="fluid-page">
      <Input.Search
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onSearch={doSearch}
        placeholder="搜索文档、图片、记忆…"
        size="large"
        enterButton="搜索"
        allowClear
      />
      <Text type="secondary" style={{ display: 'block', margin: '8px 0 20px' }}>
        点击结果可在当前页面查看命中上下文和关联信息。
      </Text>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin />
        </div>
      ) : !result ? (
        <Empty description="输入关键词，一次搜遍知识库、图片与记忆" />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(18rem, 1fr))',
            gap: 16,
            alignItems: 'start',
          }}
        >
          <ResultColumn title="文档" icon={<FileTextOutlined />} count={result.documents.length}>
            {result.documents.map((hit) => (
              <SearchResultCard
                key={hit.chunk_id}
                title={hit.doc_name || '未命名文档'}
                score={hit.score}
                excerpt={hit.matched_content || hit.content}
                onOpen={() => setSelected({ kind: 'document', hit })}
              />
            ))}
          </ResultColumn>

          <ResultColumn title="图片" icon={<PictureOutlined />} count={result.images.length}>
            {result.images.map((hit) => (
              <SearchResultCard
                key={hit.chunk_id}
                title={hit.doc_name || '图片'}
                score={hit.score}
                excerpt={hit.matched_content || hit.content}
                onOpen={() => setSelected({ kind: 'image', hit })}
              />
            ))}
          </ResultColumn>

          <ResultColumn title="记忆" icon={<HddOutlined />} count={result.memories.length}>
            {result.memories.map((hit) => (
              <SearchResultCard
                key={hit.id}
                title={hit.name}
                score={hit.score}
                meta={
                  <>
                    <Tag color="blue" style={{ margin: 0 }}>{hit.type}</Tag>
                    <MemoryTrustTag confidence={hit.confidence} />
                  </>
                }
                excerpt={hit.description}
                onOpen={() => setSelected({ kind: 'memory', hit })}
              />
            ))}
          </ResultColumn>
        </div>
      )}

      <SearchResultDrawer
        selected={selected}
        onClose={() => setSelected(null)}
        onNavigate={(path) => {
          setSelected(null)
          navigate(path)
        }}
      />
    </div>
  )
}

function ResultColumn({
  title,
  icon,
  count,
  children,
}: {
  title: string
  icon: ReactNode
  count: number
  children: ReactNode
}) {
  return (
    <section aria-label={`${title}搜索结果`}>
      <div style={{ marginBottom: 12, fontWeight: 600, fontSize: 15 }}>
        {icon} {title} <Text type="secondary">({count})</Text>
      </div>
      {count === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无结果" />
      ) : (
        children
      )}
    </section>
  )
}
