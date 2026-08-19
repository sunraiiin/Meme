import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Alert,
  Button,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import {
  ArrowRightOutlined,
  FileTextOutlined,
  HddOutlined,
  PictureOutlined,
} from '@ant-design/icons'
import type { SearchHit } from '@/api/documents'
import { imageApi, type ImageItem } from '@/api/images'
import type { MemoryHit } from '@/api/memories'
import { AuthenticatedImage } from '@/components/AuthenticatedImage'

const { Paragraph, Text, Title } = Typography

export type SearchPreview =
  | { kind: 'document'; hit: SearchHit }
  | { kind: 'image'; hit: SearchHit }
  | { kind: 'memory'; hit: MemoryHit }

type Props = {
  selected: SearchPreview | null
  onClose: () => void
  onNavigate: (path: string) => void
}

function relevanceLabel(score: number): string {
  return `${Math.round(Math.max(0, Math.min(1, score)) * 100)}% 相关`
}

function memoryLayerLabel(layer?: string): string {
  return layer === 'long_term' ? '长期记忆' : '近期记忆'
}

function HighlightedContext({ context, matched }: { context: string; matched?: string }) {
  const parts = useMemo(() => {
    if (!matched || !context.includes(matched)) return null
    return context.split(matched)
  }, [context, matched])

  if (!parts || !matched) {
    return <>{context}</>
  }

  return (
    <>
      {parts.map((part, index) => (
        <span key={`${index}-${part.slice(0, 12)}`}>
          {part}
          {index < parts.length - 1 && (
            <mark
              style={{
                background: '#fff1b8',
                color: 'inherit',
                borderRadius: 4,
                padding: '2px 3px',
                boxDecorationBreak: 'clone',
              }}
            >
              {matched}
            </mark>
          )}
        </span>
      ))}
    </>
  )
}

function DrawerTitle({ selected }: { selected: SearchPreview }): ReactNode {
  const meta =
    selected.kind === 'document'
      ? { icon: <FileTextOutlined />, label: selected.hit.doc_name || '文档详情' }
      : selected.kind === 'image'
        ? { icon: <PictureOutlined />, label: selected.hit.doc_name || '图片详情' }
        : { icon: <HddOutlined />, label: selected.hit.name }

  return (
    <Space>
      {meta.icon}
      <span>{meta.label}</span>
      <Tag color="blue">{relevanceLabel(selected.hit.score)}</Tag>
    </Space>
  )
}

function DocumentPreview({ hit }: { hit: SearchHit }) {
  const exactMatch = Boolean(hit.matched_content && hit.content.includes(hit.matched_content))

  return (
    <div>
      <Title level={5}>相关上下文</Title>
      <Text type="secondary">黄色部分是本次搜索直接命中的内容。</Text>
      {!exactMatch && hit.matched_content && (
        <Alert
          type="info"
          showIcon
          message="命中内容"
          description={hit.matched_content}
          style={{ marginTop: 14 }}
        />
      )}
      <div
        style={{
          marginTop: 14,
          padding: 18,
          border: '1px solid #e4e7ec',
          borderRadius: 10,
          background: '#fcfcfd',
          whiteSpace: 'pre-wrap',
          lineHeight: 1.85,
          overflowWrap: 'anywhere',
        }}
      >
        <HighlightedContext context={hit.content} matched={hit.matched_content} />
      </div>
    </div>
  )
}

