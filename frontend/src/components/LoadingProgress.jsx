// Loading Progress Component
import React from 'react';
import { Progress, Spin } from 'antd';

const LoadingProgress = ({
  percent = 0,
  status = 'active',
  message = 'Loading...',
  showSpinner = true,
  size = 'default',
}) => {
  return (
    <div style={{ padding: '40px', textAlign: 'center' }}>
      {showSpinner && (
        <div style={{ marginBottom: '20px' }}>
          <Spin size={size === 'small' ? 'small' : 'large'} tip={message} />
        </div>
      )}
      <Progress
        percent={Math.round(percent)}
        status={status}
        strokeColor={{
          '0%': '#108ee9',
          '100%': '#87d068',
        }}
        format={(percent) => `${percent}%`}
      />
      {message && (
        <p style={{ marginTop: '10px', color: '#666' }}>{message}</p>
      )}
    </div>
  );
};

export default LoadingProgress;
