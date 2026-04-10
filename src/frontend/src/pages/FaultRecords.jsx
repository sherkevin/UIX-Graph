import React, { useState, useEffect, useRef, useMemo } from 'react'
import { Table, Button, Modal, message, Row, Col, Select, DatePicker, Tag, TreeSelect, Alert } from 'antd'
import { rejectErrorsAPI, extractErrorMessage } from '../services/api'
import dayjs from 'dayjs'
import CustomSelect from '../components/CustomSelect'
import './FaultRecords.css'

const { RangePicker } = DatePicker
const { Option } = Select
const METRIC_PAGE_SIZE = 20

// ── 时间格式化工具 ─────────────────────────────────────────────────────────
// 后端统一返回 13 位毫秒时间戳，使用 dayjs(ms) 而非 dayjs.unix(s)
const formatTimestamp = (ts) => (ts ? dayjs(ts).format('YYYY-MM-DD HH:mm:ss') : '-')

const mixedSort = (a, b) => {
  const aNum = Number(a)
  const bNum = Number(b)
  const aIsNum = Number.isFinite(aNum) && String(aNum) === String(a)
  const bIsNum = Number.isFinite(bNum) && String(bNum) === String(b)

  if (aIsNum && bIsNum) return aNum - bNum
  return String(a).localeCompare(String(b), 'zh-Hans-CN', { numeric: true, sensitivity: 'base' })
}

const formatMetricValue = (value) => {
  if (value === null || value === undefined || value === '') return '-'
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  if (Number.isInteger(n)) return String(n)
  return parseFloat(n.toPrecision(6)).toString()
}

