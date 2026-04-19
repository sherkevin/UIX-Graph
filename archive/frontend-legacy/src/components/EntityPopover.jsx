/**
 * 实体详情悬浮卡片
 */
import React, { useState, useEffect } from 'react'
import { Popover, Descriptions, Tag, Spin, Empty, Tabs, Button } from 'antd'
import { LineChartOutlined, HistoryOutlined, DashboardOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { propagationApi } from '../services/api'
import EntityMetrics from './EntityMetrics'

const { TabPane } = Tabs

const EntityPopover = ({ entityId, visible, onVisibleChange, children }) => {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [entityData, setEntityData] = useState(null)

  useEffect(() => {
    if (visible && entityId) {
      fetchEntityDetail()
    }
  }, [visible, entityId])

  const fetchEntityDetail = async () => {
    setLoading(true)
    try {
      const response = await propagationApi.getEntityDetail(entityId)
      setEntityData(response.data)
    } catch (error) {
      console.error('获取实体详情失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const getTypeColor = (type) => {
    const colorMap = {
      phenomenon: 'red',
      subsystem: 'blue',
      component: 'green',
      parameter: 'orange',
      rootcause: 'purple',
    }
    return colorMap[type] || 'default'
  }

  const renderContent = () => {
    if (loading) {
      return <Spin size="small" />
    }

    if (!entityData) {
      return <Empty description="暂无数据" image={null} />
    }

    const handleViewDetails = () => {
      // 关闭 popover 并导航到详情页面
      onVisibleChange(false)
      navigate(`/entity/${encodeURIComponent(entityId)}`)
    }

    return (
      <div style={{ width: 500 }}>
        <Tabs defaultActiveKey="basic" size="small">
          <TabPane tab="基本信息" key="basic">
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="类型">
                <Tag color={getTypeColor(entityData.type)}>
                  {entityData.type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="名称" span={1}>
                {entityData.label}
              </Descriptions.Item>

              {/* 动态属性 */}
              {entityData.properties && Object.entries(entityData.properties).map(([key, value]) => (
                <Descriptions.Item label={key} key={key}>
                  {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </Descriptions.Item>
              ))}

              <Descriptions.Item label="相关案例">
                {entityData.related_cases.map(caseId => (
                  <Tag key={caseId}>{caseId}</Tag>
                ))}
              </Descriptions.Item>
            </Descriptions>
          </TabPane>

          {/* 指标数据Tab（仅参数和部件显示） */}
          {(entityData.type === 'parameter' || entityData.type === 'component') && (
            <TabPane tab={<span><LineChartOutlined /> 指标数据</span>} key="metrics">
              <div>
                <EntityMetrics entityId={entityId} />
                <div style={{ marginTop: 16, textAlign: 'center' }}>
                  <Button
                    type="primary"
                    icon={<DashboardOutlined />}
                    onClick={handleViewDetails}
                    size="small"
                  >
                    查看完整 Dashboard
                  </Button>
                </div>
              </div>
            </TabPane>
          )}

          {/* 传播时间线 */}
          <TabPane tab={<span><HistoryOutlined /> 传播路径</span>} key="timeline">
            <div style={{ maxHeight: 300, overflow: 'auto' }}>
              <Empty description="请查看图谱中的完整传播路径" image={null} />
            </div>
          </TabPane>
        </Tabs>
      </div>
    )
  }

  return (
    <Popover
      content={renderContent()}
      title={entityData?.label || '实体详情'}
      trigger="click"
      visible={visible}
      onVisibleChange={onVisibleChange}
      placement="right"
      overlayStyle={{ maxWidth: 600 }}
    >
      {children}
    </Popover>
  )
}

export default EntityPopover
