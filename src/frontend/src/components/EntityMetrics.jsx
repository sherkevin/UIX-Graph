/**
 * 实体指标数据展示组件（仪表板）
 */
import React, { useState, useEffect } from 'react'
import { Row, Col, Statistic, Card, Spin } from 'antd'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'
import { propagationApi } from '../services/api'

const EntityMetrics = ({ entityId }) => {
  const [loading, setLoading] = useState(false)
  const [timeSeriesData, setTimeSeriesData] = useState(null)
  const [statistics, setStatistics] = useState(null)

  useEffect(() => {
    fetchMetricsData()
  }, [entityId])

  const fetchMetricsData = async () => {
    setLoading(true)
    try {
      const response = await propagationApi.getEntityTimeseries(entityId, '7d')
      const data = response.data

      // 转换为图表数据格式
      const chartData = data.timestamps.map((ts, index) => ({
        time: new Date(ts).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit' }),
        value: data.values[index],
        threshold: data.threshold,
      }))

      setTimeSeriesData(chartData)

      // 计算统计数据
      const values = data.values
      setStatistics({
        current: values[values.length - 1],
        min: Math.min(...values),
        max: Math.max(...values),
        avg: values.reduce((a, b) => a + b, 0) / values.length,
        unit: data.unit,
      })
    } catch (error) {
      console.error('获取指标数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading || !statistics) {
    return <Spin tip="加载指标数据..." />
  }

  return (
    <div>
      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="当前值"
              value={statistics.current}
              suffix={statistics.unit}
              valueStyle={{ color: '#1890ff', fontSize: 18 }}
              precision={1}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="平均值"
              value={statistics.avg}
              suffix={statistics.unit}
              valueStyle={{ fontSize: 18 }}
              precision={1}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="最大值"
              value={statistics.max}
              suffix={statistics.unit}
              valueStyle={{ color: '#cf1322', fontSize: 18 }}
              precision={1}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic
              title="最小值"
              value={statistics.min}
              suffix={statistics.unit}
              valueStyle={{ color: '#52c41a', fontSize: 18 }}
              precision={1}
            />
          </Card>
        </Col>
      </Row>

      {/* 趋势图 */}
      {timeSeriesData && (
        <Card size="small" title="7天趋势">
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={timeSeriesData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="time"
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip
                labelFormatter={(value) => `时间: ${value}`}
                formatter={(value, name) => [
                  `${value} ${statistics.unit}`,
                  name === 'value' ? '实际值' : '阈值'
                ]}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#1890ff"
                name="实际值"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
              {statistics.threshold && (
                <Line
                  type="monotone"
                  dataKey="threshold"
                  stroke="#f5222d"
                  name="阈值"
                  strokeDasharray="5 5"
                  dot={false}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}
    </div>
  )
}

export default EntityMetrics
