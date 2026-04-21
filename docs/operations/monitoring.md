# Monitoring and Observability

This document covers all monitoring, alerting, and observability features for the Polyedge trading bot.

## Health Checks

### Health Check Endpoints

Three health check endpoints for different monitoring needs:

#### 1. Basic Health Check

**Endpoint**: `GET /health`

**Purpose**: Lightweight check for load balancers

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-21T10:43:57Z"
}
```

**Use Cases**:
- Load balancer health checks
- Uptime monitoring
- Basic availability checks

#### 2. Readiness Check

**Endpoint**: `GET /health/ready`

**Purpose**: Verify dependencies are available

**Checks**:
- Database connectivity
- Redis connectivity (if enabled)

**Response** (healthy):
```json
{
  "status": "ready",
  "timestamp": "2026-04-21T10:43:57Z",
  "database": "connected",
  "redis": "connected"
}
```

**Response** (unhealthy):
```json
{
  "status": "not_ready",
  "timestamp": "2026-04-21T10:43:57Z",
  "database": "disconnected",
  "redis": "connected"
}
```

**Status Code**: 503 Service Unavailable when not ready

**Use Cases**:
- Kubernetes readiness probes
- Deployment health checks
- Dependency verification

#### 3. Detailed Health Check

**Endpoint**: `GET /health/detailed`

**Purpose**: Comprehensive system status for monitoring dashboards

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2026-04-21T10:43:57Z",
  "database": "connected",
  "redis": "connected",
  "circuit_breakers": {
    "database": "closed",
    "polymarket": "closed",
    "kalshi": "closed",
    "redis": "closed"
  },
  "connections": {
    "websocket": 42,
    "http": 15
  },
  "memory_usage_percent": 45.2,
  "disk_usage_percent": 68.5,
  "uptime_seconds": 86400
}
```

**Includes**:
- Circuit breaker states
- Active connection counts
- Memory usage percentage
- Disk usage percentage
- System uptime

**Use Cases**:
- Monitoring dashboards (Grafana, Datadog)
- Operational visibility
- Capacity planning

## Prometheus Metrics

### Metrics Endpoint

**Endpoint**: `GET /metrics`

**Format**: Prometheus exposition format

**Authentication**: None (should be restricted by firewall)

### Available Metrics

#### HTTP Request Metrics

**`http_requests_total`** (Counter)
- Total HTTP requests by endpoint and status code
- Labels: `method`, `endpoint`, `status`

**`http_request_duration_seconds`** (Histogram)
- Request latency distribution
- Labels: `method`, `endpoint`
- Buckets: 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0

**Example**:
```
http_requests_total{method="GET",endpoint="/api/v1/dashboard",status="200"} 1523
http_request_duration_seconds_bucket{method="GET",endpoint="/api/v1/dashboard",le="0.1"} 1450
http_request_duration_seconds_sum{method="GET",endpoint="/api/v1/dashboard"} 142.3
http_request_duration_seconds_count{method="GET",endpoint="/api/v1/dashboard"} 1523
```

#### WebSocket Metrics

**`websocket_connections_active`** (Gauge)
- Current number of active WebSocket connections
- Labels: `topic`

**`websocket_messages_total`** (Counter)
- Total WebSocket messages sent
- Labels: `topic`, `type`

#### Database Metrics

**`database_query_duration_seconds`** (Histogram)
- Database query latency
- Labels: `operation`
- Buckets: 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0

**`database_connections_active`** (Gauge)
- Active database connections from pool

**`database_connections_idle`** (Gauge)
- Idle database connections in pool

#### Circuit Breaker Metrics

**`circuit_breaker_state`** (Gauge)
- Circuit breaker state (0=closed, 1=open, 2=half_open)
- Labels: `breaker_name`

**`circuit_breaker_failures_total`** (Counter)
- Total failures per circuit breaker
- Labels: `breaker_name`

#### Rate Limiting Metrics

**`rate_limit_exceeded_total`** (Counter)
- Rate limit violations
- Labels: `endpoint`, `ip`

**`rate_limit_requests_total`** (Counter)
- Total requests checked by rate limiter
- Labels: `endpoint`

#### Timeout Metrics

**`api_timeouts_total`** (Counter)
- API request timeouts

