// 临时测试文件 - 检查基本渲染
import React from 'react'

export default function TestApp() {
  return (
    <div style={{ padding: '20px' }}>
      <h1>SMEE-LITHO-RCA 测试页面</h1>
      <p>如果你看到这个，说明React基本渲染正常</p>
      <p>当前时间: {new Date().toLocaleString()}</p>
    </div>
  )
}
