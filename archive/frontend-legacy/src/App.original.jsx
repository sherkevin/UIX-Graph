import React, { useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { ProLayout } from '@ant-design/pro-components'
import {
  MenuDataItem,
  PageContainer,
} from '@ant-design/pro-components'
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

const menuDataRender = () => [
  {
    path: '/records',
    name: '故障记录',
    icon: <DatabaseOutlined />,
  },
  {
    path: '/entry',
    name: '知识录入',
    icon: <FileAddOutlined />,
  },
  {
    path: '/ontology',
    name: '本体管理',
    icon: <ApartmentOutlined />,
  },
  {
    path: '/graph',
    name: '知识图谱',
    icon: <BugOutlined />,
  },
]

function AppContent() {
  const location = useLocation()
  const navigate = useNavigate()
  const [pathname, setPathname] = useState(location.pathname)

  return (
      <ProLayout
        title="SMEE-LITHO-RCA"
        logo="https://gw.alipayobjects.com/zos/antfincdn/PmY%24TNNDBI/logo.svg"
        menuDataRender={menuDataRender}
        menuItemRender={(item, dom) => {
          return (
            <div
              onClick={() => {
                setPathname(item.path || '/')
                navigate(item.path || '/')
              }}
              style={{ cursor: 'pointer' }}
            >
              {dom}
            </div>
          )
        }}
        location={{
          pathname: location.pathname,
        }}
        navTheme="light"
        layout="mix"
        fixSiderbar
        fixedHeader
        contentStyle={{
          minHeight: 'calc(100vh - 56px)',
          padding: '24px',
        }}
      >
      <Routes>
        <Route path="/" element={<Navigate to="/records" replace />} />
        <Route
          path="/records"
          element={
            <PageContainer>
              <FaultRecords />
            </PageContainer>
          }
        />
        <Route
          path="/entry"
          element={
            <PageContainer>
              <KnowledgeEntry />
            </PageContainer>
          }
        />
        <Route
          path="/ontology"
          element={
            <PageContainer>
              <OntologyManager />
            </PageContainer>
          }
        />
        <Route
          path="/graph"
          element={
            <PageContainer>
              <KnowledgeGraph />
            </PageContainer>
          }
        />
      </Routes>
    </ProLayout>
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