const FaultRecords = () => {
  const [records, setRecords] = useState([])
  /**
   * metadata 内部结构（前端适配后）:
   *   availableMachines : string[]          — 机台列表（后端枚举白名单）
   *   availableChucks   : number[]          — Chuck ID 列表
   *   chuckLotMap       : { [chuckId]: number[] }   — Chuck → Lot ID 列表
   *   lotWaferMap       : { [lotId]:   number[] }   — Lot → Wafer ID 列表
   *   lotNameMap        : { [lotId]:   string  }    — Lot ID → Lot 名称
   */
  const [metadata, setMetadata] = useState({
    availableMachines: [],
    availableChucks: [],
    chuckLotMap: {},
    lotWaferMap: {},
    lotNameMap: {},
  })
  const [loading, setLoading] = useState(false)
  const [metadataLoading, setMetadataLoading] = useState(false)
  const [selectedMachine, setSelectedMachine] = useState(undefined)
  const [dateRange, setDateRange] = useState(null)
  const [selectedChucks, setSelectedChucks] = useState([])
  const [selectedLotWaferKeys, setSelectedLotWaferKeys] = useState([])
  const [pagination, setPagination] = useState({
    pageNo: 1,
    pageSize: 20,
    total: 0,
  })
  const [detailVisible, setDetailVisible] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState(null)
  const [metricPage, setMetricPage] = useState(1)
  const [metricTotal, setMetricTotal] = useState(0)
  const [sortConfig, setSortConfig] = useState({ sortedBy: 'time', orderedBy: 'desc' })

  const didInit = useRef(false)
  const filterReady = useRef(false)
  // 标记当前元数据所属机台，切机台时先置 null，刷新完成后再置新机台
  // fetchRecords 在 metadataMachine !== selectedMachine 时跳过，避免用旧 lot 过滤新机台
  const metadataMachine = useRef(null)
  // 竞态保护：只有最新一次 fetchRecords / refreshMetadata 请求可以写入结果
  const latestFetchId = useRef(0)
  const latestMetaId = useRef(0)

  /**
   * 将后端返回的嵌套元数据结构适配为前端所需的扁平结构
   *
   * 后端返回：
   *   data: [{ chuckId, chuckName, availableLots: [{ lotId, lotName, availableWafers: [1,3,5] }] }]
   *
   * 前端需要：
   *   availableChucks : [1, 2, ...]
   *   chuckLotMap     : { 1: [101, 102], 2: [201] }
   *   lotWaferMap     : { 101: [1,3,5], 102: [2,4] }
   *   lotNameMap      : { 101: 'Lot 0101', 102: 'Lot 0102' }
   */
  const adaptMetadata = (rawChucks) => {
    const availableChucks = []
    const chuckLotMap = {}
    const lotWaferMap = {}
    const lotNameMap = {}

    rawChucks.forEach((chuck) => {
      availableChucks.push(chuck.chuckId)
      chuckLotMap[chuck.chuckId] = chuck.availableLots.map((l) => l.lotId)
      chuck.availableLots.forEach((lot) => {
        lotWaferMap[lot.lotId] = lot.availableWafers
        lotNameMap[lot.lotId] = lot.lotName
      })
    })

    return { availableChucks, chuckLotMap, lotWaferMap, lotNameMap }
  }

  /**
   * 获取筛选元数据（接口 1）
   * 传入 equipment + startTime/endTime，动态获取该条件下的 Chuck/Lot/Wafer
   * 不同机台 + 时间下的下拉选项是不同的
   */
  const fetchMetadata = async (equipment, startTime = null, endTime = null) => {
    const response = await rejectErrorsAPI.getMetadata(equipment, startTime, endTime)
    const rawChucks = response?.data?.data || []
    const adapted = adaptMetadata(rawChucks)
    return adapted
  }

  const normalizeRecord = (row) => {
    const waferIndex = row?.waferIndex ?? row?.waferId ?? row?.wafer_id ?? null
    return {
      ...row,
      chuckId: row?.chuckId ?? row?.chuck_id ?? row?.chuck ?? null,
      lotId: row?.lotId ?? row?.lot_id ?? row?.lot ?? null,
      waferIndex,
    }
  }

  // ── 根据已选 Chuck 过滤可见的 Lot/Wafer ──────────────────────────────────
  const linkedLotWaferMap = useMemo(() => {
    if (!selectedChucks.length) return metadata.lotWaferMap || {}
    const lots = {}
    selectedChucks.forEach((chuck) => {
      const chuckLots = metadata.chuckLotMap?.[chuck] || []
      chuckLots.forEach((lot) => {
        lots[lot] = metadata.lotWaferMap?.[lot] || []
      })
    })
    return lots
  }, [selectedChucks, metadata.chuckLotMap, metadata.lotWaferMap])

  const allWaferLeafKeys = useMemo(() => {
    const keys = []
    Object.entries(linkedLotWaferMap).forEach(([lot, wafers]) => {
      wafers.forEach((wafer) => keys.push(`wafer|${lot}|${wafer}`))
    })
    return keys
  }, [linkedLotWaferMap])

  const selectedFilters = useMemo(() => {
    const selected = new Set(selectedLotWaferKeys)
    const lots = []
    const wafers = new Set()

    Object.entries(linkedLotWaferMap).forEach(([lot, lotWafers]) => {
      const selectedInLot = lotWafers.filter((wafer) => selected.has(`wafer|${lot}|${wafer}`))
      if (selectedInLot.length > 0) {
        lots.push(lot)
        selectedInLot.forEach((wafer) => wafers.add(wafer))
      }
    })

    return {
      lots: lots.sort(mixedSort),
      wafers: Array.from(wafers).sort(mixedSort),
    }
  }, [selectedLotWaferKeys, linkedLotWaferMap])

  /**
   * 查询拒片故障记录（接口 2）
   * Bug #2 已修复：payload 字段名 equipment（非 machine）
   * Bug #4 已修复：时间戳使用 dayjs.valueOf() 返回 13 位毫秒（非 unix() 10 位秒）
   */
  const fetchRecords = async (pageNo = pagination.pageNo, pageSize = pagination.pageSize) => {
    // 未选时间范围时不发请求，避免全表扫描
    if (!dateRange?.[0] || !dateRange?.[1]) {
      setRecords([])
      setPagination((prev) => ({ ...prev, pageNo: 1, total: 0 }))
      return
    }
    // 竞态保护：记录本次请求 ID，若有更新请求发出则丢弃本次结果
    const fetchId = ++latestFetchId.current
    setLoading(true)
    try {
      const payload = {
        pageNo,
        pageSize,
        equipment: selectedMachine || null,
        chucks: selectedChucks.length > 0 ? selectedChucks : null,
        lots: selectedFilters.lots.length > 0 ? selectedFilters.lots : null,
        wafers: selectedFilters.wafers.length > 0 ? selectedFilters.wafers : null,
        startTime: dateRange[0].valueOf(),
        endTime: dateRange[1].valueOf(),
        sortedBy: sortConfig.sortedBy,
        orderedBy: sortConfig.orderedBy,
      }
      const response = await rejectErrorsAPI.search(payload)
      if (fetchId !== latestFetchId.current) return  // 已被更新请求覆盖，丢弃
      const rows = (response?.data?.data || []).map(normalizeRecord)
      const meta = response?.data?.meta || {}
      setRecords(rows)
      setPagination({
        pageNo: meta.pageNo || pageNo,
        pageSize: meta.pageSize || pageSize,
        total: meta.total || 0,
      })
    } catch (error) {
      if (fetchId !== latestFetchId.current) return
      message.error({ content: `获取故障记录失败：${extractErrorMessage(error)}`, key: 'records-load-error' })
    } finally {
      if (fetchId === latestFetchId.current) setLoading(false)
    }
  }

  // ── 初始化：加载元数据 → 设置默认筛选 → 查询记录 ─────────────────────────
  useEffect(() => {
    if (didInit.current) return
    didInit.current = true

    const init = () => {
      // 初始化只设机台列表，不自动拉数据
      // 用户需先选机台 + 时间范围，才会触发 refreshMetadata 和 fetchRecords
      setMetadata((prev) => ({
        ...prev,
        availableMachines: ['SSB8000', 'SSB8001', 'SSB8002', 'SSB8005',
          'SSC8001', 'SSC8002', 'SSC8003', 'SSC8004', 'SSC8005', 'SSC8006'],
      }))
      filterReady.current = true
      setLoading(false)
    }

    init()
  }, [])

  /**
   * 切换机台或时间范围时，重新调用 fetchMetadata 更新 Chuck/Lot/Wafer 下拉
   * 不同机台 + 时间下的可选项是动态的
   */
  useEffect(() => {
    if (!filterReady.current || !selectedMachine) return
    // 未选时间范围：清空元数据下拉，不发请求，等待用户选时间
    if (!dateRange?.[0] || !dateRange?.[1]) {
      setMetadata((prev) => ({ ...prev, availableChucks: [], chuckLotMap: {}, lotWaferMap: {}, lotNameMap: {} }))
      setSelectedChucks([])
      setSelectedLotWaferKeys([])
      metadataMachine.current = selectedMachine
      return
    }

    const refreshMetadata = async () => {
      // 标记元数据正在刷新（机台已变更但元数据尚未更新）
      metadataMachine.current = null
      const metaId = ++latestMetaId.current
      setMetadataLoading(true)
      try {
        const startTime = dateRange[0].valueOf()
        const endTime = dateRange[1].valueOf()
        const adapted = await fetchMetadata(selectedMachine, startTime, endTime)
        if (metaId !== latestMetaId.current) return  // 已被更新的 refreshMetadata 覆盖，丢弃
        const allKeys = []
        Object.entries(adapted.lotWaferMap).forEach(([lot, wafers]) => {
          wafers.forEach((wafer) => allKeys.push(`wafer|${lot}|${wafer}`))
        })
        setMetadata((prev) => ({ ...prev, ...adapted }))
        // 不自动全选：空 = 不过滤，避免大量 wafer key 塞入 POST body 导致卡死
        setSelectedChucks([])
        setSelectedLotWaferKeys([])
        // 元数据已就绪，解除守卫
        metadataMachine.current = selectedMachine
      } catch (error) {
        if (metaId !== latestMetaId.current) return
        metadataMachine.current = selectedMachine
        message.error(`刷新筛选元数据失败：${extractErrorMessage(error)}`)
      } finally {
        if (metaId === latestMetaId.current) setMetadataLoading(false)
      }
    }

    refreshMetadata()
  }, [selectedMachine, dateRange]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── 不再自动触发 fetchRecords ──────────────────────────────────────────────
  // 改为用户点击"查询"按钮手动触发，消除级联竞态，防止大数据量下自动全扫

  // Chuck 变化时，清理不再属于新 Chuck 范围的 Lot/Wafer 选中项
  // 注意：不再自动全选——空选 = 不过滤，POST body 保持小
  useEffect(() => {
    if (!filterReady.current) return
    const validSet = new Set(allWaferLeafKeys)
    const next = selectedLotWaferKeys.filter((key) => validSet.has(key))
    if (next.length !== selectedLotWaferKeys.length) {
      setSelectedLotWaferKeys(next)
    }
  }, [allWaferLeafKeys]) // eslint-disable-line react-hooks/exhaustive-deps

  const lotWaferTreeData = useMemo(() => (
    Object.entries(linkedLotWaferMap).map(([lot, wafers]) => ({
      title: metadata.lotNameMap?.[lot] || `Lot ${lot}`,
      value: `lot|${lot}`,
      key: `lot|${lot}`,
      selectable: false,
      children: wafers.map((wafer) => ({
        title: `Wafer ID ${wafer}`,
        value: `wafer|${lot}|${wafer}`,
        key: `wafer|${lot}|${wafer}`,
      })),
    }))
  ), [linkedLotWaferMap, metadata.lotNameMap])

  const lotWaferSummary = useMemo(() => {
    const selected = new Set(selectedLotWaferKeys)
    const selectedWaferCount = selectedLotWaferKeys.length
    let fullLotCount = 0
    Object.entries(linkedLotWaferMap).forEach(([lot, wafers]) => {
      const allInLot = wafers.length > 0 && wafers.every((wafer) => selected.has(`wafer|${lot}|${wafer}`))
      if (allInLot) fullLotCount += 1
    })
    return `${fullLotCount} Lot / ${selectedWaferCount} Wafer`
  }, [selectedLotWaferKeys, linkedLotWaferMap])

  /**
   * 获取故障详情（接口 3）
   * Bug #6  已修复：errorField fallback 使用 record.rootCause（非 record.errorReason）
   * Bug #9  已修复：totalMetrics 从 response.data.meta.total 读取（非 data.totalMetrics）
   * Bug #10 已修复：直接使用后端返回的 status 和排序，不再客户端重算
   * Bug #12 已修复：Modal 翻页时携带 pageNo/pageSize 参数，使用服务端分页
   */
  const openDetail = async (record, pageNo = 1) => {
    setDetailVisible(true)
    setDetailLoading(true)
    setMetricPage(pageNo)
    try {
      const response = await rejectErrorsAPI.getMetrics(
        record.id,
        pageNo,
        METRIC_PAGE_SIZE,
        record.time ?? null,
      )
      const data = response?.data?.data || {}
      const meta = response?.data?.meta || {}

      // Bug #10 fix: 直接使用后端已排序的 metrics，不重新计算 status，不重新排序
      const metrics = data.metrics || []

      setDetailData({
        id: record.id,
        record,                                           // 保留原始 record 用于翻页
        errorField: data.errorField || '-',
        time: data.time || record.time,
        rootCause: data.rootCause || null,
        system: data.system || null,
        metrics,
        metricsMeta: meta,
      })

      // 详情接口返回了最新诊断结果后，立即回填主页表格当前行，
      // 避免用户必须手动刷新或重新筛选才能看到 rootCause/system。
      if (data.rootCause || data.system) {
        setRecords((prev) => prev.map((row) => (
          row.id === record.id
            ? {
                ...row,
                rootCause: data.rootCause ?? row.rootCause,
                system: data.system ?? row.system,
              }
            : row
        )))
      }
      // 后端 meta.metricDiagnosticTotal：全量诊断指标数（分页仅切诊断类；建模参数每页全量附带）
      const diagTotal = meta.metricDiagnosticTotal ?? (data.metrics || []).filter(m => m.type !== 'model_param').length
      setMetricTotal(diagTotal)
    } catch (error) {
      message.error(`获取详情失败：${extractErrorMessage(error)}`)
      setDetailVisible(false)
    } finally {
      setDetailLoading(false)
    }
  }

  // 指标分页翻页（服务端分页）
  const handleMetricPageChange = (page) => {
    if (detailData?.record) {
      openDetail(detailData.record, page)
    }
  }

  const closeDetail = () => {
    setDetailVisible(false)
    // openDetail 已经把 rootCause/system 回填到 records 里了，不需要重新查询
  }

  // ── 表格列定义 ─────────────────────────────────────────────────────────
  const columns = [
    {
      title: 'Chuck',
      dataIndex: 'chuckId',          // Bug #5 fix: chuck → chuckId
      key: 'chuckId',
      width: 90,
    },
    {
      title: 'Lot Id',
      dataIndex: 'lotId',
      key: 'lotId',
      width: 90,
    },
    {
      title: 'Wafer Index',
      dataIndex: 'waferIndex',
      key: 'waferIndex',
      width: 110,
    },
    {
      title: '拒片时间',
      dataIndex: 'time',
      key: 'time',
      width: 170,
      sorter: true,
      sortOrder: sortConfig.sortedBy === 'time' ? (sortConfig.orderedBy === 'asc' ? 'ascend' : 'descend') : null,
      render: (time) => formatTimestamp(time),
    },
    {
      title: '拒片现象',
      dataIndex: 'rejectReason',
      key: 'rejectReason',
      width: 160,
      sorter: true,
      sortOrder: sortConfig.sortedBy === 'reason' ? (sortConfig.orderedBy === 'asc' ? 'ascend' : 'descend') : null,
      render: (reason) => reason || '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      render: (_, record) => (
        <Button type="link" onClick={() => openDetail(record)}>
          详情
        </Button>
      ),
    },
  ]

  const metricColumns = [
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status) => (
        <Tag color={status === 'ABNORMAL' ? 'red' : status === 'UNKNOWN' ? 'default' : 'green'}>
          {status}
        </Tag>
      ),
    },
    {
      title: '指标名',
      dataIndex: 'name',
      key: 'name',
      width: 220,
    },
    {
      title: '指标值',
      key: 'value',
      width: 160,
      render: (_, row) => `${row.approximate ? '~' : ''}${formatMetricValue(row.value)} ${row.unit || ''}`.trim(),
    },
    {
      title: '阈值条件',
      key: 'threshold',
      width: 180,
      render: (_, row) => {
        const threshold = row.threshold || {}
        if (threshold.display) return threshold.display
        const op = threshold.operator || '-'
        // operator="-" 表示该指标在规则中无阈值定义，直接显示 "--"
        if (op === '-') return '--'
        const unit = threshold.unit || ''
        let limitStr = ''
        if (threshold.limit !== undefined && threshold.limit !== null) {
          if (Array.isArray(threshold.limit)) {
            // 保留足够精度避免 1.00002 被截为 1.00
            limitStr = `[${threshold.limit.map(v => {
              const n = Number(v)
              return Number.isInteger(n) ? String(n) : parseFloat(n.toPrecision(6)).toString()
            }).join(', ')}]`
          } else {
            const n = Number(threshold.limit)
            limitStr = Number.isInteger(n) ? String(n) : parseFloat(n.toPrecision(6)).toString()
          }
        }
        return `${op} ${limitStr}${unit ? ' ' + unit : ''}`.trim()
      },
    },
  ]

  return (
    <div>
      {/* 顶部筛选区 */}
      <div className="filter-section">
        <Row gutter={24} align="middle" style={{ marginBottom: 16 }}>
          <Col span={6}>
            <span className="filter-label">机台:</span>
            <Select
              style={{ width: '100%', minWidth: 120 }}
              value={selectedMachine}
              onChange={(value) => {
                setSelectedMachine(value)
                setDateRange(null)          // 切机台强制重选时间，防止用旧范围查大表
                setRecords([])
                setPagination((prev) => ({ ...prev, pageNo: 1, total: 0 }))
              }}
              placeholder="选择机台"
            >
              {metadata.availableMachines.map((machine) => (
                <Option key={machine} value={machine}>{machine}</Option>
              ))}
            </Select>
          </Col>
          <Col span={10}>
            <span className="filter-label">量产开始时间:</span>
            <RangePicker
              showTime
              format="YYYY-MM-DD HH:mm:ss"
              value={dateRange}
              presets={[
                { label: '今天', value: [dayjs().startOf('day'), dayjs().endOf('day')] },
                { label: '最近 3 天', value: [dayjs().subtract(2, 'day').startOf('day'), dayjs().endOf('day')] },
                { label: '最近 7 天', value: [dayjs().subtract(6, 'day').startOf('day'), dayjs().endOf('day')] },
                { label: '最近 30 天', value: [dayjs().subtract(29, 'day').startOf('day'), dayjs().endOf('day')] },
              ]}
              onChange={(value) => {
                setDateRange(value)
                setPagination((prev) => ({ ...prev, pageNo: 1 }))
              }}
              style={{ width: '100%' }}
              placeholder={['开始时间 (必填)', '结束时间 (必填)']}
            />
          </Col>
        </Row>
        <Row gutter={24} align="middle">
          <Col span={8}>
            <CustomSelect
              label="Chuck"
              options={metadata.availableChucks}
              value={selectedChucks}
              onChange={(value) => {
                setSelectedChucks(value)
                setPagination((prev) => ({ ...prev, pageNo: 1 }))
              }}
              placeholder={metadataLoading ? '加载中...' : '全选'}
              disabled={metadataLoading}
            />
          </Col>
          <Col span={16}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 2 }}>
              <span className="filter-label" style={{ marginRight: 4 }}>Lot List:</span>
              {metadataLoading
                ? <span style={{ fontSize: 11, color: '#999' }}>加载中...</span>
                : <>
                    <a
                      style={{ fontSize: 11, color: '#1677ff', marginRight: 6 }}
                      onClick={() => {
                        setSelectedLotWaferKeys(allWaferLeafKeys)
                        setPagination((prev) => ({ ...prev, pageNo: 1 }))
                      }}
                    >全选</a>
                    <a
                      style={{ fontSize: 11, color: '#999' }}
                      onClick={() => {
                        setSelectedLotWaferKeys([])
                        setPagination((prev) => ({ ...prev, pageNo: 1 }))
                      }}
                    >清空</a>
                  </>
              }
            </div>
            <TreeSelect
              style={{ width: '100%' }}
              treeData={lotWaferTreeData}
              value={selectedLotWaferKeys}
              treeCheckable
              showCheckedStrategy={TreeSelect.SHOW_CHILD}
              placeholder={metadataLoading ? '正在加载 Chuck / Lot 数据...' : '不选 = 不过滤（查全部）'}
              disabled={metadataLoading}
              maxTagCount={0}
              maxTagPlaceholder={() => lotWaferSummary}
              onChange={(value) => {
                setSelectedLotWaferKeys(value)
                setPagination((prev) => ({ ...prev, pageNo: 1 }))
              }}
            />
          </Col>
        </Row>

        {/* 查询按钮：明确触发，避免自动级联请求卡死 */}
        <Row style={{ marginTop: 8 }}>
          <Col span={24} style={{ textAlign: 'right' }}>
            <Button
              type="primary"
              disabled={!selectedMachine || !dateRange?.[0] || !dateRange?.[1]}
              loading={loading}
              onClick={() => {
                setPagination((prev) => ({ ...prev, pageNo: 1 }))
                fetchRecords(1, pagination.pageSize)
              }}
            >
              查询
            </Button>
          </Col>
        </Row>
      </div>

      <Table
        columns={columns}
        dataSource={records}
        loading={loading}
        rowKey="id"
        size="small"
        locale={{
          emptyText: !selectedMachine
            ? '请先选择机台'
            : (!dateRange?.[0] || !dateRange?.[1])
              ? '请选择时间范围后查询'
              : '点击"查询"按钮加载数据',
        }}
        onChange={(pager, _filters, sorter) => {
          // 排序变化：同步 sortConfig 后立即重查
          if (sorter && sorter.columnKey) {
            const keyMap = { time: 'time', rejectReason: 'reason' }
            const newSortedBy = keyMap[sorter.columnKey] || 'time'
            const newOrderedBy = sorter.order === 'ascend' ? 'asc' : 'desc'
            setSortConfig({ sortedBy: newSortedBy, orderedBy: newOrderedBy })
            // 排序是用户主动操作，直接重查当前页
            fetchRecords(pager.current || 1, pager.pageSize || pagination.pageSize)
            return
          }
          // 处理翻页
          const nextPageNo = pager.current || 1
          const nextPageSize = pager.pageSize || 20
          fetchRecords(nextPageNo, nextPageSize)
        }}
        pagination={{
          current: pagination.pageNo,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条记录`,
        }}
      />

      <Modal
        title={`详情 - ID ${detailData?.id || '-'}`}
        open={detailVisible}
        onCancel={closeDetail}
        footer={null}
        width={980}
      >
        <div style={{ marginBottom: 12 }}>
          <Row gutter={16}>
            <Col span={12}><strong>报错字段：</strong>{detailData?.errorField || '-'}</Col>
            <Col span={12}><strong>发生时间：</strong>{formatTimestamp(detailData?.time)}</Col>
          </Row>
          <Row gutter={16} style={{ marginTop: 8 }}>
            <Col span={8}><strong>故障根因：</strong>{detailData?.rootCause || '-'}</Col>
            <Col span={8}><strong>分系统：</strong>{detailData?.system || '-'}</Col>
            <Col span={8}>
              <strong>诊断指标数：</strong>{detailData?.metricsMeta?.metricDiagnosticTotal ?? metricTotal}
              {((detailData?.metricsMeta?.metricModelParamTotal ?? 0) > 0 || (detailData?.metrics || []).some(m => m.type === 'model_param')) && (
                <span style={{ color: '#888', fontWeight: 400, marginLeft: 6 }}>
                  （建模参数 {detailData?.metricsMeta?.metricModelParamTotal ?? (detailData?.metrics || []).filter(m => m.type === 'model_param').length} 项，见下方折叠区）
                </span>
              )}
            </Col>
          </Row>
        </div>

        {/* 诊断指标：有阈值规则，显示状态 + 阈值条件 */}
        <Table
          columns={metricColumns}
          dataSource={(detailData?.metrics || []).filter(m => m.type !== 'model_param')}
          loading={detailLoading}
          rowKey={(row) => row.name}
          pagination={{
            current: metricPage,
            pageSize: METRIC_PAGE_SIZE,
            total: detailData?.metricsMeta?.metricDiagnosticTotal ?? metricTotal,
            onChange: handleMetricPageChange,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 条诊断指标`,
          }}
          scroll={{ y: 320 }}
        />

        {/* 建模参数：仅作为模型输入，无阈值判断，折叠展示 */}
        {((detailData?.metricsMeta?.metricModelParamTotal ?? 0) > 0 || (detailData?.metrics || []).some(m => m.type === 'model_param')) && (
          <details style={{ marginTop: 12 }}>
            <summary style={{
              cursor: 'pointer',
              color: '#888',
              fontSize: 13,
              userSelect: 'none',
              padding: '4px 0',
            }}>
              建模参数（{detailData?.metricsMeta?.metricModelParamTotal ?? (detailData?.metrics || []).filter(m => m.type === 'model_param').length} 项，仅供参考，无阈值判断）
            </summary>
            <div style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '6px 16px',
              marginTop: 8,
              padding: '8px 12px',
              background: '#fafafa',
              borderRadius: 4,
              border: '1px solid #f0f0f0',
            }}>
              {(detailData?.metrics || [])
                .filter(m => m.type === 'model_param')
                .map(m => (
                  <span key={m.name} style={{ fontSize: 13, color: '#555', whiteSpace: 'nowrap' }}>
                    <span style={{ color: '#888' }}>{m.name}：</span>
                    <span>{m.approximate ? '~' : ''}{formatMetricValue(m.value)}{m.unit ? ' ' + m.unit : ''}</span>
                  </span>
                ))
              }
              {!(detailData?.metrics || []).some(m => m.type === 'model_param') && (
                <span style={{ fontSize: 13, color: '#999' }}>本次返回未附带建模参数明细，请检查后端取数日志。</span>
              )}
            </div>
          </details>
        )}
      </Modal>
    </div>
  )
}

export default FaultRecords
