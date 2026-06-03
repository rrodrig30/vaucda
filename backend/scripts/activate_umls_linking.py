"""
Activate UMLS Concept Linking

This script extracts clinical terms from documents and links them
to UMLS concepts using the NLM REST API.

Run: cd backend && python scripts/activate_umls_linking.py

Requires: UMLS_API_KEY in .env (free from https://uts.nlm.nih.gov/uts/)
"""

import asyncio
import logging
import sys
import time
import re
from pathlib import Path
from typing import List, Dict, Set, Optional

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.neo4j_client import Neo4jClient, Neo4jConfig
from app.config import settings
from rag.umls_linker import UMLSRestAPILinker, UMLSConcept

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Clinical terms to extract from documents
CLINICAL_TERM_PATTERNS = [
    # Prostate conditions
    r'\b(prostate cancer|prostatic adenocarcinoma|PCa)\b',
    r'\b(benign prostatic hyperplasia|BPH|enlarged prostate)\b',
    r'\b(prostatitis|chronic prostatitis)\b',
    r'\b(PSA|prostate[- ]specific antigen)\b',
    r'\b(Gleason|gleason score|gleason grade)\b',
    r'\b(ISUP grade|grade group)\b',
    r'\b(PIRADS|PI-RADS)\b',

    # Kidney conditions
    r'\b(renal cell carcinoma|RCC|kidney cancer)\b',
    r'\b(nephrolithiasis|kidney stones?|renal calcul[ui])\b',
    r'\b(hydronephrosis)\b',
    r'\b(chronic kidney disease|CKD)\b',
    r'\b(acute kidney injury|AKI)\b',

    # Bladder conditions
    r'\b(bladder cancer|urothelial carcinoma|TCC)\b',
    r'\b(overactive bladder|OAB)\b',
    r'\b(urinary incontinence)\b',
    r'\b(interstitial cystitis)\b',
    r'\b(neurogenic bladder)\b',

    # Symptoms
    r'\b(hematuria|blood in urine)\b',
    r'\b(nocturia)\b',
    r'\b(urinary frequency)\b',
    r'\b(urinary urgency)\b',
    r'\b(urinary retention)\b',
    r'\b(dysuria)\b',
    r'\b(LUTS|lower urinary tract symptoms)\b',

    # Procedures
    r'\b(radical prostatectomy|RP)\b',
    r'\b(TURP|transurethral resection)\b',
    r'\b(cystectomy)\b',
    r'\b(nephrectomy)\b',
    r'\b(prostate biopsy)\b',
    r'\b(cystoscopy)\b',
    r'\b(ureteroscopy)\b',

    # Labs and Tests
    r'\b(creatinine|serum creatinine)\b',
    r'\b(eGFR|GFR|glomerular filtration rate)\b',
    r'\b(urinalysis)\b',
    r'\b(urine culture)\b',
    r'\b(testosterone)\b',

    # Questionnaires
    r'\b(IPSS|international prostate symptom score)\b',
    r'\b(AUA symptom score|AUA-SI)\b',
    r'\b(SHIM|IIEF)\b',

    # Treatments
    r'\b(alpha[- ]blocker|tamsulosin|alfuzosin)\b',
    r'\b(5[- ]?alpha[- ]?reductase inhibitor|finasteride|dutasteride)\b',
    r'\b(androgen deprivation therapy|ADT)\b',
    r'\b(radiation therapy|radiotherapy|EBRT)\b',
    r'\b(brachytherapy)\b',
    r'\b(chemotherapy)\b',
    r'\b(immunotherapy)\b',
]


async def get_neo4j_client() -> Neo4jClient:
    """Get connected Neo4j client."""
    config = Neo4jConfig(
        uri=settings.NEO4J_URI,
        username=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        encrypted=settings.NEO4J_ENCRYPTED
    )
    client = Neo4jClient(config)

    if not await client.verify_connectivity():
        raise RuntimeError("Cannot connect to Neo4j")

    return client


def extract_clinical_terms(text: str) -> Set[str]:
    """Extract clinical terms from text using regex patterns."""
    terms = set()
    text_lower = text.lower()

    for pattern in CLINICAL_TERM_PATTERNS:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            # Normalize the term
            term = match.strip().lower()
            if len(term) > 2:
                terms.add(term)

    return terms


async def get_terms_from_documents(client: Neo4jClient) -> Set[str]:
    """Extract clinical terms from all document titles and summaries."""
    logger.info("Extracting clinical terms from documents...")

    all_terms: Set[str] = set()

    async with client.driver.session() as session:
        # Get document titles and summaries
        result = await session.run('''
            MATCH (d:Document)
            RETURN d.title as title, d.summary as summary
            LIMIT 1000
        ''')

        doc_count = 0
        async for record in result:
            title = record['title'] or ''
            summary = record['summary'] or ''

            # Extract terms from title and summary
            terms = extract_clinical_terms(title + ' ' + summary)
            all_terms.update(terms)
            doc_count += 1

        logger.info(f"Processed {doc_count} documents, found {len(all_terms)} unique terms")

    return all_terms


