// Application Configuration
// Reads from environment variables with fallback defaults

const config = {
  // API Configuration
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',

  // Feature Flags
  enableDebug: import.meta.env.VITE_ENABLE_DEBUG === 'true',
  enableAnalytics: import.meta.env.VITE_ENABLE_ANALYTICS === 'true',

  // Graph Configuration
  graph: {
    maxNodes: parseInt(import.meta.env.VITE_GRAPH_MAX_NODES || '1000', 10),
    defaultLayout: import.meta.env.VITE_GRAPH_DEFAULT_LAYOUT || 'force',
    animationDuration: parseInt(import.meta.env.VITE_GRAPH_ANIMATION_DURATION || '500', 10),
  },

  // Cache Configuration
  cache: {
    enabled: import.meta.env.VITE_CACHE_ENABLED !== 'false',
    ttl: parseInt(import.meta.env.VITE_CACHE_TTL || '300000', 10),
  },

  // UI Configuration
  ui: {
    defaultTheme: import.meta.env.VITE_DEFAULT_THEME || 'light',
    defaultLanguage: import.meta.env.VITE_DEFAULT_LANGUAGE || 'zh-CN',
  },
};

export default config;
