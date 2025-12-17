#!/bin/bash
#
# VAUCDA Load Testing Runner
# Comprehensive performance testing automation
#
# Usage:
#   ./run_load_tests.sh [baseline|target|stress|spike|endurance|all]
#

set -e

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"
REPORTS_DIR="$PROJECT_ROOT/reports/load_tests"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# API Configuration
API_HOST="${API_HOST:-http://localhost:8000}"
API_HEALTH_ENDPOINT="$API_HOST/api/v1/health"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check if locust is installed
    if ! command -v locust &> /dev/null; then
        print_error "Locust is not installed"
        print_info "Install with: pip install locust"
        exit 1
    fi
    print_success "Locust installed: $(locust --version)"

    # Check if API is running
    print_info "Checking API availability at $API_HOST"
    if curl -s -f "$API_HEALTH_ENDPOINT" > /dev/null 2>&1; then
        print_success "API is running and healthy"
    else
        print_error "API is not accessible at $API_HOST"
        print_info "Start the API with: docker-compose up -d"
        exit 1
    fi

    # Check if reports directory exists
    if [ ! -d "$REPORTS_DIR" ]; then
        print_info "Creating reports directory: $REPORTS_DIR"
        mkdir -p "$REPORTS_DIR"
    fi

    # Check if test users exist
    print_info "Verifying test users exist"
    python3 "$SCRIPT_DIR/setup_test_users.py" verify || {
        print_warning "Test users not found or invalid"
        print_info "Creating test users..."
        python3 "$SCRIPT_DIR/setup_test_users.py" create
    }

    print_success "All prerequisites met"
    echo
}

# System warm-up
warm_up_system() {
    print_header "System Warm-up"
    print_info "Warming up system for 60 seconds..."

    # Make sample requests to warm up caches
    for i in {1..10}; do
        curl -s "$API_HEALTH_ENDPOINT" > /dev/null 2>&1
        sleep 1
    done

    print_success "System warm-up complete"
    echo
}

# Run baseline test (10 concurrent users)
run_baseline_test() {
    print_header "Running Baseline Test (10 users)"
    print_info "Expected: 0% errors, <3s response time, <30% CPU"

    locust -f "$SCRIPT_DIR/locustfile.py" \
           --headless \
           --users 10 \
           --spawn-rate 2 \
           --run-time 5m \
           --host "$API_HOST" \
           --html "$REPORTS_DIR/baseline_${TIMESTAMP}.html" \
           --csv "$REPORTS_DIR/baseline_${TIMESTAMP}" \
           --logfile "$REPORTS_DIR/baseline_${TIMESTAMP}.log"

    analyze_results "baseline_${TIMESTAMP}"
}

# Run target load test (500 concurrent users)
run_target_load_test() {
    print_header "Running Target Load Test (500 users)"
    print_info "Expected: <1% errors, <5s p95, <80% CPU"

    locust -f "$SCRIPT_DIR/locustfile.py" \
           --headless \
           --users 500 \
           --spawn-rate 10 \
           --run-time 10m \
           --host "$API_HOST" \
           --html "$REPORTS_DIR/target_${TIMESTAMP}.html" \
           --csv "$REPORTS_DIR/target_${TIMESTAMP}" \
           --logfile "$REPORTS_DIR/target_${TIMESTAMP}.log"

    analyze_results "target_${TIMESTAMP}"
}

# Run stress test (1000 concurrent users)
run_stress_test() {
    print_header "Running Stress Test (1000 users)"
    print_info "Expected: System under stress, identify breaking point"

    locust -f "$SCRIPT_DIR/locustfile.py" \
           --headless \
           --users 1000 \
           --spawn-rate 20 \
           --run-time 5m \
           --host "$API_HOST" \
           --html "$REPORTS_DIR/stress_${TIMESTAMP}.html" \
           --csv "$REPORTS_DIR/stress_${TIMESTAMP}" \
           --logfile "$REPORTS_DIR/stress_${TIMESTAMP}.log"

    analyze_results "stress_${TIMESTAMP}"
}

# Run spike test (sudden traffic increase)
run_spike_test() {
    print_header "Running Spike Test (0 to 100 users instantly)"
    print_info "Expected: System handles sudden load increase"

    locust -f "$SCRIPT_DIR/locustfile.py" \
           --headless \
           --users 100 \
           --spawn-rate 100 \
           --run-time 2m \
           --host "$API_HOST" \
           --html "$REPORTS_DIR/spike_${TIMESTAMP}.html" \
           --csv "$REPORTS_DIR/spike_${TIMESTAMP}" \
           --logfile "$REPORTS_DIR/spike_${TIMESTAMP}.log"

    analyze_results "spike_${TIMESTAMP}"
}

# Run endurance test (24 hours)
run_endurance_test() {
    print_header "Running Endurance Test (24 hours)"
    print_warning "This will take 24 hours to complete!"
    print_info "Expected: No memory leaks, stable performance"

    read -p "Are you sure you want to run 24-hour test? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        print_info "Endurance test cancelled"
        return
    fi

    locust -f "$SCRIPT_DIR/locustfile.py" \
           --headless \
           --users 200 \
           --spawn-rate 5 \
           --run-time 24h \
           --host "$API_HOST" \
           --html "$REPORTS_DIR/endurance_${TIMESTAMP}.html" \
           --csv "$REPORTS_DIR/endurance_${TIMESTAMP}" \
           --logfile "$REPORTS_DIR/endurance_${TIMESTAMP}.log"

    analyze_results "endurance_${TIMESTAMP}"
}