async def get_terms_from_chunks(client: Neo4jClient, sample_size: int = 5000) -> Set[str]:
    """Extract clinical terms from chunk content."""
    logger.info(f"Extracting clinical terms from {sample_size} chunks...")

    all_terms: Set[str] = set()

    async with client.driver.session() as session:
        # Sample chunks from each community
        result = await session.run('''
            MATCH (c:Chunk)-[:BELONGS_TO]->(d:Document)
            WITH c, rand() as r
            ORDER BY r
            LIMIT $sample_size
            RETURN c.content as content
        ''', {'sample_size': sample_size})

        chunk_count = 0
        async for record in result:
            content = record['content'] or ''
            terms = extract_clinical_terms(content)
            all_terms.update(terms)
            chunk_count += 1

            if chunk_count % 1000 == 0:
                logger.info(f"  Processed {chunk_count} chunks, {len(all_terms)} terms so far")

        logger.info(f"Processed {chunk_count} chunks, found {len(all_terms)} unique terms total")

    return all_terms


async def link_terms_to_umls(
    linker: UMLSRestAPILinker,
    terms: Set[str],
    max_concepts_per_term: int = 2
) -> Dict[str, List[UMLSConcept]]:
    """Link clinical terms to UMLS concepts."""
    logger.info(f"Linking {len(terms)} terms to UMLS...")

    results: Dict[str, List[UMLSConcept]] = {}

    term_list = sorted(terms)
    total = len(term_list)

    for i, term in enumerate(term_list):
        try:
            concepts = await linker.link_text(term, max_concepts=max_concepts_per_term)
            if concepts:
                results[term] = concepts
                logger.debug(f"  '{term}' -> {len(concepts)} concepts")

            # Progress update
            if (i + 1) % 10 == 0:
                logger.info(f"  Progress: {i+1}/{total} terms ({len(results)} linked)")

            # Rate limiting - UMLS API has limits
            await asyncio.sleep(0.2)

        except Exception as e:
            logger.warning(f"  Failed to link '{term}': {e}")

    logger.info(f"Linked {len(results)} terms to UMLS concepts")
    return results


async def store_concepts_in_neo4j(
    client: Neo4jClient,
    term_concepts: Dict[str, List[UMLSConcept]]
) -> int:
    """Store UMLS concepts in Neo4j as OntologyConcept nodes."""
    logger.info("Storing concepts in Neo4j...")

    stored = 0
    seen_cuis: Set[str] = set()

    async with client.driver.session() as session:
        for term, concepts in term_concepts.items():
            for concept in concepts:
                if concept.cui in seen_cuis:
                    continue

                try:
                    # Create OntologyConcept node
                    await session.run('''
                        MERGE (o:OntologyConcept {umls_cui: $cui})
                        SET o.preferred_term = $preferred_term,
                            o.semantic_types = $semantic_types,
                            o.synonyms = $synonyms,
                            o.synonyms_text = $synonyms_text,
                            o.snomed_id = $snomed_id,
                            o.icd10_code = $icd10_code,
                            o.definition = $definition,
                            o.source_term = $source_term,
                            o.updated_at = datetime()
                    ''', {
                        'cui': concept.cui,
                        'preferred_term': concept.preferred_term,
                        'semantic_types': concept.semantic_types,
                        'synonyms': concept.synonyms,
                        'synonyms_text': ' '.join(concept.synonyms) if concept.synonyms else '',
                        'snomed_id': concept.snomed_id,
                        'icd10_code': concept.icd10_code,
                        'definition': concept.definition,
                        'source_term': term
                    })

                    seen_cuis.add(concept.cui)
                    stored += 1

                except Exception as e:
                    logger.warning(f"Failed to store concept {concept.cui}: {e}")

    logger.info(f"Stored {stored} unique UMLS concepts")
    return stored


async def link_documents_to_concepts(client: Neo4jClient) -> int:
    """Create relationships between Documents and OntologyConcepts."""
    logger.info("Linking documents to ontology concepts...")

    async with client.driver.session() as session:
        # Link documents to concepts based on title/content matching
        result = await session.run('''
            MATCH (d:Document), (o:OntologyConcept)
            WHERE toLower(d.title) CONTAINS toLower(o.preferred_term)
               OR toLower(d.title) CONTAINS toLower(o.source_term)
            MERGE (d)-[:REFERENCES_CONCEPT]->(o)
            RETURN count(*) as linked
        ''')

        record = await result.single()
        linked = record['linked'] if record else 0

        logger.info(f"Created {linked} document-concept relationships")
        return linked


