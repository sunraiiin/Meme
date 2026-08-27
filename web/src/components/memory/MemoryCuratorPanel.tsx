import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Divider,
  Empty,
  Input,
  List,
  Popconfirm,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  CheckCircleOutlined,
  HistoryOutlined,
  RedoOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import {
  memoryApi,
  type CurationAuditRecord,
  type CurationOperation,
  type CurationPlan,
  type CurationRisk,
} from '@/api/memories'

const { Text, Paragraph } = Typography
const { TextArea } = Input

const EXAMPLES = [
  '我叫林舟',
  '请把小舟作为我的另一个称呼',
  '移除我的别名小林',
  '保留后端开发工程师，合并后端工程师',
]

const KIND_LABEL: Record<CurationOperation['kind'], string> = {
  set_self_display_name: '设置本人名称',
  add_self_alias: '增加本人别名',
  remove_self_alias: '移除本人别名',
  correct_entity: '修正实体名称',
  merge_entities: '合并实体',
  invalidate_fact: '停止召回',
  forget_source: '忘记来源',
}

const STATUS_LABEL: Record<CurationAuditRecord['status'], string> = {
  confirmed: '已确认',
  executed: '已执行',
  failed: '失败',
  undone: '已撤销',
}

function riskMeta(risk: CurationRisk) {
  if (risk === 'high') return { label: '高风险', color: 'error' as const }
  if (risk === 'medium') return { label: '中风险', color: 'warning' as const }
  return { label: '低风险', color: 'success' as const }
}

function targetStatusLabel(status: CurationOperation['target_status']) {
  if (status === 'resolved') return '已找到目标'
  if (status === 'will_create') return '将创建或补全身份'
  if (status === 'not_found') return '未找到目标'
  if (status === 'ambiguous') return '找到多个同名目标'
  return '无需查找目标'
}

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function EntitySnapshotSummary({
  label,
  snapshot,
}: {
  label: string
  snapshot: Record<string, unknown>
}) {
  const name = typeof snapshot.name === 'string' ? snapshot.name : '未命名'
  const type = typeof snapshot.type === 'string' ? snapshot.type : '未分类'
  const description = typeof snapshot.description === 'string' ? snapshot.description : ''
  const aliases = Array.isArray(snapshot.aliases)
    ? snapshot.aliases.filter((item): item is string => typeof item === 'string')
    : []

  return (
    <div style={{ marginTop: 10, padding: '8px 10px', borderRadius: 6, background: '#fafafa' }}>
      <Space direction="vertical" size={2}>
        <Text>
          <Text strong>{label}：</Text>
          {name} <Text type="secondary">（{type}）</Text>
        </Text>
        {description && <Text type="secondary">{description}</Text>}
        {aliases.length > 0 && <Text type="secondary">别名：{aliases.join('、')}</Text>}
      </Space>
    </div>
  )
}

