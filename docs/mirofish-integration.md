# MiroFish Integration

Technical documentation for the MiroFish dual debate system integration in PolyEdge.

## Overview

MiroFish provides AI-powered signal analysis through an external debate API. When enabled, PolyEdge routes debate requests to MiroFish instead of using the local debate engine. The system includes automatic fallback to local debate if MiroFish is unavailable or fails.

## Architecture

### Components

1. **MiroFishClient** (`backend/ai/mirofish_client.py`)
   - HTTP client for MiroFish API
   - Exponential backoff retry (3 attempts: 1s, 5s, 10s)
   - Circuit breaker tracking for consecutive failures
   - Credential priority: Database → Environment → Defaults

2. **Debate Router** (`backend/ai/debate_router.py`)
   - Routes debate requests based on `mirofish_enabled` flag
   - Converts MiroFish signals to DebateResult format
   - Automatic fallback to local debate on failure
   - Preserves all debate parameters for fallback

3. **Settings API** (`backend/api/settings.py`)
   - GET/PUT endpoints for MiroFish credentials
   - POST `/api/v1/settings/test-mirofish` for connection testing
   - Admin authentication required for all operations

4. **Settings UI** (`frontend/src/pages/Settings.tsx`)
   - Toggle switch for enabling/disabling MiroFish
   - Credential inputs (API URL, API Key)
   - Test Connection button with real-time feedback
   - Validation prevents enabling without successful test

### Data Flow

```
Scanner Strategy
    ↓
debate_router.run_debate_with_routing()
    ↓
Check mirofish_enabled flag in SystemSettings
    ↓
    ├─ Enabled → MiroFishClient.fetch_signals()
    │              ↓
    │          Convert signals to DebateResult
    │              ↓
    │          Return weighted consensus
    │
    └─ Disabled/Failed → run_debate() (local)
                            ↓
                        Return local DebateResult
```

## Configuration

### Environment Variables

```bash
# MiroFish API endpoint
MIROFISH_API_URL=https://api.mirofish.ai/v1

# MiroFish authentication key
MIROFISH_API_KEY=your-api-key-here

# Request timeout in seconds
MIROFISH_API_TIMEOUT=10
```

### Database Settings

Credentials stored in `SystemSettings` table with higher priority than environment variables:

- `mirofish_enabled` (boolean) - Enable/disable flag
- `mirofish_api_url` (string) - API endpoint URL
- `mirofish_api_key` (string) - Authentication key
- `mirofish_api_timeout` (float) - Request timeout

### Settings UI

1. Navigate to Admin → Settings
2. Scroll to MiroFish Integration section
3. Enter API URL and API Key
4. Click "Test Connection" to validate credentials
5. Toggle switch to enable (requires successful test)

## API Reference

### Test Connection Endpoint

**POST** `/api/v1/settings/test-mirofish`

Tests MiroFish credentials without saving to database.

**Request:**
```json
{
  "api_url": "https://api.mirofish.ai/v1",
  "api_key": "your-api-key"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Connection successful",
  "latency_ms": 245,
  "signals_count": 3
}
```

**Response (Failure):**
```json
{
  "success": false,
  "message": "Connection failed",
  "error": "authentication_failed"
}
```

**Error Types:**
- `authentication_failed` - Invalid API key (401)
- `not_found` - Invalid endpoint URL (404)
- `timeout` - Request exceeded timeout limit
- `connection_error` - Network/DNS failure

### MiroFish Signal Format

**Request to MiroFish:**
```json
{
  "market_id": "0x1234...",
  "question": "Will BTC be above $100K on Friday?",
  "market_price": 0.65,
  "context": {
    "volume": 125000,
    "category": "crypto"
  }
}
```

**Response from MiroFish:**
```json
{
  "signals": [
    {
      "market_id": "0x1234...",
      "prediction": 0.75,
      "confidence": 0.82,
      "reasoning": "Strong momentum indicators...",
      "source": "mirofish"
    }
  ]
}
```

## Fallback Behavior

The system automatically falls back to local debate in these scenarios:

1. **MiroFish Disabled**: `mirofish_enabled` flag is `false`
2. **Empty Signals**: MiroFish returns zero signals
3. **API Failure**: Connection timeout, authentication error, or HTTP error
4. **Exception**: Any unhandled exception during MiroFish call

Fallback preserves all original debate parameters:
- `question` - Market question text
- `market_price` - Current market price
- `max_rounds` - Debate round limit
- `data_sources` - Available data sources
- `signal_votes` - Existing signal votes

## Signal Conversion

MiroFish signals are converted to DebateResult format:

### Weighted Consensus Calculation

```python
# Confidence used as weight
total_weight = sum(signal.confidence for signal in signals)
weighted_prediction = sum(
    signal.prediction * signal.confidence 
    for signal in signals
) / total_weight
```

### SignalVote Creation

Each MiroFish signal becomes a SignalVote:
- `agent_name`: "mirofish"
- `vote`: signal.prediction (0.0-1.0)
- `confidence`: signal.confidence (0.0-1.0)
- `reasoning`: signal.reasoning

