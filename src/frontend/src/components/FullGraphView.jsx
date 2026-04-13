/**
 * 全图谱组件 - 使用 Cytoscape.js
 * 展示包含所有节点和边的大图谱，支持按需高亮案例相关子图
 */
import React, { useEffect, useRef, useState } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import { Card, Select, Spin, Tag, Space, Button, message } from 'antd'
import { ClearOutlined } from '@ant-design/icons'
import { knowledgeApi, api } from '../services/api'

const FullGraphView = () => {
  const cyRef = useRef(null)
  const [loading, setLoading] = useState(false)
  const [graphData, setGraphData] = useState(null)
  const [selectedCase, setSelectedCase] = useState(null)
  const [caseOptions, setCaseOptions] = useState([])

  // Cytoscape 样式表
  const stylesheet = [
    // 默认节点样式（初始状态：所有节点正常显示）
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'width': 50,
        'height': 50,
        'font-size': 11,
        'text-valign': 'bottom',
        'text-margin-y': 5,
        'border-width': 2,
        'border-color': '#999',
        'opacity': 1,
        'transition-property': 'opacity, width, height, border-width',
        'transition-duration': '0.3s',
      },
    },
    // 节点类型颜色
    {
      selector: 'node[type="phenomenon"]',
      style: {
        'background-color': '#ff7875',
        'border-color': '#ff4d4f',
        'shape': 'ellipse',
      },
    },
    {
      selector: 'node[type="subsystem"]',
      style: {
        'background-color': '#69c0ff',
        'border-color': '#1890ff',
        'shape': 'round-rectangle',
      },
    },
    {
      selector: 'node[type="component"]',
      style: {
        'background-color': '#95de64',
        'border-color': '#52c41a',
        'shape': 'round-rectangle',
      },
    },
    {
      selector: 'node[type="parameter"]',
      style: {
        'background-color': '#ffc069',
        'border-color': '#fa8c16',
        'shape': 'diamond',
        'width': 40,
        'height': 40,
      },
    },
    {
      selector: 'node[type="rootcause"]',
      style: {
        'background-color': '#b37feb',
        'border-color': '#722ed1',
        'shape': 'triangle',
      },
    },
    // 淡化的节点（选择案例后非相关节点）
    {
      selector: 'node.faded',
      style: {
        'opacity': 0.2,
      },
    },
    // 高亮的路径节点（选择案例后相关节点，带蓝色边框）
    {
      selector: 'node.path-highlight',
      style: {
        'opacity': 1,
        'width': 60,
        'height': 60,
        'border-width': 4,
        'border-color': '#1890ff',
        'border-opacity': 1,
      },
    },
    {
      selector: 'node.path-highlight[type="parameter"]',
      style: {
        'width': 50,
        'height': 50,
      },
    },
    // 默认边样式
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': '#999',
        'target-arrow-color': '#999',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'opacity': 1,
        'arrow-scale': 0.8,
        'transition-property': 'opacity, width',
        'transition-duration': '0.3s',
      },
    },
    // 淡化的边
    {
      selector: 'edge.faded',
      style: {
        'opacity': 0.15,
        'width': 1,
      },
    },
    // 高亮的路径边
    {
      selector: 'edge.path-highlight',
      style: {
        'width': 4,
        'line-color': '#1890ff',
        'target-arrow-color': '#1890ff',
        'opacity': 1,
      },
    },
  ]

  // 布局配置
  const layout = {
    name: 'cose',
    animate: true,
    animationDuration: 500,
    animationEasing: 'ease-out',
    nodeRepulsion: 800000,
    idealEdgeLength: 100,
    nodeOverlap: 20,
    refresh: 20,
    fit: true,
    padding: 80,
    randomize: false,
    componentSpacing: 100,
    nodeDimensionsIncludeLabels: true,
  }

  useEffect(() => {
    fetchCaseOptions()
    fetchFullGraph()
  }, [])

  const fetchCaseOptions = async () => {
    try {
      const response = await knowledgeApi.getRecords()
      const options = response.data.map(record => ({
        label: `${record.case_id} - ${record.phenomenon}`,
        value: record.case_id,
      }))
      setCaseOptions(options)
    } catch (error) {
      message.error('获取案例列表失败: ' + error.message)
    }
  }

  const fetchFullGraph = async () => {
    setLoading(true)
    try {
      const response = await api.getFullGraph()
      const data = response.data

      // 转换为 Cytoscape 格式
      const elements = [
        ...data.nodes.map(node => ({
          data: {
            id: node.id,
            label: node.label,
            type: node.type,
            properties: node.properties,
            cases: node.cases,
          },
        })),
        ...data.edges.map(edge => ({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            relation: edge.relation,
            cases: edge.cases,
          },
        })),
      ]

      setGraphData({ elements, stats: data.stats })
    } catch (error) {
      message.error('加载图谱失败: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  const handleCaseSelect = async (caseId) => {
    if (!caseId) {
      clearHighlight()
      return
    }

    setSelectedCase(caseId)

    try {
      // 获取该案例相关的节点ID
      const response = await api.getSubgraph(caseId)
      const data = response.data

      if (cyRef.current) {
        const cy = cyRef.current

        // 清除之前的高亮
        cy.elements().removeClass('faded path-highlight')

        // 获取相关节点
        const pathNodes = cy.$(`#${data.node_ids.join(',#')}`)

        // 淡化所有元素
        cy.elements().addClass('faded')

        // 高亮路径上的节点（去除淡化，添加路径高亮）
        pathNodes.removeClass('faded').addClass('path-highlight')

        // 找到所有相关边（连接路径节点的边）
        const pathEdges = pathNodes.connectedEdges()
        pathEdges.removeClass('faded').addClass('path-highlight')

        // 适当放大查看（不要太近）
        cy.fit(pathNodes, 100)
      }
    } catch (error) {
      message.error('获取子图失败: ' + error.message)
    }
  }

  const clearHighlight = () => {
    setSelectedCase(null)

    if (cyRef.current) {
      const cy = cyRef.current
      // 移除所有高亮和淡化效果
      cy.elements().removeClass('faded path-highlight')
      // 适应整个图谱
      cy.fit()
    }
  }

  const handleNodeClick = (event) => {
    const node = event.target
    const data = node.data()

    message.info(`${data.label} (${data.type})`)
    console.log('节点数据:', data)
  }

  if (loading || !graphData) {
    return (
      <Card title="全量故障知识图谱">
        <div style={{ textAlign: 'center', padding: 60 }}>
          <Spin size="large" tip="加载全图谱中..." />
        </div>
      </Card>
    )
  }

  return (
    <Card
      title="全量故障知识图谱"
      extra={
        <Space>
          {graphData.stats && (
            <>
              <Tag color="blue">节点: {graphData.stats.total_nodes}</Tag>
              <Tag color="green">边: {graphData.stats.total_edges}</Tag>
              <Tag color="purple">案例: {graphData.stats.total_cases}</Tag>
            </>
          )}
        </Space>
      }
    >
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Select
            style={{ width: 400 }}
            placeholder="选择案例，高亮相关链路"
            value={selectedCase}
            onChange={handleCaseSelect}
            options={caseOptions}
            allowClear
            showSearch
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
          <Button
            icon={<ClearOutlined />}
            onClick={clearHighlight}
            disabled={!selectedCase}
          >
            清除高亮
          </Button>
        </Space>
      </div>

      <div style={{ height: 700, border: '1px solid #f0f0f0', borderRadius: 4 }}>
        <CytoscapeComponent
          elements={graphData.elements}
          stylesheet={stylesheet}
          layout={layout}
          style={{ width: '100%', height: '100%' }}
          cy={(cy) => {
            cyRef.current = cy

            // 节点点击事件
            cy.on('tap', 'node', handleNodeClick)

            // 节点悬浮事件
            cy.on('mouseover', 'node', (event) => {
              const node = event.target
              const data = node.data()
              console.log('悬浮节点:', data.label)
            })
          }}
        />
      </div>

      <div style={{ marginTop: 16, fontSize: 12, color: '#999' }}>
        <p>使用说明：</p>
        <ul style={{ paddingLeft: 20, margin: 0 }}>
          <li>初始状态所有节点正常显示</li>
          <li>选择案例后，只高亮相关链路（从现象到所有叶子节点），其他节点淡化</li>
          <li>点击节点查看详细信息</li>
          <li>拖拽节点调整位置</li>
          <li>滚轮缩放，右键拖拽平移</li>
        </ul>
      </div>
    </Card>
  )
}

export default FullGraphView
