# VAUCDA Load Testing Suite

## Overview

This directory contains comprehensive load testing tools for VAUCDA using Locust.

## Prerequisites

```bash
pip install locust
```

## Test Scenarios

### 1. Baseline Test (10 concurrent users)

Validates basic functionality under light load.

```bash
locust -f locustfile.py --users 10 --spawn-rate 2 --host http://localhost:8000 --run-time 5m
```

**Expected Results:**
- 0% error rate
- All response times < 3s
- CPU < 30%
- Memory < 2GB

### 2. Target Load (500 concurrent users)

Production target capacity.

```bash
locust -f locustfile.py --users 500 --spawn-rate 10 --host http://localhost:8000 --run-time 10m
```

**Expected Results:**
- < 1% error rate
- 95th percentile < 5s
- CPU < 80%
- Memory < 8GB

### 3. Stress Test (1000 concurrent users)

Maximum capacity testing.

```bash
locust -f locustfile.py --users 1000 --spawn-rate 20 --host http://localhost:8000 --run-time 5m
```

**Expected Results:**
- Identify breaking point
- Graceful degradation
- No crashes or data corruption

### 4. Spike Test

Sudden traffic increase.

```bash
locust -f locustfile.py --users 100 --spawn-rate 100 --host http://localhost:8000 --run-time 2m
```

### 5. Endurance Test (24 hours)

Long-running stability test.

```bash
locust -f locustfile.py --users 200 --spawn-rate 5 --host http://localhost:8000 --run-time 24h
```

## Web UI Mode

Launch interactive web interface:

```bash
locust -f locustfile.py --host http://localhost:8000
```

Then open http://localhost:8089

## Headless Mode with Reports

Generate HTML and CSV reports:

```bash
locust -f locustfile.py --headless --users 500 --spawn-rate 10 \
       --run-time 10m --host http://localhost:8000 \
       --html=report.html --csv=results
```

## Test Data Setup

Before running load tests, create test users:

```bash
cd /home/gulab/PythonProjects/VAUCDA/backend
python tests/load_tests/setup_test_users.py
```

## Monitoring During Tests

### System Resources

```bash
# CPU and Memory
watch -n 1 docker stats

# API Logs
docker logs -f vaucda-api

# Database Connections
docker exec vaucda-neo4j cypher-shell -u neo4j -p password \
  "CALL dbms.listConnections() YIELD connectionId RETURN count(*)"

# Redis Metrics
redis-cli -a <password> INFO stats
```

### Application Metrics

```bash
# Request rate
curl http://localhost:8000/api/v1/health | jq '.metrics.requests_per_second'

# Active users
curl http://localhost:8000/api/v1/health | jq '.metrics.active_users'
```

## Results Analysis

### Key Metrics

1. **Response Time Distribution**
   - 50th percentile (median): < 2s
   - 95th percentile: < 5s
   - 99th percentile: < 10s

2. **Throughput**
   - Target: > 100 requests/second
   - Note generation: > 10/second

3. **Error Rate**
   - Target: < 1%
   - No 5xx errors

4. **Resource Usage**
   - CPU: < 80%
   - Memory: < 8GB
   - Database connections: < 100

### Sample Analysis Commands

```bash
# Parse CSV results
python -c "
import pandas as pd
df = pd.read_csv('results_stats.csv')
print('Response Time Summary:')
print(df[['Name', 'Average Response Time', '95%']].to_string())
print('\nError Summary:')
print(df[['Name', '# Failures', 'Failure %']].to_string())
"

# Extract slow requests
awk -F',' '$3 > 5000 {print $1, $3}' results_stats.csv
```

## Common Issues

### High Error Rate

**Symptoms:** > 5% errors

**Possible Causes:**
- Database connection pool exhausted
- LLM provider rate limits
- Memory exhaustion