async def get_database_stats(client: Neo4jClient) -> dict:
    """Get current database statistics."""
    async with client.driver.session() as session:
        result = await session.run('''
            MATCH (d:Document)
            OPTIONAL MATCH (c:Chunk)-[:BELONGS_TO]->(d)
            WITH count(DISTINCT d) as docs, count(c) as chunks
            OPTIONAL MATCH (com:Community)
            WITH docs, chunks, count(com) as communities
            OPTIONAL MATCH (hs:HierarchicalSummary)
            WITH docs, chunks, communities, count(hs) as summaries
            OPTIONAL MATCH (oc:OntologyConcept)
            RETURN docs, chunks, communities, summaries, count(oc) as concepts
        ''')
        record = await result.single()
        return {
            'documents': record['docs'],
            'chunks': record['chunks'],
            'communities': record['communities'],
            'summaries': record['summaries'],
            'concepts': record['concepts']
        }


async def main():
    """Main UMLS linking workflow."""
    print("=" * 70)
    print("UMLS CONCEPT LINKING ACTIVATION")
    print("=" * 70)

    start_time = time.time()

    # Check API key
    api_key = settings.UMLS_API_KEY if hasattr(settings, 'UMLS_API_KEY') else None
    if not api_key:
        import os
        api_key = os.getenv('UMLS_API_KEY')

    if not api_key:
        print("\n   ERROR: UMLS_API_KEY not found in environment.")
        print("   Set it in .env or export UMLS_API_KEY=your_key")
        print("   Get free key at: https://uts.nlm.nih.gov/uts/")
        return

    # Initialize UMLS linker
    print("\n1. Initializing UMLS REST API linker...")
    linker = UMLSRestAPILinker(api_key=api_key)
    print("   Initialized!")

    # Test API connection
    print("\n2. Testing UMLS API connection...")
    test_concepts = await linker.link_text("prostate cancer")
    if test_concepts:
        print(f"   API working! Test query returned {len(test_concepts)} concepts")
        print(f"   Example: {test_concepts[0].preferred_term} (CUI: {test_concepts[0].cui})")
    else:
        print("   WARNING: API test returned no results. Check your API key.")

    # Connect to Neo4j
    print("\n3. Connecting to Neo4j...")
    client = await get_neo4j_client()
    print("   Connected!")

    # Get initial stats
    print("\n4. Current database state:")
    stats = await get_database_stats(client)
    print(f"   Documents:    {stats['documents']}")
    print(f"   Chunks:       {stats['chunks']}")
    print(f"   Communities:  {stats['communities']}")
    print(f"   Summaries:    {stats['summaries']}")
    print(f"   Concepts:     {stats['concepts']}")

    # Extract clinical terms
    print("\n5. Extracting clinical terms...")
    doc_terms = await get_terms_from_documents(client)
    chunk_terms = await get_terms_from_chunks(client, sample_size=3000)

    all_terms = doc_terms.union(chunk_terms)
    print(f"   Found {len(all_terms)} unique clinical terms")

    # Link to UMLS
    print("\n6. Linking terms to UMLS concepts...")
    term_concepts = await link_terms_to_umls(linker, all_terms, max_concepts_per_term=2)
    print(f"   Linked {len(term_concepts)} terms to UMLS")

    # Store in Neo4j
    print("\n7. Storing concepts in Neo4j...")
    stored = await store_concepts_in_neo4j(client, term_concepts)
    print(f"   Stored {stored} OntologyConcept nodes")

    # Create document-concept relationships
    print("\n8. Creating document-concept relationships...")
    linked = await link_documents_to_concepts(client)
    print(f"   Created {linked} relationships")

    # Final stats
    print("\n9. Final database state:")
    final_stats = await get_database_stats(client)
    print(f"   Documents:    {final_stats['documents']}")
    print(f"   Chunks:       {final_stats['chunks']}")
    print(f"   Communities:  {final_stats['communities']}")
    print(f"   Summaries:    {final_stats['summaries']}")
    print(f"   Concepts:     {final_stats['concepts']} (was {stats['concepts']})")

    # Cleanup
    await linker.close()
    await client.close()

    duration = time.time() - start_time
    print(f"\n   Total time: {duration:.1f}s ({duration/60:.1f} minutes)")

    print("\n" + "=" * 70)
    print("UMLS CONCEPT LINKING COMPLETE")
    print("=" * 70)
    print("\nConcepts now available for:")
    print("  - Query expansion with synonyms")
    print("  - SNOMED CT / ICD-10 code lookups")
    print("  - Semantic search enhancement")


if __name__ == "__main__":
    asyncio.run(main())
