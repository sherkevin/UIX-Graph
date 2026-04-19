/**
 * 故障传播图谱组件 - 使用G6 v5
 */
import React, { useEffect, useRef, useState } from 'react'
import { Graph } from '@antv/g6'
import { Card, Spin, Tag, Space, message } from 'antd'
import { propagationApi } from '../services/api'

const FaultPropagationGraph = ({ caseId, onNodeClick, onGraphReady }) => {
  const containerRef = useRef(null)
  const graphRef = useRef(null)
  const [loading, setLoading] = useState(false)
  const [pathInfo, setPathInfo] = useState(null)

  useEffect(() => {
    if (caseId && containerRef.current) {
      initGraph()
      fetchAndRenderGraph()
    }

    return () => {
      if (graphRef.current) {
        graphRef.current.destroy()
      }
    }
  }, [caseId])

  const initGraph = () => {
    const width = containerRef.current.clientWidth
    const height = 600

    const graph = new Graph({
      container: containerRef.current,
      width,
      height,
      layout: {
        type: 'dagre',
        rankdir: 'LR',
        nodesep: 50,
        ranksep: 100,
      },
      node: {
        style: {
          size: 60,
          lineWidth: 2,
        },
      },
      edge: {
        type: 'polyline',
        style: {
          stroke: '#999',
          lineWidth: 2,
          endArrow: true,
        },
      },
    })

    // 节点点击事件
    graph.on('node:click', (evt) => {
      const { itemId } = evt
      const node = graph.getNodeData(itemId)

      // 清除之前的选中状态
      const allNodes = graph.getNodeData()
      if (allNodes) {
        allNodes.forEach(n => {
          graph.updateNodeData([{
            id: n.id,
            style: {
              ...n.style,
              halo: false,
              lineWidth: 2,
            }
          }])
        })
      }

      // 高亮当前节点
      graph.updateNodeData([{
        id: itemId,
        style: {
          halo: true,
          haloColor: '#f5222d',
          haloLineWidth: 4,
          lineWidth: 4,
          stroke: '#f5222d',
        }
      }])

      // 触发回调
      if (onNodeClick) {
        onNodeClick(node, evt.originalEvent)
      }
    })

    graphRef.current = graph
  }

  const fetchAndRenderGraph = async () => {
    setLoading(true)
    try {
      const response = await propagationApi.getPropagationPath(caseId)
      const pathData = response.data

      setPathInfo(pathData)

      // 转换为G6 v5数据格式
      const nodes = pathData.nodes.map(node => {
        const baseStyle = {
          fill: getNodeColor(node.type),
          stroke: getNodeColor(node.type),
          lineWidth: 2,
        }

        // 根据节点类型设置不同形状
        let nodeType = 'circle'
        if (node.type === 'subsystem' || node.type === 'component') {
          nodeType = 'rect'
        } else if (node.type === 'parameter') {
          nodeType = 'ellipse'
        } else if (node.type === 'rootcause') {
          nodeType = 'triangle'
        }

        return {
          id: node.id,
          data: node,
          label: node.label,
          type: nodeType,
          style: baseStyle,
          labelCfg: {
            style: {
              fill: '#fff',
              fontSize: 11,
            },
            position: 'bottom',
          }
        }
      })

      // 如果有故障节点，添加红色高亮
      if (pathData.fault_node) {
        const faultNodeIndex = nodes.findIndex(n => n.id === pathData.fault_node)
        if (faultNodeIndex >= 0) {
          nodes[faultNodeIndex].style = {
            ...nodes[faultNodeIndex].style,
            halo: true,
            haloColor: '#ff0000',
            haloLineWidth: 6,
            lineWidth: 4,
            stroke: '#ff0000',
          }
        }
      }

      const edges = pathData.edges.map((edge, index) => ({
        id: `edge-${index}`,
        source: edge.source,
        target: edge.target,
        data: { label: edge.label },
        label: edge.label,
        style: {
          labelBackgroundColor: '#fff',
          labelBackgroundFill: '#fff',
          labelBackgroundOpacity: 0.8,
          labelPlacement: 'center',
        }
      }))

      const graph = graphRef.current

      // 使用G6 v5的setData方法
      graph.setData({ nodes, edges })
      await graph.render()

      // 通知父组件图谱已准备就绪
      if (onGraphReady) {
        onGraphReady({
          graph,
          faultNodeId: pathData.fault_node,
          pathData
        })
      }

    } catch (error) {
      console.error('Graph rendering error:', error)
      message.error('加载图谱失败: ' + error.message)
    } finally {
      setLoading(false)
    }
  }

  const getNodeColor = (type) => {
    const colorMap = {
      phenomenon: '#ff7875',  // 红色 - 故障现象
      subsystem: '#69c0ff',
      component: '#95de64',
      parameter: '#ffc069',
      rootcause: '#b37feb',
    }
    return colorMap[type] || '#d9d9d9'
  }

  return (
    <Card
      title="故障传播路径"
      extra={
        pathInfo && (
          <Space>
            <Tag color="blue">置信度: {pathInfo.confidence}%</Tag>
            <Tag color="green">路径长度: {pathInfo.path.length}</Tag>
            {pathInfo.fault_node && <Tag color="red">故障节点已高亮</Tag>}
          </Space>
        )
      }
    >
      <Spin spinning={loading}>
        <div ref={containerRef} style={{ width: '100%', height: 600, border: '1px solid #f0f0f0' }} />
      </Spin>
    </Card>
  )
}

export default FaultPropagationGraph
