import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Col, Empty, Row, Select, Space, Statistic, Tag, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';

type Target = {
  id: number;
  name: string;
  target_type: 'website' | 'port' | 'exporter';
  exporter_kind?: string | null;
};

type TargetMetric = {
  key: string;
  label: string;
  unit: string;
  value?: number | null;
  series: [number, number][];
};

type TargetMetrics = {
  scrape_status: 'pending' | 'up' | 'down';
  last_scrape_at?: string | null;
  scrape_duration_seconds?: number | null;
  last_error?: string | null;
  metric_count: number;
  series_count: number;
  metric_names: string[];
  metrics: TargetMetric[];
};

type Props = {
  target: Target | null;
  token: string;
};

async function apiRequest<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

function formatMetricValue(value: number | null | undefined, unit: string) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  if (unit === 'bytes') {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let next = value;
    let index = 0;
    while (Math.abs(next) >= 1024 && index < units.length - 1) {
      next /= 1024;
      index += 1;
    }
    return `${next.toFixed(next >= 100 ? 0 : next >= 10 ? 1 : 2)} ${units[index]}`;
  }
  const formatted = Math.abs(value) >= 1000
    ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : Number(value.toFixed(2)).toString();
  return unit ? `${formatted} ${unit}` : formatted;
}

export default function TargetMetricsPanel({ target, token }: Props) {
  const [minutes, setMinutes] = useState(60);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<TargetMetrics | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const selectedMetric = useMemo(
    () => data?.metrics.find((item) => item.key === selectedKey)
      || data?.metrics.find((item) => item.series.length > 0)
      || data?.metrics[0]
      || null,
    [data, selectedKey],
  );

  const chartOption = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: { top: 28, right: 20, bottom: 42, left: 64 },
    xAxis: {
      type: 'category',
      data: (selectedMetric?.series || []).map(([timestamp]) => new Date(timestamp * 1000).toLocaleTimeString()),
      axisLabel: { rotate: 25 },
    },
    yAxis: { type: 'value', name: selectedMetric?.unit || '' },
    series: [{
      name: selectedMetric?.label || '指标值',
      type: 'line',
      showSymbol: false,
      smooth: true,
      data: (selectedMetric?.series || []).map(([, value]) => value),
    }],
  }), [selectedMetric]);

  async function loadMetrics(nextMinutes = minutes, showError = true) {
    if (!target || !token) {
      setData(null);
      return;
    }
    setLoading(true);
    try {
      const next = await apiRequest<TargetMetrics>(`/targets/${target.id}/metrics?minutes=${nextMinutes}`, token);
      setData(next);
      setSelectedKey((current) => current && next.metrics.some((item) => item.key === current)
        ? current
        : next.metrics.find((item) => item.series.length > 0)?.key || next.metrics[0]?.key || null);
    } catch (error) {
      setData(null);
      if (showError) message.error(error instanceof Error ? error.message : '加载持续指标失败');
    } finally {
      setLoading(false);
    }
  }

  async function syncCollection() {
    if (!target) return;
    setLoading(true);
    try {
      await apiRequest(`/targets/${target.id}/sync`, token, { method: 'POST', body: '{}' });
      message.success('采集配置已同步，Prometheus 通常会在 30 秒内产生第一批数据');
      await loadMetrics(minutes, false);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '同步采集配置失败');
      setLoading(false);
    }
  }

  useEffect(() => {
    setData(null);
    setSelectedKey(null);
    if (target) void loadMetrics(minutes, false);
  }, [target?.id, target?.target_type, token]);

  if (!target) return null;

  const metricTitle = target.target_type === 'website'
    ? '网站 Blackbox 持续指标'
    : target.target_type === 'port'
      ? 'TCP Blackbox 持续指标'
      : (target.exporter_kind || 'custom') + ' 持续指标';

  return (
    <Card
      className="section"
      title={metricTitle}
      extra={(
        <Space wrap>
          <Select
            value={minutes}
            style={{ width: 128 }}
            options={[
              { label: '最近 30 分钟', value: 30 },
              { label: '最近 1 小时', value: 60 },
              { label: '最近 6 小时', value: 360 },
              { label: '最近 24 小时', value: 1440 },
            ]}
            onChange={(value) => {
              setMinutes(value);
              void loadMetrics(value);
            }}
          />
          <Button icon={<ReloadOutlined />} loading={loading} onClick={() => loadMetrics()}>刷新指标</Button>
          <Button loading={loading} onClick={syncCollection}>同步采集</Button>
        </Space>
      )}
    >
      {data ? (
        <Space direction="vertical" className="fullWidth" size={16}>
          {data.last_error ? <Alert type="error" showIcon message="Prometheus 采集失败" description={data.last_error} /> : null}
          <Row gutter={[12, 12]}>
            <Col xs={12} md={6}><Statistic title="采集状态" value={data.scrape_status === 'up' ? '正常' : data.scrape_status === 'down' ? '异常' : '待采集'} /></Col>
            <Col xs={12} md={6}><Statistic title="指标名称" value={data.metric_count} /></Col>
            <Col xs={12} md={6}><Statistic title="时间序列" value={data.series_count} /></Col>
            <Col xs={12} md={6}><Statistic title="采集耗时" value={data.scrape_duration_seconds != null ? Math.round(data.scrape_duration_seconds * 1000) : '-'} suffix={data.scrape_duration_seconds != null ? 'ms' : undefined} /></Col>
          </Row>
          <div>
            <Space wrap>
              <Tag color={data.scrape_status === 'up' ? 'green' : data.scrape_status === 'down' ? 'red' : 'gold'}>
                {data.scrape_status === 'up' ? '持续采集正常' : data.scrape_status === 'down' ? '持续采集异常' : '等待首次采集'}
              </Tag>
              {data.last_scrape_at ? <span>最后采集：{new Date(data.last_scrape_at).toLocaleString()}</span> : null}
            </Space>
          </div>
          <Row gutter={[12, 12]}>
            {data.metrics.map((item) => (
              <Col xs={12} md={8} xl={6} key={item.key}>
                <Card
                  size="small"
                  className={selectedMetric?.key === item.key ? 'metricTile selected' : 'metricTile'}
                  onClick={() => setSelectedKey(item.key)}
                >
                  <Statistic title={item.label} value={formatMetricValue(item.value, item.unit)} />
                </Card>
              </Col>
            ))}
          </Row>
          {selectedMetric?.series.length
            ? <ReactECharts option={chartOption} style={{ height: 320 }} />
            : <Empty description="尚未形成该指标的历史序列，请等待下一次采集并确认目标可由采集组件访问" />}
          <Card size="small" title="已发现的指标名称">
            {data.metric_names.length
              ? <Space wrap>{data.metric_names.slice(0, 60).map((name) => <Tag key={name}>{name}</Tag>)}</Space>
              : <Empty description="尚未发现指标" />}
          </Card>
        </Space>
      ) : <Empty description="尚未读取到持续指标。点击“同步采集”，等待约 30 秒后刷新。" />}
    </Card>
  );
}