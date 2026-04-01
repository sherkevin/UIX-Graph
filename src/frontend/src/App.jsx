import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import {
  DatabaseOutlined,
  FileAddOutlined,
  ApartmentOutlined,
  BugOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons'

// Stage3：拒片故障管理
import FaultRecords from './pages/FaultRecords'

// 旧版页面（图谱、知识、本体等）——暂时占位，后续补充
// import KnowledgeEntry   from './pages/KnowledgeEntry'
// import OntologyManager  from './pages/OntologyManager'
// import OntologyView     from './pages/OntologyView'
// import KnowledgeGraph   from './pages/KnowledgeGraph'
// import EntityDashboard  from './pages/EntityDashboard'
// import FullGraphView    from './components/FullGraphView'

const { Header, Sider, Content } = Layout

const menuItems = [
  {
    key: '/records',
    icon: <DatabaseOutlined />,
    label: '故障记录',
  },
  // 以下菜单项在对应页面迁移完成后逐步开启
  // { key: '/entry',       icon: <FileAddOutlined />,   label: '知识录入' },
  // { key: '/ontology',    icon: <ApartmentOutlined />, label: '本体管理' },
  // { key: '/ontology-view', icon: <ApartmentOutlined />, label: '本体展示' },
  // { key: '/graph',       icon: <BugOutlined />,       label: '知识图谱' },
  // { key: '/full-graph',  icon: <NodeIndexOutlined />, label: '全量图谱' },
]

function AppContent() {
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#001529', padding: '0 24px', display: 'flex', alignItems: 'center' }}>
        <h1 style={{ margin: 0, fontSize: '20px', color: '#fff' }}>SXEE-LITHO-RCA</h1>
      </Header>
      <Layout>
        <Sider width={200} style={{ background: '#fff' }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems.map(item => ({
              ...item,
              label: <Link to={item.key}>{item.label}</Link>,
            }))}
            style={{ height: '100%', borderRight: 0 }}
          />
        </Sider>
        <Layout style={{ padding: '24px' }}>
          <Content style={{ background: '#fff', padding: '24px', minHeight: 280 }}>
            <Routes>
              <Route path="/"        element={<Navigate to="/records" replace />} />
              <Route path="/records" element={<FaultRecords />} />
              {/* 以下路由在对应页面迁移完成后逐步开启 */}
              {/* <Route path="/entry"        element={<KnowledgeEntry />} /> */}
              {/* <Route path="/ontology"     element={<OntologyManager />} /> */}
              {/* <Route path="/ontology-view" element={<OntologyView />} /> */}
              {/* <Route path="/graph"        element={<KnowledgeGraph />} /> */}
              {/* <Route path="/full-graph"   element={<FullGraphView />} /> */}
              {/* <Route path="/entity/:entityId" element={<EntityDashboard />} /> */}
              <Route path="*"        element={<Navigate to="/records" replace />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </Layout>
  )
}

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  )
}

export default App
