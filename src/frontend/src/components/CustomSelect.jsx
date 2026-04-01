import React, { useState, useEffect, useRef } from 'react'
import './CustomSelect.css'

/**
 * 自定义下拉选择组件
 * 特性：
 * - 默认显示"全选"状态
 * - 打开后支持单选/多选
 * - 提供"全选"、"确定"、"取消"按钮
 * - 点击外部或取消按钮时恢复原值
 */
const CustomSelect = ({ label, options, value, onChange, placeholder = '全选' }) => {
  const [open, setOpen] = useState(false)
  const [tempSelected, setTempSelected] = useState(value)
  const wrapperRef = useRef(null)

  // 同步外部 value 变化
  useEffect(() => {
    setTempSelected(value)
  }, [value])

  // 判断是否全选
  const isAllSelected = tempSelected.length === options.length

  // 打开下拉框时，初始化 tempSelected 为当前 value（如果全选则显示所有选项）
  useEffect(() => {
    if (open) {
      // 打开时，如果当前是全选状态，则 tempSelected 应该包含所有选项
      if (value.length === options.length) {
        setTempSelected(options)
      } else {
        setTempSelected(value)
      }
    }
  }, [open, value, options])

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setOpen(false)
        setTempSelected(value) // 取消时恢复原值
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [open, value])

  const handleToggle = (option) => {
    if (tempSelected.includes(option)) {
      setTempSelected(tempSelected.filter(v => v !== option))
    } else {
      setTempSelected([...tempSelected, option])
    }
  }

  const handleSelectAll = () => {
    setTempSelected(options)
  }

  const handleConfirm = () => {
    onChange(tempSelected)
    setOpen(false)
  }

  const handleCancel = () => {
    setTempSelected(value)
    setOpen(false)
  }

  const displayText = isAllSelected
    ? placeholder
    : tempSelected.length === 0
    ? '未选择'
    : tempSelected.length <= 2
    ? tempSelected.join(', ')
    : `${tempSelected.slice(0, 2).join(', ')} + ${tempSelected.length - 2}...`

  return (
    <div className="custom-select-wrapper" ref={wrapperRef}>
      <span className="filter-label">{label}:</span>
      <div
        className={`custom-select-input ${open ? 'open' : ''}`}
        onClick={() => setOpen(!open)}
      >
        <span>{displayText}</span>
        <span style={{ color: '#999', marginLeft: 8 }}>▼</span>
      </div>
      {open && (
        <div className="custom-select-dropdown">
          <div
            className="custom-select-option select-all-option"
            onClick={handleSelectAll}
          >
            全选
          </div>
          {options.map((option) => (
            <div
              key={option}
              className={`custom-select-option ${tempSelected.includes(option) ? 'selected' : ''}`}
              onClick={() => handleToggle(option)}
            >
              {option}
            </div>
          ))}
          <div className="custom-select-actions">
            <button onClick={handleCancel}>取消</button>
            <button className="primary" onClick={handleConfirm}>
              确定
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default CustomSelect
