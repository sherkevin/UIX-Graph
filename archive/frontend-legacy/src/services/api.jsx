// Unified API Service
import axios from 'axios';
import config from '../config';

// Create axios instance with base configuration
const apiClient = axios.create({
  baseURL: config.apiBaseUrl,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
apiClient.interceptors.request.use(
  (request) => {
    if (config.enableDebug) {
      console.log(`[API Request] ${request.method?.toUpperCase()} ${request.url}`, request.data);
    }
    return request;
  },
  (error) => {
    if (config.enableDebug) {
      console.error('[API Request Error]', error);
    }
    return Promise.reject(error);
  }
);

// Response interceptor
apiClient.interceptors.response.use(
  (response) => {
    if (config.enableDebug) {
      console.log(`[API Response] ${response.config.url}`, response.data);
    }
    return response;
  },
  (error) => {
    if (config.enableDebug) {
      console.error('[API Response Error]', error);
    }

    // Handle common error scenarios
    if (error.response) {
      // Server responded with error status
      const { status, data } = error.response;

      switch (status) {
        case 401:
          console.error('Unauthorized: Please check authentication');
          break;
        case 403:
          console.error('Forbidden: You do not have permission to access this resource');
          break;
        case 404:
          console.error('Not Found: The requested resource does not exist');
          break;
        case 500:
          console.error('Server Error: Please try again later');
          break;
        default:
          console.error(`API Error (${status}):`, data?.detail || data?.message || 'Unknown error');
      }
    } else if (error.request) {
      // Request made but no response received
      console.error('Network Error: Unable to connect to the server');
    } else {
      // Error in request configuration
      console.error('Request Error:', error.message);
    }

    return Promise.reject(error);
  }
);

// API Endpoints
export const api = {
  // Entity endpoints
  getEntities: (params) => apiClient.get('/api/entities', { params }),
  getEntity: (id) => apiClient.get(`/api/entities/${id}`),
  getEntityConnections: (id) => apiClient.get(`/api/entities/${id}/connections`),
  getEntityMetrics: (id) => apiClient.get(`/api/entities/${id}/metrics`),

  // Diagnosis endpoints
  getDiagnosis: (symptoms) => apiClient.post('/api/diagnosis/diagnose', { symptoms }),
  getDiagnosisHistory: () => apiClient.get('/api/diagnosis/history'),
  getDiagnosisDetails: (id) => apiClient.get(`/api/diagnosis/${id}`),

  // Graph endpoints
  getFullGraph: (params) => apiClient.get('/api/graph/full', { params }),
  getSubgraph: (params) => apiClient.get('/api/graph/subgraph', { params }),
  getGraphStats: () => apiClient.get('/api/graph/stats'),

  // Fault propagation endpoints
  getPropagationPaths: (params) => apiClient.post('/api/propagation/paths', params),
  getPropagationImpact: (params) => apiClient.post('/api/propagation/impact', params),

  // Knowledge endpoints
  searchKnowledge: (query) => apiClient.get('/api/knowledge/search', { params: { q: query } }),
  getKnowledgeGraph: (topic) => apiClient.get(`/api/knowledge/graph/${topic}`),

  // Ontology endpoints
  getOntologyTree: () => apiClient.get('/api/ontology/tree'),
  getOntologyDetails: (type) => apiClient.get(`/api/ontology/details/${type}`),

  // Visualization endpoints
  getVisualizationData: (params) => apiClient.get('/api/visualization/data', { params }),
  exportVisualization: (params) => apiClient.post('/api/visualization/export', params),
};

export default apiClient;