**Solutions:**
```bash
# Increase connection pool
export DATABASE_POOL_SIZE=50

# Enable connection pooling for Neo4j
export NEO4J_MAX_CONNECTION_POOL_SIZE=100

# Add Redis connection pool
export REDIS_MAX_CONNECTIONS=50
```

### Slow Response Times

**Symptoms:** 95th percentile > 10s

**Possible Causes:**
- Ollama model not loaded
- Neo4j vector index not optimized
- No caching

**Solutions:**
```bash
# Preload Ollama model
curl http://localhost:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":-1}'

# Create Neo4j indexes
docker exec vaucda-neo4j cypher-shell -u neo4j -p password < scripts/optimize_indexes.cypher

# Enable Redis caching
export ENABLE_REDIS_CACHE=true
```

### Memory Leaks

**Symptoms:** Memory usage continually increases

**Solutions:**
```bash
# Enable memory profiling
pip install memory-profiler
python -m memory_profiler app/main.py

# Check for session cleanup
grep "session cleanup" docker logs vaucda-api
```

## Distributed Load Testing

For testing from multiple machines:

### Master Node

```bash
locust -f locustfile.py --master --host http://production.va.gov
```

### Worker Nodes

```bash
locust -f locustfile.py --worker --master-host=<master-ip>
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Load Test

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  load-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Start VAUCDA
        run: docker-compose up -d

      - name: Wait for services
        run: sleep 60

      - name: Run load test
        run: |
          pip install locust
          locust -f backend/tests/load_tests/locustfile.py \
                 --headless --users 100 --spawn-rate 10 \
                 --run-time 5m --host http://localhost:8000 \
                 --html=report.html --csv=results

      - name: Check results
        run: |
          ERRORS=$(awk -F',' 'NR>1 {sum+=$6} END {print sum}' results_stats.csv)
          if [ $ERRORS -gt 10 ]; then
            echo "Too many errors: $ERRORS"
            exit 1
          fi

      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: load-test-results
          path: |
            report.html
            results_*.csv
```

## Best Practices

1. **Warm Up**: Always allow 1-2 minutes for warm-up before measuring
2. **Baseline**: Run baseline test before every change
3. **Isolation**: Run tests in isolated environment
4. **Monitoring**: Monitor all system resources during tests
5. **Repeatability**: Run tests 3 times and average results
6. **Documentation**: Document all test configurations and results

## Troubleshooting

### Connection Refused

```bash
# Check if API is running
curl http://localhost:8000/api/v1/health

# Check Docker containers
docker ps | grep vaucda
```

### Authentication Failures

```bash
# Create test users
python tests/load_tests/setup_test_users.py

# Verify credentials
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"loadtest1@va.gov","password":"LoadTest123!@#"}'
```

### Rate Limiting

```bash
# Adjust rate limits
export RATE_LIMIT_PER_MINUTE=1000

# Disable rate limiting for testing (NOT for production)
export DISABLE_RATE_LIMITING=true
```

## Performance Optimization Tips

1. **Enable caching:**
   ```bash
   export ENABLE_REDIS_CACHE=true
   export CACHE_TTL_SECONDS=300
   ```

2. **Optimize database queries:**
   ```cypher
   // Create indexes
   CREATE INDEX ON :Guideline(embedding);
   CREATE INDEX ON :Document(title);
   ```

3. **Use connection pooling:**
   ```python
   # In config.py
   DATABASE_POOL_SIZE=50
   NEO4J_MAX_CONNECTION_POOL_SIZE=100
   ```

4. **Enable HTTP/2:**
   ```nginx
   listen 443 ssl http2;
   ```

5. **Compress responses:**
   ```python
   # In main.py
   app.add_middleware(GZipMiddleware, minimum_size=1000)
   ```

## References

- [Locust Documentation](https://docs.locust.io/)
- [Performance Testing Best Practices](https://www.perfmatrix.com/performance-testing-best-practices/)
- [VA Performance Requirements](https://www.oit.va.gov/library/recurring/edm/)