export default function MemoryCuratorPanel() {
  const [request, setRequest] = useState('')
  const [plan, setPlan] = useState<CurationPlan | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [executing, setExecuting] = useState(false)
  const [auditLoading, setAuditLoading] = useState(false)
  const [undoing, setUndoing] = useState<string | null>(null)
  const [audit, setAudit] = useState<CurationAuditRecord[]>([])

  const loadAudit = useCallback(async () => {
    setAuditLoading(true)
    try {
      const { data } = await memoryApi.curationAudit(30)
      setAudit(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setAuditLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAudit()
  }, [loadAudit])

  const preview = async () => {
    const value = request.trim()
    if (!value) {
      message.warning('请先描述你希望如何整理记忆')
      return
    }
    setPlanning(true)
    setConfirmed(false)
    try {
      const { data } = await memoryApi.curationPlan(value)
      setPlan(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setPlanning(false)
    }
  }

  const execute = async () => {
    if (!plan?.executable || plan.status !== 'ready' || !plan.confirmation_token) return
    if (plan.requires_confirmation && !confirmed) {
      message.warning('请先确认已经核对目标和影响范围')
      return
    }
    setExecuting(true)
    try {
      await memoryApi.curationExecute(plan, confirmed)
      message.success('记忆整理已执行')
      setPlan(null)
      setConfirmed(false)
      await loadAudit()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setExecuting(false)
    }
  }

  const undo = async (operationId: string) => {
    setUndoing(operationId)
    try {
      await memoryApi.curationUndo(operationId)
      message.success('已撤销这次记忆整理')
      await loadAudit()
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setUndoing(null)
    }
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message="先预览，再修改"
        description="记忆管家会把你的自然语言请求转换成白名单操作。预览阶段不会修改数据；目标、风险和影响确认无误后才会执行，并保留审计记录。"
      />

      <div>
        <Text strong>你希望怎样整理记忆？</Text>
        <TextArea
          value={request}
          onChange={(event) => {
            setRequest(event.target.value)
            setPlan(null)
            setConfirmed(false)
          }}
          placeholder="例如：请把小舟作为我的另一个称呼"
          autoSize={{ minRows: 3, maxRows: 6 }}
          maxLength={2000}
          showCount
          style={{ marginTop: 8 }}
        />
        <Space wrap size={[8, 8]} style={{ marginTop: 12 }}>
          {EXAMPLES.map((item) => (
            <Button
              key={item}
              size="small"
              onClick={() => {
                setRequest(item)
                setPlan(null)
                setConfirmed(false)
              }}
            >
              {item}
            </Button>
          ))}
          <Button
            type="primary"
            icon={<RobotOutlined />}
            loading={planning}
            onClick={preview}
          >
            生成整理预览
          </Button>
        </Space>
      </div>

      {plan && <PlanPreview plan={plan} confirmed={confirmed} onConfirm={setConfirmed} onExecute={execute} executing={executing} />}

      <Divider style={{ margin: '4px 0' }} />

      <div>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <HistoryOutlined />
            <Text strong>最近整理记录</Text>
          </Space>
          <Button size="small" icon={<RedoOutlined />} onClick={loadAudit}>
            刷新
          </Button>
        </Space>
        <Spin spinning={auditLoading}>
          <List
            style={{ marginTop: 8 }}
            dataSource={audit}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有整理记录" /> }}
            renderItem={(item) => {
              const risk = riskMeta(item.risk)
              const canUndo = item.status === 'executed' && item.operation_kind !== 'merge_entities'
              return (
                <List.Item
                  actions={canUndo ? [
                    <Popconfirm
                      key="undo"
                      title="撤销这次整理？"
                      description="系统会按照执行前快照恢复可逆字段。"
                      okText="撤销"
                      cancelText="取消"
                      onConfirm={() => undo(item.operation_id)}
                    >
                      <Button size="small" loading={undoing === item.operation_id}>撤销</Button>
                    </Popconfirm>,
                  ] : undefined}
                >
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <span>{KIND_LABEL[item.operation_kind]}</span>
                        <Tag color={risk.color}>{risk.label}</Tag>
                        <Tag color={item.status === 'executed' ? 'success' : item.status === 'failed' ? 'error' : 'default'}>
                          {STATUS_LABEL[item.status]}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={2}>
                        <Text>{item.request}</Text>
                        <Text type="secondary">{formatTime(item.executed_at || item.created_at)}</Text>
                        {item.error && <Text type="danger">{item.error}</Text>}
                        {item.operation_kind === 'merge_entities' && item.status === 'executed' && (
                          <Text type="secondary">实体合并暂不支持自动撤销，可根据审计快照人工处理。</Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )
            }}
          />
        </Spin>
      </div>
    </Space>
  )
}

function PlanPreview({
  plan,
  confirmed,
  onConfirm,
  onExecute,
  executing,
}: {
  plan: CurationPlan
  confirmed: boolean
  onConfirm: (value: boolean) => void
  onExecute: () => void
  executing: boolean
}) {
  const risk = riskMeta(plan.risk)
  const rejected = plan.status === 'rejected'
  return (
    <Card
      size="small"
      title="整理预览"
      extra={
        <Space wrap>
          <Tag color={plan.planner_source === 'rules' ? 'blue' : 'purple'}>
            {plan.planner_source === 'rules' ? '规则解析' : '语义解析'}
          </Tag>
          {!rejected && <Tag color={risk.color}>{risk.label}</Tag>}
        </Space>
      }
    >
      <Alert
        type={rejected ? 'warning' : plan.executable ? 'success' : 'error'}
        showIcon
        message={plan.message}
      />

      {plan.blocking_reasons.length > 0 && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 12 }}
          message="当前计划不能执行"
          description={plan.blocking_reasons.join('；')}
        />
      )}

      {plan.operations.map((operation) => {
        const operationRisk = riskMeta(operation.risk)
        return (
          <Card key={operation.operation_id} size="small" style={{ marginTop: 12 }}>
            <Space wrap>
              <Tag>{KIND_LABEL[operation.kind]}</Tag>
              <Tag color={operationRisk.color}>{operationRisk.label}</Tag>
              <Tag color={operation.target_status === 'not_found' || operation.target_status === 'ambiguous' ? 'error' : 'processing'}>
                {targetStatusLabel(operation.target_status)}
              </Tag>
            </Space>
            <Paragraph style={{ margin: '10px 0 4px' }}>{operation.summary}</Paragraph>
            {operation.reason && <Text type="secondary">解析依据：{operation.reason}</Text>}
            {operation.target_snapshot && (
              <EntitySnapshotSummary label="当前目标" snapshot={operation.target_snapshot} />
            )}
            {operation.secondary_target_snapshot && (
              <EntitySnapshotSummary label="将被合并的目标" snapshot={operation.secondary_target_snapshot} />
            )}
          </Card>
        )
      })}

      {!rejected && plan.executable && (
        <Space direction="vertical" size={10} style={{ width: '100%', marginTop: 14 }}>
          {plan.requires_confirmation && (
            <Checkbox checked={confirmed} onChange={(event) => onConfirm(event.target.checked)}>
              我已核对目标和影响范围，确认执行这项整理
            </Checkbox>
          )}
          <Space wrap>
            <Button
              type="primary"
              danger={plan.risk === 'high'}
              icon={<CheckCircleOutlined />}
              loading={executing}
              disabled={plan.requires_confirmation && !confirmed}
              onClick={onExecute}
            >
              确认执行
            </Button>
            <Text type="secondary">计划有效期至 {formatTime(plan.expires_at)}</Text>
          </Space>
        </Space>
      )}
    </Card>
  )
}