function ImagePreview({ hit }: { hit: SearchHit }) {
  const [detail, setDetail] = useState<ImageItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    setDetail(null)
    setError(null)
    if (!hit.source_id) {
      setError('该搜索结果缺少图片来源信息')
      return () => {
        active = false
      }
    }

    setLoading(true)
    imageApi
      .detail(hit.source_id)
      .then(({ data }) => {
        if (active) setDetail(data)
      })
      .catch((reason: unknown) => {
        if (active) setError((reason as Error)?.message || '图片详情加载失败')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [hit.source_id])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 64 }}>
        <Spin tip="正在加载图片详情" />
      </div>
    )
  }
  if (error) return <Alert type="error" showIcon message={error} />
  if (!detail) return <Empty description="没有可显示的图片详情" />

  return (
    <div>
      <div
        style={{
          minHeight: 220,
          maxHeight: 420,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          borderRadius: 12,
          background: '#f2f4f7',
        }}
      >
        <AuthenticatedImage
          src={detail.url}
          alt={detail.file_name}
          style={{ maxWidth: '100%', maxHeight: 420, objectFit: 'contain' }}
        />
      </div>
      <Descriptions column={1} size="small" style={{ marginTop: 18 }}>
        {detail.scene && <Descriptions.Item label="场景">{detail.scene}</Descriptions.Item>}
        {detail.objects?.length ? (
          <Descriptions.Item label="识别内容">
            <Space size={[4, 6]} wrap>
              {detail.objects.map((item) => <Tag key={item}>{item}</Tag>)}
            </Space>
          </Descriptions.Item>
        ) : null}
        {detail.tags.length ? (
          <Descriptions.Item label="标签">
            <Space size={[4, 6]} wrap>
              {detail.tags.map((tag) => <Tag key={tag.name} color={tag.color}>{tag.name}</Tag>)}
            </Space>
          </Descriptions.Item>
        ) : null}
      </Descriptions>
      <Divider />
      <Title level={5}>相关描述</Title>
      <Paragraph style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>
        {detail.description || hit.content || '暂无描述'}
      </Paragraph>
    </div>
  )
}

function MemoryPreview({ hit }: { hit: MemoryHit }) {
  const confidence = typeof hit.confidence === 'number' ? hit.confidence : 0.8

  return (
    <div>
      <Descriptions column={1} bordered size="small">
        <Descriptions.Item label="类型">{hit.type}</Descriptions.Item>
        <Descriptions.Item label="可信度">
          <Tag color={confidence >= 0.85 ? 'success' : confidence >= 0.75 ? 'processing' : 'warning'}>
            {Math.round(confidence * 100)}%
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="记忆阶段">
          {memoryLayerLabel(hit.memory_layer)}
        </Descriptions.Item>
        {hit.aliases.length ? (
          <Descriptions.Item label="其他称呼">
            <Space size={[4, 6]} wrap>
              {hit.aliases.map((alias) => <Tag key={alias}>{alias}</Tag>)}
            </Space>
          </Descriptions.Item>
        ) : null}
      </Descriptions>

      <Divider />
      <Title level={5}>记忆内容</Title>
      <Paragraph style={{ lineHeight: 1.8 }}>
        {hit.description || '该记忆暂时没有补充描述。'}
      </Paragraph>

      <Title level={5}>关联信息</Title>
      {hit.relations.length ? (
        <Space direction="vertical" size={10} style={{ width: '100%' }}>
          {hit.relations.map((relation, index) => (
            <div
              key={`${relation.predicate}-${relation.object_name}-${index}`}
              style={{ padding: 12, border: '1px solid #e4e7ec', borderRadius: 8 }}
            >
              <Space size={6} wrap>
                <Text strong>{hit.name}</Text>
                <Tag color="blue">{relation.predicate}</Tag>
                <Text>{relation.object_name || '未命名对象'}</Text>
                {relation.object_type && <Tag>{relation.object_type}</Tag>}
              </Space>
              {relation.source_text && (
                <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>
                  来源：{relation.source_text}
                </Paragraph>
              )}
            </div>
          ))}
        </Space>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无关联信息" />
      )}
    </div>
  )
}

export default function SearchResultDrawer({ selected, onClose, onNavigate }: Props) {
  const sourceAction = selected
    ? selected.kind === 'document'
      ? {
          label: '进入所属知识库',
          path: selected.hit.kb_id ? `/knowledge-bases/${selected.hit.kb_id}` : '/knowledge',
        }
      : selected.kind === 'image'
        ? {
            label: '在图片库查看',
            path: selected.hit.source_id ? `/images?image=${selected.hit.source_id}` : '/images',
          }
        : { label: '在记忆图谱查看', path: '/graph' }
    : null

  return (
    <Drawer
      title={selected ? <DrawerTitle selected={selected} /> : '搜索详情'}
      open={Boolean(selected)}
      onClose={onClose}
      width={720}
      extra={
        sourceAction && (
          <Button
            type="primary"
            icon={<ArrowRightOutlined />}
            onClick={() => onNavigate(sourceAction.path)}
          >
            {sourceAction.label}
          </Button>
        )
      }
    >
      {selected?.kind === 'document' && <DocumentPreview hit={selected.hit} />}
      {selected?.kind === 'image' && <ImagePreview hit={selected.hit} />}
      {selected?.kind === 'memory' && <MemoryPreview hit={selected.hit} />}
    </Drawer>
  )
}
