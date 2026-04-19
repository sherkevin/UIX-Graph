import React from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { Layout, Menu, Card } from 'antd'
import {
  DatabaseOutlined,
  FileAddOutlined,
  ApartmentOutlined,
  BugOutlined,
} from '@ant-design/icons'
import FaultRecords from './pages/FaultRecords'
import KnowledgeEntry from './pages/KnowledgeEntry'
import OntologyManager from './pages/OntologyManager'
import KnowledgeGraph from './pages/KnowledgeGraph'

const { Header, Sider, Content } = Layout

const menuItems = [
  {
    key: '/records',
    icon: <DatabaseOutlined />,
    label: '故障记录',
  },
  {
    key: '/entry',
    icon: <FileAddOutlined />,
    label: '知识录入',
  },
  {
    key: '/ontology',
    icon: <ApartmentOutlined />,
    label: '本体管理',
  },
  {
    key: '/graph',
    icon: <BugOutlined />,
    label: '知识图谱',
  },
]

function AppContent() {
  const location = useLocation()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center' }}>
        <h1 style={{ margin: 0, fontSize: '20px' }}>SMEE-LITHO-RCA</h1>
      </Header>
      <Layout>
        <Sider width={200} style={{ background: '#fff' }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems.map(item => ({
              ...item,
              label: <Link to={item.key}>{item.label}</Link>
            }))}
            style={{ height: '100%', borderRight: 0 }}
          />
        </Sider>
        <Layout style={{ padding: '24px' }}>
          <Content style={{ background: '#fff', padding: '24px', minHeight: 280 }}>
            <Routes>
              <Route path="/" element={<Navigate to="/records" replace />} />
              <Route path="/records" element={<FaultRecords />} />
              <Route path="/entry" element={<KnowledgeEntry />} />
              <Route path="/ontology" element={<OntologyManager />} />
              <Route path="/graph" element={<KnowledgeGraph />} />
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