# Analyze test results
analyze_results() {
    local test_name=$1
    local csv_file="$REPORTS_DIR/${test_name}_stats.csv"

    if [ ! -f "$csv_file" ]; then
        print_error "Results file not found: $csv_file"
        return
    fi

    print_header "Test Results Analysis: $test_name"

    # Parse CSV results
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Summary Statistics:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Extract key metrics using awk
    awk -F',' '
    BEGIN {
        total_requests = 0
        total_failures = 0
        max_response_time = 0
    }
    NR > 1 {
        requests = $4
        failures = $5
        avg_time = $6
        min_time = $7
        max_time = $8
        p50 = $11
        p95 = $13

        total_requests += requests
        total_failures += failures
        if (max_time > max_response_time) max_response_time = max_time

        if (requests > 0) {
            printf "  %-40s %8d requests | %4.1f%% errors | P95: %6.0fms\n", $1, requests, (failures/requests*100), p95
        }
    }
    END {
        error_rate = (total_requests > 0) ? (total_failures / total_requests * 100) : 0
        printf "\n"
        printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        printf "Total Requests:  %d\n", total_requests
        printf "Total Failures:  %d (%.2f%%)\n", total_failures, error_rate
        printf "Max Response:    %.0f ms\n", max_response_time
        printf "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    }
    ' "$csv_file"

    echo

    # Check if results meet targets
    local error_rate=$(awk -F',' 'NR>1 {r+=$4; f+=$5} END {if(r>0) print (f/r*100); else print 0}' "$csv_file")
    local p95=$(awk -F',' 'NR>1 && $13>0 {sum+=$13; count++} END {if(count>0) print sum/count; else print 0}' "$csv_file")

    echo "Target Validation:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Error rate check
    if (( $(echo "$error_rate < 1.0" | bc -l) )); then
        print_success "Error Rate: ${error_rate}% (Target: <1%)"
    else
        print_error "Error Rate: ${error_rate}% (Target: <1%)"
    fi

    # P95 response time check
    if (( $(echo "$p95 < 5000" | bc -l) )); then
        print_success "P95 Response Time: ${p95}ms (Target: <5000ms)"
    else
        print_error "P95 Response Time: ${p95}ms (Target: <5000ms)"
    fi

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    print_info "Full report: $REPORTS_DIR/${test_name}.html"
    echo
}

# Monitor system resources
monitor_resources() {
    print_header "System Resource Monitoring"

    echo "Docker Container Stats:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" | grep vaucda

    echo
    echo "Database Connection Counts:"

    # Neo4j connections
    if docker ps | grep -q vaucda-neo4j; then
        NEO4J_CONN=$(docker exec vaucda-neo4j cypher-shell -u neo4j -p password \
            "CALL dbms.listConnections() YIELD connectionId RETURN count(*)" 2>/dev/null | tail -1 || echo "N/A")
        echo "  Neo4j: $NEO4J_CONN active connections"
    fi

    # Redis connections
    if docker ps | grep -q vaucda-redis; then
        REDIS_CONN=$(docker exec vaucda-redis redis-cli -a $(grep REDIS_PASSWORD backend/.env | cut -d= -f2) \
            INFO clients | grep connected_clients | cut -d: -f2 | tr -d '\r' || echo "N/A")
        echo "  Redis: $REDIS_CONN active connections"
    fi

    echo
}

# Main script
main() {
    local test_type=${1:-help}

    case $test_type in
        baseline)
            check_prerequisites
            warm_up_system
            run_baseline_test
            monitor_resources
            ;;
        target)
            check_prerequisites
            warm_up_system
            run_target_load_test
            monitor_resources
            ;;
        stress)
            check_prerequisites
            warm_up_system
            run_stress_test
            monitor_resources
            ;;
        spike)
            check_prerequisites
            warm_up_system
            run_spike_test
            monitor_resources
            ;;
        endurance)
            check_prerequisites
            warm_up_system
            run_endurance_test
            monitor_resources
            ;;
        all)
            check_prerequisites
            warm_up_system
            print_warning "Running all tests - this will take ~30 minutes"
            run_baseline_test
            sleep 30
            run_target_load_test
            sleep 30
            run_stress_test
            sleep 30
            run_spike_test
            monitor_resources
            print_success "All load tests complete!"
            ;;
        monitor)
            monitor_resources
            ;;
        help|*)
            cat << EOF
VAUCDA Load Testing Runner

Usage:
    ./run_load_tests.sh [test_type]

Test Types:
    baseline    - Light load test (10 users, 5 minutes)
    target      - Production load test (500 users, 10 minutes)
    stress      - Stress test (1000 users, 5 minutes)
    spike       - Spike test (instant 100 users, 2 minutes)
    endurance   - Long-running test (200 users, 24 hours)
    all         - Run all tests except endurance
    monitor     - Show current resource usage
    help        - Show this help message

Environment Variables:
    API_HOST    - API endpoint (default: http://localhost:8000)

Examples:
    ./run_load_tests.sh baseline
    ./run_load_tests.sh target
    API_HOST=https://staging.va.gov ./run_load_tests.sh all

Reports are saved to: $REPORTS_DIR
EOF
            ;;
    esac
}

# Run main function
main "$@"