**`db_timeouts_total`** (Counter)
- Database query timeouts

**`external_api_timeouts_total`** (Counter)
- External API call timeouts
- Labels: `service`

### Prometheus Configuration

**Example `prometheus.yml`**:
```yaml
scrape_configs:
  - job_name: 'polyedge'
    scrape_interval: 15s
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

## Error Logging

### Centralized Error Logger

All errors logged with full context for debugging.

**Implementation**: `backend/core/error_logger.py`

### Error Log API

#### Get Recent Errors

**Endpoint**: `GET /api/v1/system/errors`

**Query Parameters**:
- `limit` (default: 100) - Number of errors to return
- `error_type` - Filter by error type
- `endpoint` - Filter by endpoint
- `since` - ISO timestamp for time range

**Response**:
```json
{
  "errors": [
    {
      "id": 1234,
      "timestamp": "2026-04-21T10:43:57Z",
      "error_type": "DatabaseError",
      "message": "Connection timeout",
      "endpoint": "/api/v1/trades",
      "user_id": "admin",
      "stack_trace": "...",
      "context": {
        "request_id": "abc123",
        "ip": "192.168.1.1"
      }
    }
  ],
  "total": 1234
}
```

#### Get Error Aggregation

**Endpoint**: `GET /api/v1/system/aggregation`

**Response**:
```json
{
  "by_type": {
    "DatabaseError": 45,
    "ValidationError": 23,
    "TimeoutError": 12
  },
  "by_endpoint": {
    "/api/v1/trades": 34,
    "/api/v1/signals": 28,
    "/api/v1/dashboard": 18
  }
}
```

#### Get Error Rate

**Endpoint**: `GET /api/v1/system/rate`

**Response**:
```json
{
  "errors_per_minute": 2.5,
  "window_seconds": 60,
  "total_errors": 150
}
```

#### Cleanup Old Errors

**Endpoint**: `POST /api/v1/system/cleanup`

**Query Parameters**:
- `days` (default: 30) - Delete errors older than N days

**Response**:
```json
{
  "deleted": 1523,
  "message": "Deleted 1523 errors older than 30 days"
}
```

## Alert System

### Alert Manager

Automated alerts for critical system events.

**Implementation**: `backend/core/alert_manager.py`

### Alert Types

#### CIRCUIT_BREAKER (Critical)
- **Trigger**: Circuit breaker opened
- **Threshold**: 3-5 consecutive failures
- **Cooldown**: 5 minutes

#### ERROR_RATE (High)
- **Trigger**: Error rate exceeds threshold
- **Threshold**: >10 errors/minute
- **Cooldown**: 5 minutes

#### MEMORY_USAGE (High)
- **Trigger**: Memory usage exceeds threshold
- **Threshold**: >80% memory usage
- **Cooldown**: 5 minutes

#### DISK_SPACE (Critical)
- **Trigger**: Disk space below threshold
- **Threshold**: <10% free space
- **Cooldown**: 5 minutes

#### CONNECTION_POOL (Critical)
- **Trigger**: Database connection pool exhausted
- **Threshold**: All connections in use
- **Cooldown**: 5 minutes

### Alert API

#### Get Alerts

**Endpoint**: `GET /api/v1/system/alerts`

**Query Parameters**:
- `type` - Filter by alert type
- `severity` - Filter by severity (critical, high, medium, low)
- `resolved` - Filter by resolution status (true/false)
- `limit` (default: 100)

**Response**:
```json
{
  "alerts": [
    {
      "id": 456,
      "type": "CIRCUIT_BREAKER",
      "severity": "critical",
      "message": "Database circuit breaker opened",
      "timestamp": "2026-04-21T10:43:57Z",
      "resolved": false,
      "resolved_at": null,
      "context": {
        "breaker_name": "database",
        "failure_count": 5
      }
    }
  ],
  "total": 456
}
```

#### Get Alert Statistics

**Endpoint**: `GET /api/v1/system/alerts/stats`

**Response**:
```json
{
  "by_type": {
    "CIRCUIT_BREAKER": 12,
    "ERROR_RATE": 8,
    "MEMORY_USAGE": 5
  },
  "by_severity": {
    "critical": 15,
    "high": 10
  },
  "unresolved": 3
}
```

#### Resolve Alert

**Endpoint**: `POST /api/v1/system/alerts/{id}/resolve`

**Response**:
```json
{
  "id": 456,
  "resolved": true,
  "resolved_at": "2026-04-21T10:45:00Z"
}
```

#### Get System Metrics

**Endpoint**: `GET /api/v1/system/metrics`

**Response**:
```json
{
  "memory": {
    "total_mb": 16384,
    "used_mb": 7372,
    "percent": 45.0
  },
  "disk": {
    "total_gb": 500,
    "used_gb": 342,
    "free_gb": 158,
    "percent": 68.4
  },
  "connections": {
    "database": {
      "active": 8,
      "idle": 12,
      "total": 20
    },
    "websocket": 42,
    "http": 15
  },
  "circuit_breakers": {
    "database": "closed",
    "polymarket": "closed",
    "kalshi": "closed",
    "redis": "closed"
  }
}
```

## Audit Trail

### Audit Log API

Track all configuration changes for compliance.

**Implementation**: `backend/models/audit_logger.py`

#### Get Audit Logs

**Endpoint**: `GET /api/v1/system/audit-logs`

**Query Parameters**:
- `event_type` - Filter by event type
- `entity_type` - Filter by entity type
- `entity_id` - Filter by entity ID
- `user_id` - Filter by user
- `since` - ISO timestamp for time range
- `limit` (default: 100)

**Response**:
```json
{
  "logs": [
    {
      "id": 789,
      "timestamp": "2026-04-21T10:43:57Z",
      "event_type": "CONFIG_UPDATED",
      "entity_type": "settings",
      "entity_id": "trading_mode",
      "old_value": {"trading_mode": "paper"},
      "new_value": {"trading_mode": "live"},
      "user_id": "admin"
    }
  ],
  "total": 789
}
```

### Logged Events

- `CONFIG_UPDATED` - System settings changes
- `STRATEGY_CONFIG_UPDATED` - Strategy configuration changes
- `STRATEGY_TOGGLE` - Strategy enable/disable
- `MIROFISH_TOGGLE` - MiroFish integration toggle
- `AI_TOGGLE` - AI-enhanced signals toggle

## Monitoring Best Practices

### Recommended Dashboards

**1. System Health Dashboard**
- Health check status (all 3 endpoints)
- Circuit breaker states
- Memory and disk usage
- Active connections

**2. Performance Dashboard**
- API response time (p50, p95, p99)
- Database query latency
- WebSocket message rate
- Request throughput

**3. Error Dashboard**
- Error rate over time
- Error aggregation by type
- Top failing endpoints
- Recent critical errors

**4. Alert Dashboard**
- Active alerts by severity
- Alert history
- Mean time to resolution
- Alert frequency by type

### Recommended Alerts

**Critical Alerts** (page on-call):
- Circuit breaker opened
- Disk space <10%
- Connection pool exhausted
- Health check failing

**High Priority Alerts** (notify team):
- Error rate >10/minute
- Memory usage >80%
- API latency p99 >1s
- Database latency p99 >500ms

**Medium Priority Alerts** (log only):
- Rate limit exceeded frequently
- WebSocket disconnections >10/minute
- Backup verification failed

### Monitoring Tools Integration

**Grafana**:
- Import Prometheus metrics
- Create custom dashboards
- Set up alert rules

**Datadog**:
- Use `/health/detailed` endpoint
- Custom metrics via StatsD
- APM integration

**PagerDuty**:
- Integrate with alert system
- Route critical alerts to on-call
- Escalation policies

**Slack**:
- Webhook integration for alerts
- Error notifications
- Daily summary reports

## Log Files

### Application Logs

**Location**: `logs/app.log`

**Format**: JSON structured logging

**Rotation**: Daily, keep 30 days

### Backup Logs

**Location**: `logs/backup.log`

**Format**: Timestamped text

**Rotation**: Weekly, keep 90 days

### Alert Logs

**Location**: `logs/backup_alerts.log`

**Format**: Timestamped text with severity

**Rotation**: Monthly, keep 1 year

### Error Logs

**Location**: Database table `error_logs`

**Retention**: 30 days (configurable)

**Cleanup**: Automated via `/api/v1/system/cleanup`