### DebateResult Fields

- `final_prediction`: Weighted consensus prediction
- `confidence`: Weighted average confidence
- `reasoning`: Combined reasoning from all signals
- `data_sources`: ["mirofish"]
- `signal_votes`: List of SignalVote objects
- `latency_ms`: Full API round-trip time

## Error Handling

### Retry Logic

MiroFishClient implements exponential backoff:
1. First attempt: immediate
2. Second attempt: 1 second delay
3. Third attempt: 5 seconds delay
4. Fourth attempt: 10 seconds delay

After 3 retries, returns empty signal list (triggers fallback).

### Circuit Breaker

Tracks consecutive failures:
- Threshold: 5 consecutive failures
- State: OPEN (blocks requests) or CLOSED (allows requests)
- Reset: Automatic after timeout period

### Timeout Protection

Two-level timeout:
1. MiroFishClient timeout (from settings)
2. asyncio.wait_for() wrapper (10 seconds)

Timeout triggers fallback to local debate.

### Logging

All errors logged with context:
```python
logger.warning(
    "MiroFish API failed, falling back to local debate",
    extra={
        "error": str(e),
        "market_id": market_id,
        "fallback": "local_debate"
    }
)
```

## Testing

### Unit Tests

**MiroFishClient** (`backend/tests/test_mirofish_client.py`):
- Database priority over environment variables
- Environment variable fallback
- Default value fallback
- Retry logic with exponential backoff
- Timeout handling
- Empty signal list handling

**Debate Router** (`backend/tests/test_debate_router.py`):
- MiroFish enabled with success
- MiroFish disabled fallback
- Empty signals fallback
- Exception fallback
- Weighted consensus calculation
- Parameter preservation

**Scanner Integration** (`backend/tests/test_general_scanner.py`):
- Scanner uses debate router
- Router integration transparent
- Fallback behavior preserved

### Integration Tests

Test full pipeline:
1. Enable MiroFish in settings
2. Trigger scanner strategy
3. Verify MiroFish API called
4. Verify signal conversion
5. Verify fallback on failure

### Manual Testing

1. **Test Connection Button**:
   - Enter valid credentials → green checkmark
   - Enter invalid credentials → red error message
   - Test timeout → timeout error

2. **Enable/Disable Toggle**:
   - Cannot enable without successful test
   - Can disable at any time
   - State persists across page reloads

3. **Fallback Verification**:
   - Enable MiroFish with invalid URL
   - Trigger scanner
   - Verify local debate used (check logs)

## Troubleshooting

### Connection Test Fails

**Symptom**: Red error message after clicking "Test Connection"

**Solutions**:
- Verify API URL is correct (include `/v1` path)
- Check API key is valid (no extra spaces)
- Confirm MiroFish service is running
- Check network connectivity
- Review backend logs for detailed error

### Toggle Won't Enable

**Symptom**: Toggle switch doesn't turn on

**Solutions**:
- Ensure both API URL and API Key are entered
- Click "Test Connection" and wait for green checkmark
- Refresh page if test succeeded but toggle still disabled
- Check browser console for JavaScript errors

### Signals Not Using MiroFish

**Symptom**: Local debate used despite MiroFish enabled

**Solutions**:
- Verify `mirofish_enabled` flag in database: `SELECT * FROM system_settings WHERE key='mirofish_enabled'`
- Check backend logs for MiroFish API errors
- Confirm scanner is using debate router (not direct debate engine)
- Test MiroFish endpoint manually with curl

### High Latency

**Symptom**: Slow signal generation when MiroFish enabled

**Solutions**:
- Increase `MIROFISH_API_TIMEOUT` setting
- Check MiroFish service performance
- Consider caching MiroFish responses
- Monitor network latency to MiroFish endpoint

## Security Considerations

1. **Credential Storage**: API keys stored in database, never logged in plain text
2. **Admin Authentication**: All settings endpoints require admin token
3. **Audit Logging**: Configuration changes logged with redacted credentials
4. **Input Validation**: API URL and key validated before storage
5. **Error Messages**: Sanitized error messages prevent information leakage

## Performance

### Latency Impact

- MiroFish API call: ~200-500ms typical
- Fallback to local debate: ~50-100ms
- Total overhead: Minimal (async execution)

### Caching Strategy

Consider caching MiroFish responses:
- Cache key: `mirofish:{market_id}:{market_price}`
- TTL: 60 seconds (configurable)
- Invalidation: On market price change > 5%

### Rate Limiting

MiroFish client respects rate limits:
- Exponential backoff on 429 responses
- Circuit breaker prevents request storms
- Fallback ensures system continues operating

## Future Enhancements

1. **Response Caching**: Cache MiroFish signals for 60 seconds
2. **Batch Requests**: Send multiple markets in single API call
3. **Streaming**: WebSocket connection for real-time signals
4. **A/B Testing**: Compare MiroFish vs local debate performance
5. **Metrics Dashboard**: Track MiroFish usage, latency, accuracy
6. **Multi-Provider**: Support multiple debate providers with routing logic
