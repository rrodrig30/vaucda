#!/usr/bin/env python3
"""
VAUCDA Neo4j Schema Initialization Script
==========================================

This script initializes the Neo4j database schema for VAUCDA, including:
- Creating constraints and indexes
- Validating schema deployment
- Optionally loading sample data

Usage:
    python init_neo4j_schema.py --uri bolt://localhost:7687 --user neo4j --password <password>
    python init_neo4j_schema.py --load-sample-data
    python init_neo4j_schema.py --verify-only

Requirements:
    pip install neo4j python-dotenv
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from neo4j import GraphDatabase, Session
from neo4j.exceptions import ServiceUnavailable, AuthError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Path constants
SCRIPT_DIR = Path(__file__).parent.parent
SCHEMA_DIR = SCRIPT_DIR / 'schema'
SCHEMA_FILE = SCHEMA_DIR / 'neo4j_schema.cypher'
SAMPLE_DATA_FILE = SCHEMA_DIR / 'sample_data' / 'load_sample_data.cypher'


class Neo4jSchemaInitializer:
    """Initialize and validate Neo4j schema for VAUCDA."""

    def __init__(self, uri: str, user: str, password: str):
        """
        Initialize Neo4j connection.

        Args:
            uri: Neo4j connection URI (e.g., bolt://localhost:7687)
            user: Neo4j username
            password: Neo4j password
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None

    def connect(self) -> bool:
        """
        Connect to Neo4j database.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            # Test connection
            with self.driver.session() as session:
                result = session.run("RETURN 1 AS test")
                result.single()
            logger.info(f"✓ Connected to Neo4j at {self.uri}")
            return True
        except ServiceUnavailable as e:
            logger.error(f"✗ Cannot connect to Neo4j at {self.uri}: {e}")
            return False
        except AuthError as e:
            logger.error(f"✗ Authentication failed: {e}")
            return False
        except Exception as e:
            logger.error(f"✗ Unexpected error connecting to Neo4j: {e}")
            return False

    def close(self):
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            logger.info("✓ Closed Neo4j connection")

    def execute_cypher_file(self, file_path: Path) -> bool:
        """
        Execute Cypher statements from file.

        Args:
            file_path: Path to .cypher file

        Returns:
            True if successful, False otherwise
        """
        if not file_path.exists():
            logger.error(f"✗ File not found: {file_path}")
            return False

        logger.info(f"Executing Cypher from: {file_path.name}")

        try:
            with open(file_path, 'r') as f:
                cypher_content = f.read()

            # Split on semicolons (basic approach - doesn't handle all cases)
            statements = [
                stmt.strip() for stmt in cypher_content.split(';')
                if stmt.strip() and not stmt.strip().startswith('//')
            ]

            with self.driver.session() as session:
                for i, statement in enumerate(statements):
                    # Skip comments and empty statements
                    if statement.startswith('/*') or not statement:
                        continue

                    try:
                        session.run(statement)
                        logger.debug(f"  Executed statement {i+1}/{len(statements)}")
                    except Exception as e:
                        # Some statements may fail if already exist (e.g., constraints)
                        if "already exists" in str(e).lower():
                            logger.debug(f"  Statement {i+1} already exists (skipping)")
                        else:
                            logger.warning(f"  Statement {i+1} failed: {e}")

            logger.info(f"✓ Executed {len(statements)} statements from {file_path.name}")
            return True

        except Exception as e:
            logger.error(f"✗ Error executing Cypher file: {e}")
            return False

    def create_schema(self) -> bool:
        """
        Create database schema (constraints, indexes).

        Returns:
            True if successful, False otherwise
        """
        logger.info("=" * 60)
        logger.info("Creating VAUCDA Neo4j Schema")
        logger.info("=" * 60)

        if not self.execute_cypher_file(SCHEMA_FILE):
            return False

        logger.info("✓ Schema creation complete")
        return True

    def load_sample_data(self) -> bool:
        """
        Load sample data for testing.

        Returns:
            True if successful, False otherwise
        """
        logger.info("=" * 60)
        logger.info("Loading Sample Data")
        logger.info("=" * 60)

        if not self.execute_cypher_file(SAMPLE_DATA_FILE):
            return False

        logger.info("✓ Sample data loaded successfully")
        return True

    def wait_for_indexes(self, timeout_seconds: int = 300) -> bool:
        """
        Wait for all indexes to come online.

        Args:
            timeout_seconds: Maximum time to wait (default: 5 minutes)

        Returns:
            True if all indexes online, False on timeout
        """
        logger.info(f"Waiting for indexes to populate (timeout: {timeout_seconds}s)...")

        try:
            with self.driver.session() as session:
                result = session.run(f"CALL db.awaitIndexes({timeout_seconds})")
                result.consume()
            logger.info("✓ All indexes are online")
            return True
        except Exception as e:
            logger.error(f"✗ Error waiting for indexes: {e}")
            return False

    def verify_constraints(self) -> Dict[str, int]:
        """
        Verify constraints were created.

        Returns:
            Dictionary with constraint counts by type
        """
        logger.info("Verifying constraints...")

        try:
            with self.driver.session() as session:
                result = session.run("SHOW CONSTRAINTS")
                constraints = [record for record in result]

            uniqueness_count = sum(1 for c in constraints if 'UNIQUE' in str(c.get('type', '')))
            existence_count = sum(1 for c in constraints if 'EXISTS' in str(c.get('type', '')))

            logger.info(f"  Uniqueness constraints: {uniqueness_count}")
            logger.info(f"  Existence constraints: {existence_count}")
            logger.info(f"  Total constraints: {len(constraints)}")

            return {
                'uniqueness': uniqueness_count,
                'existence': existence_count,
                'total': len(constraints)
            }
        except Exception as e:
            logger.error(f"✗ Error verifying constraints: {e}")
            return {}

    def verify_indexes(self) -> Dict[str, int]:
        """
        Verify indexes were created.

        Returns:
            Dictionary with index counts by type
        """
        logger.info("Verifying indexes...")

        try:
            with self.driver.session() as session:
                result = session.run("SHOW INDEXES")
                indexes = [record for record in result]

            vector_count = sum(1 for idx in indexes if idx.get('type') == 'VECTOR')
            fulltext_count = sum(1 for idx in indexes if idx.get('type') == 'FULLTEXT')
            property_count = sum(1 for idx in indexes if idx.get('type') in ['RANGE', 'BTREE', 'LOOKUP'])

            logger.info(f"  Vector indexes: {vector_count}")
            logger.info(f"  Full-text indexes: {fulltext_count}")
            logger.info(f"  Property indexes: {property_count}")
            logger.info(f"  Total indexes: {len(indexes)}")

            # Verify vector indexes are online
            vector_indexes_online = sum(
                1 for idx in indexes
                if idx.get('type') == 'VECTOR' and idx.get('state') == 'ONLINE'
            )
            logger.info(f"  Vector indexes online: {vector_indexes_online}/{vector_count}")

            return {
                'vector': vector_count,
                'fulltext': fulltext_count,
                'property': property_count,
                'total': len(indexes),
                'vector_online': vector_indexes_online
            }
        except Exception as e:
            logger.error(f"✗ Error verifying indexes: {e}")
            return {}

    def verify_node_counts(self) -> Dict[str, int]:
        """
        Count nodes by type.

        Returns:
            Dictionary with node counts by label
        """
        logger.info("Verifying node counts...")

        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (n)
                    RETURN labels(n)[0] AS node_type, count(n) AS count
                    ORDER BY count DESC
                """)
                node_counts = {record['node_type']: record['count'] for record in result}

            for node_type, count in node_counts.items():
                logger.info(f"  {node_type}: {count}")

            return node_counts
        except Exception as e:
            logger.error(f"✗ Error counting nodes: {e}")
            return {}

    def verify_relationship_counts(self) -> Dict[str, int]:
        """
        Count relationships by type.

        Returns:
            Dictionary with relationship counts by type
        """
        logger.info("Verifying relationship counts...")

        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH ()-[r]->()
                    RETURN type(r) AS relationship_type, count(r) AS count
                    ORDER BY count DESC
                """)
                rel_counts = {record['relationship_type']: record['count'] for record in result}

            for rel_type, count in rel_counts.items():
                logger.info(f"  {rel_type}: {count}")

            return rel_counts
        except Exception as e:
            logger.error(f"✗ Error counting relationships: {e}")
            return {}

    def verify_schema(self) -> bool:
        """
        Comprehensive schema verification.

        Returns:
            True if schema valid, False otherwise
        """
        logger.info("=" * 60)
        logger.info("Verifying VAUCDA Neo4j Schema")
        logger.info("=" * 60)

        all_checks_passed = True

        # Verify constraints
        constraint_counts = self.verify_constraints()
        if not constraint_counts or constraint_counts.get('total', 0) < 10:
            logger.error("✗ Insufficient constraints created")
            all_checks_passed = False
        else:
            logger.info("✓ Constraints verification passed")

        # Verify indexes
        index_counts = self.verify_indexes()
        if not index_counts or index_counts.get('total', 0) < 20:
            logger.error("✗ Insufficient indexes created")
            all_checks_passed = False
        else:
            logger.info("✓ Indexes verification passed")

        # Verify vector indexes are online
        if index_counts.get('vector', 0) != index_counts.get('vector_online', 0):
            logger.warning("⚠ Some vector indexes are not online yet")

        return all_checks_passed

    def verify_data(self) -> bool:
        """
        Verify sample data was loaded.

        Returns:
            True if data present, False otherwise
        """
        logger.info("=" * 60)
        logger.info("Verifying Sample Data")
        logger.info("=" * 60)

        node_counts = self.verify_node_counts()
        rel_counts = self.verify_relationship_counts()

        if not node_counts or sum(node_counts.values()) == 0:
            logger.error("✗ No nodes found - sample data may not be loaded")
            return False

        logger.info("✓ Data verification passed")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Initialize VAUCDA Neo4j schema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize schema
  python init_neo4j_schema.py --uri bolt://localhost:7687 --user neo4j --password mypassword

  # Initialize schema and load sample data
  python init_neo4j_schema.py --load-sample-data

  # Verify existing schema only
  python init_neo4j_schema.py --verify-only

Environment Variables:
  NEO4J_URI       - Neo4j connection URI (default: bolt://localhost:7687)
  NEO4J_USER      - Neo4j username (default: neo4j)
  NEO4J_PASSWORD  - Neo4j password (required if not provided via --password)
        """
    )

    parser.add_argument(
        '--uri',
        default=os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
        help='Neo4j connection URI'
    )
    parser.add_argument(
        '--user',
        default=os.getenv('NEO4J_USER', 'neo4j'),
        help='Neo4j username'
    )
    parser.add_argument(
        '--password',
        default=os.getenv('NEO4J_PASSWORD'),
        help='Neo4j password'
    )
    parser.add_argument(
        '--load-sample-data',
        action='store_true',
        help='Load sample data after schema creation'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing schema (do not create)'
    )
    parser.add_argument(
        '--skip-wait-indexes',
        action='store_true',
        help='Skip waiting for indexes to populate'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set log level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate password
    if not args.password:
        logger.error("✗ Neo4j password is required (--password or NEO4J_PASSWORD env var)")
        sys.exit(1)

    # Initialize schema manager
    initializer = Neo4jSchemaInitializer(args.uri, args.user, args.password)

    try:
        # Connect to Neo4j
        if not initializer.connect():
            sys.exit(1)

        if args.verify_only:
            # Verification only
            if not initializer.verify_schema():
                sys.exit(1)
            if args.load_sample_data:
                if not initializer.verify_data():
                    sys.exit(1)
        else:
            # Create schema
            if not initializer.create_schema():
                sys.exit(1)

            # Wait for indexes to populate
            if not args.skip_wait_indexes:
                if not initializer.wait_for_indexes():
                    logger.warning("⚠ Timeout waiting for indexes - they may still be populating")

            # Verify schema
            if not initializer.verify_schema():
                sys.exit(1)

            # Load sample data if requested
            if args.load_sample_data:
                if not initializer.load_sample_data():
                    sys.exit(1)
                if not initializer.verify_data():
                    sys.exit(1)

        logger.info("=" * 60)
        logger.info("✓ VAUCDA Neo4j Schema Initialization Complete")
        logger.info("=" * 60)

    except KeyboardInterrupt:
        logger.info("\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        initializer.close()


if __name__ == '__main__':
    main()
