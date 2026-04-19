// Graph Skeleton Loading Component
import React from 'react';
import { Skeleton, Card, Row, Col, Space } from 'antd';

const GraphSkeleton = ({ count = 3 }) => {
  return (
    <div style={{ padding: '24px' }}>
      <Row gutter={[16, 16]}>
        {/* Control Panel Skeleton */}
        <Col span={24}>
          <Card>
            <Skeleton active paragraph={{ rows: 1 }} />
          </Card>
        </Col>

        {/* Graph Canvas Skeleton */}
        <Col span={18}>
          <Card
            style={{
              height: '600px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Space direction="vertical" size="large" style={{ width: '100%' }}>
              <Skeleton.Image active style={{ width: '100%', height: '400px' }} />
              <Skeleton active paragraph={{ rows: 2 }} />
            </Space>
          </Card>
        </Col>

        {/* Entity List Skeleton */}
        <Col span={6}>
          <Card title="Entities" style={{ height: '600px', overflow: 'auto' }}>
            {Array.from({ length: count }).map((_, index) => (
              <div key={index} style={{ marginBottom: '16px' }}>
                <Skeleton active avatar paragraph={{ rows: 1 }} />
              </div>
            ))}
          </Card>
        </Col>

        {/* Metrics Skeleton */}
        <Col span={24}>
          <Row gutter={16}>
            {Array.from({ length: 4 }).map((_, index) => (
              <Col span={6} key={index}>
                <Card>
                  <Skeleton active />
                </Card>
              </Col>
            ))}
          </Row>
        </Col>
      </Row>
    </div>
  );
};

export default GraphSkeleton;
