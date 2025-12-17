#!/usr/bin/env python3
"""
Neo4j Monitoring Script for VAUCDA

Collects and reports key database metrics:
- Connection status
- Index health
- Session counts
- Query performance
- Database statistics
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Dict, Any

# Add backend to path
sys.path.insert(0, '/home/gulab/PythonProjects/VAUCDA/backend')

from database.neo4j_client import Neo4jClient, Neo4jConfig


async def check_connection(client: Neo4jClient) -> Dict[str, Any]:
    """Check database connectivity."""
    is_connected = await client.verify_connectivity()
    return {
        "status": "healthy" if is_connected else "unhealthy",
        "connected": is_connected
    }


async def check_indexes(client: Neo4jClient) -> Dict[str, Any]:
    """Check vector index status."""
    indexes = await client.check_vector_indexes()

    all_online = all(state == "ONLINE" for state in indexes.values())

    return {
        "status": "healthy" if all_online else "degraded",
        "indexes": indexes
    }


async def get_session_counts(client: Neo4jClient) -> Dict[str, Any]:
    """Get active and total session counts."""
    query_active = """
    MATCH (s:Session {status: 'active'})
    WHERE s.expires_at > datetime()
    RETURN count(s) AS active_count
    """

    query_total = """
    MATCH (s:Session)
    RETURN count(s) AS total_count
    """

    async with client.driver.session() as session:
        result_active = await session.run(query_active)
        active_record = await result_active.single()
        active_count = active_record["active_count"] if active_record else 0

        result_total = await session.run(query_total)
        total_record = await result_total.single()
        total_count = total_record["total_count"] if total_record else 0

    return {
        "active_sessions": active_count,
        "total_sessions": total_count
    }


async def get_database_stats(client: Neo4jClient) -> Dict[str, Any]:
    """Get database statistics."""
    query = """
    MATCH (n)
    WITH labels(n) AS nodeLabels, count(n) AS nodeCount
    UNWIND nodeLabels AS label
    RETURN label, sum(nodeCount) AS total_nodes
    ORDER BY total_nodes DESC
    """

    async with client.driver.session() as session:
        result = await session.run(query)

        stats = {}
        async for record in result:
            stats[record["label"]] = record["total_nodes"]

    return stats


async def get_query_performance(client: Neo4jClient) -> Dict[str, Any]:
    """Get slow query statistics from logs."""
    # This would parse query logs for slow queries
    # For now, return placeholder
    return {
        "slow_queries_last_hour": 0,
        "avg_query_time_ms": 0
    }


async def main():
    """Main monitoring function."""
    print("=" * 80)
    print(f"VAUCDA Neo4j Monitoring Report")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    # Initialize client
    config = Neo4jConfig()
    client = Neo4jClient(config)

    try:
        # Connection check
        print("📡 Connection Status:")
        connection_status = await check_connection(client)
        print(f"  Status: {connection_status['status'].upper()}")
        print(f"  Connected: {connection_status['connected']}")
        print()

        if not connection_status['connected']:
            print("❌ Cannot connect to Neo4j. Exiting.")
            return 1

        # Index health
        print("🔍 Index Health:")
        index_status = await check_indexes(client)
        print(f"  Status: {index_status['status'].upper()}")
        for index_name, state in index_status['indexes'].items():
            status_icon = "✅" if state == "ONLINE" else "⚠️"
            print(f"  {status_icon} {index_name}: {state}")
        print()

        # Session counts
        print("👥 Session Statistics:")
        session_stats = await get_session_counts(client)
        print(f"  Active Sessions: {session_stats['active_sessions']}")
        print(f"  Total Sessions: {session_stats['total_sessions']}")
        print()

        # Database statistics
        print("📊 Database Statistics:")
        db_stats = await get_database_stats(client)
        for label, count in db_stats.items():
            print(f"  {label}: {count:,} nodes")
        print()

        # Query performance
        print("⚡ Query Performance:")
        perf_stats = await get_query_performance(client)
        print(f"  Slow Queries (last hour): {perf_stats['slow_queries_last_hour']}")
        print(f"  Avg Query Time: {perf_stats['avg_query_time_ms']}ms")
        print()

        print("=" * 80)
        print("✅ Monitoring report completed successfully")
        print("=" * 80)

        return 0

    except Exception as e:
        print(f"❌ ERROR: {e}")
        return 1

    finally:
        await client.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
