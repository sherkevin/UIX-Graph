/**
 * 统一 API 服务层
 * Stage3 拒片故障管理接口（v1）+ 旧版图谱、本体等接口
 *
 * API 基址策略：
 *   VITE_API_BASE_URL 未设置或为空 → 请求路径以 /api 开头，依赖 Vite 代理（开发）
 *                                     或同源反代（生产，推荐）
 *   VITE_API_BASE_URL 设置为后端根地址（如 http://backend.example.com）→
 *                                     跨域直连后端，需后端 CORS 允许该来源
 */
import axios from 'axios'

const _origin = (import.meta.env.VITE_API_BASE_URL || '').trim()
const BASE_URL = _origin ? `${_origin}/api` : '/api'
const DEBUG    = import.meta.env.VITE_ENABLE_DEBUG === 'true'

// ── Axios 实例 ───────────────────────────────────────────────────────────
const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// 请求拦截器
apiClient.interceptors.request.use(
  (request) => {
    if (DEBUG) console.log(`[API ▶] ${request.method?.toUpperCase()} ${request.baseURL}${request.url}`, request.data)
    return request
  },
  (error) => {
    if (DEBUG) console.error('[API ▶ Error]', error)
    return Promise.reject(error)
  }
)

/**
 * 从 axios 错误对象中提取可读的错误信息
 * 优先级：后端 detail > message > HTTP 状态文本 > 网络错误
 */
export function extractErrorMessage(error) {
  if (error.response) {
    const { status, data } = error.response
    const detail = data?.detail || data?.message
    if (detail) return `[${status}] ${detail}`
    return `请求失败 (HTTP ${status})`
  }
  if (error.request) {
    return '无法连接到服务器，请检查网络或后端服务是否运行'
  }
  return error.message || '未知错误'
}

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    if (DEBUG) console.log(`[API ◀] ${response.config.url}`, response.data)
    return response
  },
  (error) => {
    const msg = extractErrorMessage(error)
    if (DEBUG) console.error('[API ◀ Error]', msg, error)
    else console.error(`[API Error] ${msg}`)
    return Promise.reject(error)
  }
)

// ── Stage3：拒片故障管理（/api/v1/reject-errors） ────────────────────────
export const rejectErrorsAPI = {
  /**
   * 接口 1：获取筛选元数据（Chuck/Lot/Wafer 树）
   * GET /api/v1/reject-errors/metadata?equipment=SSB8000&startTime=...&endTime=...
   * 不同机台 + 时间下的 Chuck/Lot/Wafer 下拉选项是动态的
   */
  getMetadata: (equipment, startTime = null, endTime = null) => {
    const params = { equipment }
    if (startTime) params.startTime = startTime
    if (endTime) params.endTime = endTime
    return apiClient.get('/v1/reject-errors/metadata', { params })
  },

  /**
   * 接口 2：查询拒片故障记录（分页 + 筛选）
   * POST /api/v1/reject-errors/search
   */
  search: (payload) => apiClient.post('/v1/reject-errors/search', payload),

  /**
   * 接口 3：获取拒片故障详情（含指标数据）
   * GET /api/v1/reject-errors/{id}/metrics
   * @param {number|null} requestTime 分析基准时间 T（13 位毫秒）；与行上 time 一致时可走服务端缓存
   */
  getMetrics: (id, pageNo = 1, pageSize = 20, requestTime = null) => {
    const params = { pageNo, pageSize }
    if (requestTime != null) params.requestTime = requestTime
    return apiClient.get(`/v1/reject-errors/${id}/metrics`, { params })
  },
}

// ── 辅助 API：旧版图谱 / 实体 / 诊断 / 知识模块 ──────────────────────────
export const knowledgeApi = {
  getRecords:          ()         => apiClient.get('/knowledge/records'),
  getRecord:           (caseId)   => apiClient.get(`/knowledge/records/${caseId}`),
  createRecord:        (payload)  => apiClient.post('/knowledge/records', payload),
  updateRecord:        (caseId, payload) => apiClient.put(`/knowledge/records/${caseId}`, payload),
  deleteRecord:        (caseId)   => apiClient.delete(`/knowledge/records/${caseId}`),
}

export const propagationApi = {
  getPropagationPath:  (caseId, startNode = null) => {
    const params = {}
    if (startNode) params.start_node = startNode
    return apiClient.get(`/propagation/${caseId}`, { params })
  },
  getEntityDetail:     (entityId) => apiClient.get(`/entity/${entityId}`),
  getEntityTimeseries: (entityId, timeRange = '7d') =>
    apiClient.get(`/entity/${entityId}/timeseries`, { params: { time_range: timeRange } }),
}

// ── 旧版：实体 / 图谱 / 诊断 / 本体等接口 ──────────────────────────────
export const api = {
  // 实体
  getEntities:         (params)   => apiClient.get('/entity', { params }),
  getEntity:           (id)       => apiClient.get(`/entity/${id}`),
  getEntityConnections:(id)       => apiClient.get(`/entity/${id}/connections`),
  getEntityMetrics:    (id)       => apiClient.get(`/entity/${id}/timeseries`),

  // 诊断
  getDiagnosis:        (payload)  => apiClient.post('/diagnosis/analyze', payload),
  getDiagnosisHistory: ()         => apiClient.get('/diagnosis/history'),
  getDiagnosisDetails: (id)       => apiClient.get(`/diagnosis/${id}`),

  // 图谱
  getFullGraph:        ()         => apiClient.get('/graph/full-graph'),
  getSubgraph:         (caseId)   => apiClient.get(`/graph/subgraph/${caseId}`),
  getGraphStats:       ()         => apiClient.get('/graph/stats'),

  // 故障传播
  getPropagationPaths: (caseId, startNode = null) => propagationApi.getPropagationPath(caseId, startNode),
  getPropagationImpact:(params)   => apiClient.post('/propagation/impact', params),

  // 知识
  searchKnowledge:     (query)    => apiClient.get('/knowledge/search', { params: { q: query } }),
  getKnowledgeGraph:   (topic)    => apiClient.get(`/knowledge/graph/${topic}`),

  // 本体
  getOntologyTree:     ()         => apiClient.get('/ontology/tree'),
  getOntologyDetails:  (type)     => apiClient.get(`/ontology/details/${type}`),

  // 可视化
  getVisualizationData:(params)   => apiClient.get('/visualization/data', { params }),
  exportVisualization: (params)   => apiClient.post('/visualization/export', params),
}

export default apiClient
