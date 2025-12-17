// ============================================================================
// VAUCDA Schema Migration 001: Ambient Listening Support
// ============================================================================
// Version: 1.1
// Date: 2025-12-01
// Purpose: Add schema support for future ambient listening capabilities
// Status: PLANNED (Not yet implemented in application)
// ============================================================================

// ============================================================================
// SECTION 1: NEW NODE TYPE - AmbientTranscript (Ephemeral)
// ============================================================================

// Create constraints for AmbientTranscript
CREATE CONSTRAINT ambient_transcript_id_unique IF NOT EXISTS
FOR (at:AmbientTranscript) REQUIRE at.id IS UNIQUE;

CREATE CONSTRAINT ambient_transcript_id_exists IF NOT EXISTS
FOR (at:AmbientTranscript) REQUIRE at.id IS NOT NULL;

// Create indexes for AmbientTranscript
CREATE INDEX ambient_session_id_idx IF NOT EXISTS
FOR (at:AmbientTranscript) ON (at.session_id);

CREATE INDEX ambient_timestamp_idx IF NOT EXISTS
FOR (at:AmbientTranscript) ON (at.timestamp);

CREATE INDEX ambient_expires_at_idx IF NOT EXISTS
FOR (at:AmbientTranscript) ON (at.expires_at);

/*
╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: AmbientTranscript (EPHEMERAL - 30 MIN TTL)                    ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: Store real-time transcriptions from provider-patient audio      ║
║ CRITICAL: Auto-delete after 30 minutes or on provider approval           ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   id              : STRING (UUID)             [UNIQUE, NOT NULL]          ║
║   session_id      : STRING (UUID)             [REQUIRED, INDEXED]         ║
║   timestamp       : DATETIME                  [REQUIRED, INDEXED]         ║
║   expires_at      : DATETIME                  [REQUIRED, INDEXED]         ║
║   speaker         : STRING (provider|patient) [REQUIRED]                  ║
║   text            : STRING                    [REQUIRED, PHI CONTENT]     ║
║   confidence      : FLOAT (0.0-1.0)           [REQUIRED]                  ║
║   start_time_ms   : INTEGER                   [OPTIONAL]                  ║
║   end_time_ms     : INTEGER                   [OPTIONAL]                  ║
║   extracted       : BOOLEAN                   [DEFAULT: false]            ║
║                                                                           ║
║ SECURITY NOTES:                                                           ║
║   - Contains PHI (patient speech)                                        ║
║   - Must be deleted within 30 minutes                                    ║
║   - Deleted immediately upon provider note approval                      ║
║   - Never logged or persisted outside this node                          ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     id: "trans-001",                                                     ║
║     session_id: "sess-ambient-001",                                      ║
║     timestamp: datetime("2025-11-29T14:32:15Z"),                         ║
║     expires_at: datetime("2025-11-29T15:02:15Z"),                        ║
║     speaker: "patient",                                                  ║
║     text: "I've been having trouble with urination...",                  ║
║     confidence: 0.94,                                                    ║
║     start_time_ms: 15300,                                                ║
║     end_time_ms: 18700,                                                  ║
║     extracted: false                                                     ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝
*/


// ============================================================================
// SECTION 2: ENHANCED SESSION NODE - Add Ambient Fields
// ============================================================================

// Add new properties to existing Session nodes (if any exist)
// This is safe to run even if no sessions exist

MATCH (s:Session)
WHERE NOT exists(s.ambient_enabled)
SET s.ambient_enabled = false,
    s.consent_obtained = false,
    s.consent_timestamp = null,
    s.transcription_complete = false;

/*
UPDATED Session Properties for Ambient Listening:
  ambient_enabled      : BOOLEAN (default: false)
  consent_obtained     : BOOLEAN (default: false)
  consent_timestamp    : DATETIME (when consent was recorded)
  transcription_complete: BOOLEAN (default: false)
*/


// ============================================================================
// SECTION 3: NEW NODE TYPE - ExtractedElement
// ============================================================================

CREATE CONSTRAINT extracted_element_id_unique IF NOT EXISTS
FOR (ee:ExtractedElement) REQUIRE ee.id IS UNIQUE;

CREATE INDEX extracted_element_session_idx IF NOT EXISTS
FOR (ee:ExtractedElement) ON (ee.session_id);

CREATE INDEX extracted_element_section_idx IF NOT EXISTS
FOR (ee:ExtractedElement) ON (ee.note_section);

/*
╔═══════════════════════════════════════════════════════════════════════════╗
║ NODE TYPE: ExtractedElement (EPHEMERAL - Linked to Session TTL)          ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PURPOSE: Store clinically relevant elements extracted from transcription ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   id              : STRING (UUID)             [UNIQUE]                    ║
║   session_id      : STRING (UUID)             [REQUIRED, INDEXED]         ║
║   element_type    : STRING                    [REQUIRED]                  ║
║                     (symptom|exam_finding|plan|history|discussion)        ║
║   note_section    : STRING                    [REQUIRED, INDEXED]         ║
║                     (hpi|ros|physical_exam|assessment|plan)               ║
║   content         : STRING                    [REQUIRED]                  ║
║   confidence      : FLOAT (0.0-1.0)           [REQUIRED]                  ║
║   source_transcript_ids: LIST<STRING>         [REQUIRED]                  ║
║   created_at      : DATETIME                  [DEFAULT: now()]            ║
║   approved        : BOOLEAN                   [DEFAULT: false]            ║
║                                                                           ║
║ EXAMPLE:                                                                  ║
║   {                                                                       ║
║     id: "elem-001",                                                      ║
║     session_id: "sess-ambient-001",                                      ║
║     element_type: "symptom",                                             ║
║     note_section: "hpi",                                                 ║
║     content: "Nocturia 4-5 times per night, worsening over 2 weeks",     ║
║     confidence: 0.92,                                                    ║
║     source_transcript_ids: ["trans-003", "trans-004"],                   ║
║     approved: false                                                      ║
║   }                                                                       ║
╚═══════════════════════════════════════════════════════════════════════════╝
*/


// ============================================================================
// SECTION 4: NEW RELATIONSHIPS FOR AMBIENT WORKFLOW
// ============================================================================

/*
╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:HAS_TRANSCRIPT]                                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (Session)-[:HAS_TRANSCRIPT]->(AmbientTranscript)                ║
║ PURPOSE: Link transcripts to their session                               ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   created_at      : DATETIME                                             ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:EXTRACTED_FROM]                                           ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (ExtractedElement)-[:EXTRACTED_FROM]->(AmbientTranscript)       ║
║ PURPOSE: Trace extracted elements back to source speech                  ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   extraction_confidence : FLOAT (0.0-1.0)                                ║
║   extraction_method     : STRING (llm_extraction|keyword_match)          ║
╚═══════════════════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════════════════╗
║ RELATIONSHIP: [:CONTAINS_ELEMENT]                                         ║
╠═══════════════════════════════════════════════════════════════════════════╣
║ PATTERN: (Session)-[:CONTAINS_ELEMENT]->(ExtractedElement)               ║
║ PURPOSE: Direct link from session to all extracted clinical elements     ║
║                                                                           ║
║ PROPERTIES:                                                               ║
║   created_at      : DATETIME                                             ║
╚═══════════════════════════════════════════════════════════════════════════╝
*/


// ============================================================================
// SECTION 5: TTL CLEANUP EXTENSION
// ============================================================================

// Enhanced TTL cleanup query that deletes AmbientTranscript and
// ExtractedElement nodes when their parent Session expires

// This query should be run every 1 minute via external scheduler:
/*
MATCH (s:Session)
WHERE s.expires_at < datetime()
OPTIONAL MATCH (s)-[:HAS_TRANSCRIPT]->(at:AmbientTranscript)
OPTIONAL MATCH (s)-[:CONTAINS_ELEMENT]->(ee:ExtractedElement)
WITH s, collect(DISTINCT at) AS transcripts, collect(DISTINCT ee) AS elements
DETACH DELETE s
FOREACH (t IN transcripts | DETACH DELETE t)
FOREACH (e IN elements | DETACH DELETE e)
RETURN count(s) AS deleted_sessions,
       size(transcripts) AS deleted_transcripts,
       size(elements) AS deleted_elements;
*/


// ============================================================================
// SECTION 6: ENHANCED AUDIT LOG FIELDS
// ============================================================================

// Add ambient-specific audit fields to existing AuditLog nodes
MATCH (a:AuditLog)
WHERE NOT exists(a.ambient_source)
SET a.ambient_source = false,
    a.transcription_duration_ms = null,
    a.elements_extracted = null;

/*
UPDATED AuditLog Properties for Ambient Tracking:
  ambient_source           : BOOLEAN (was this from ambient listening?)
  transcription_duration_ms: INTEGER (total audio duration)
  elements_extracted       : INTEGER (count of extracted elements)

NOTE: Still NO PHI in audit logs - only metadata
*/


// ============================================================================
// SECTION 7: NEW INDEXES FOR AMBIENT QUERIES
// ============================================================================

// Index for finding pending transcripts to process
CREATE INDEX ambient_transcript_extracted_idx IF NOT EXISTS
FOR (at:AmbientTranscript) ON (at.extracted);

// Index for filtering by confidence threshold
CREATE INDEX ambient_confidence_idx IF NOT EXISTS
FOR (at:AmbientTranscript) ON (at.confidence);

// Index for element approval status
CREATE INDEX extracted_element_approved_idx IF NOT EXISTS
FOR (ee:ExtractedElement) ON (ee.approved);


// ============================================================================
// SECTION 8: SAMPLE AMBIENT QUERIES (For Testing)
// ============================================================================

// Query 8.1: Get all transcripts for active session
/*
MATCH (s:Session {session_id: $session_id})-[:HAS_TRANSCRIPT]->(at:AmbientTranscript)
WHERE s.expires_at > datetime()
RETURN at.timestamp AS timestamp,
       at.speaker AS speaker,
       at.text AS text,
       at.confidence AS confidence
ORDER BY at.timestamp;
*/

// Query 8.2: Get extracted elements by note section
/*
MATCH (s:Session {session_id: $session_id})-[:CONTAINS_ELEMENT]->(ee:ExtractedElement)
WHERE ee.note_section = $section
  AND s.expires_at > datetime()
RETURN ee.content AS content,
       ee.element_type AS type,
       ee.confidence AS confidence,
       ee.approved AS approved
ORDER BY ee.created_at;
*/

// Query 8.3: Create ambient transcript
/*
MATCH (s:Session {session_id: $session_id})
CREATE (at:AmbientTranscript {
    id: randomUUID(),
    session_id: $session_id,
    timestamp: datetime(),
    expires_at: s.expires_at,
    speaker: $speaker,
    text: $text,
    confidence: $confidence,
    start_time_ms: $start_time_ms,
    end_time_ms: $end_time_ms,
    extracted: false
})
CREATE (s)-[:HAS_TRANSCRIPT {created_at: datetime()}]->(at)
RETURN at.id AS transcript_id;
*/

// Query 8.4: Create extracted element
/*
MATCH (s:Session {session_id: $session_id})
CREATE (ee:ExtractedElement {
    id: randomUUID(),
    session_id: $session_id,
    element_type: $element_type,
    note_section: $note_section,
    content: $content,
    confidence: $confidence,
    source_transcript_ids: $source_transcript_ids,
    created_at: datetime(),
    approved: false
})
CREATE (s)-[:CONTAINS_ELEMENT {created_at: datetime()}]->(ee)
WITH ee, $source_transcript_ids AS transcript_ids
UNWIND transcript_ids AS tid
MATCH (at:AmbientTranscript {id: tid})
CREATE (ee)-[:EXTRACTED_FROM {
    extraction_confidence: $confidence,
    extraction_method: 'llm_extraction'
}]->(at)
RETURN ee.id AS element_id;
*/

// Query 8.5: Approve and finalize session (delete all ambient data)
/*
MATCH (s:Session {session_id: $session_id})
OPTIONAL MATCH (s)-[:HAS_TRANSCRIPT]->(at:AmbientTranscript)
OPTIONAL MATCH (s)-[:CONTAINS_ELEMENT]->(ee:ExtractedElement)
WITH s, collect(DISTINCT at) AS transcripts, collect(DISTINCT ee) AS elements
// Delete all ambient data
FOREACH (t IN transcripts | DETACH DELETE t)
FOREACH (e IN elements | DETACH DELETE e)
// Keep session for remaining TTL but mark transcription complete
SET s.transcription_complete = true
RETURN true AS ambient_data_deleted;
*/


// ============================================================================
// SECTION 9: VERIFICATION
// ============================================================================

// Verify new constraints were created
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes
WHERE name CONTAINS 'ambient' OR name CONTAINS 'extracted'
RETURN name, type, entityType, labelsOrTypes;

// Verify new indexes were created
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes
WHERE name CONTAINS 'ambient' OR name CONTAINS 'extracted'
RETURN name, type, entityType, labelsOrTypes;


// ============================================================================
// MIGRATION COMPLETE
// ============================================================================
// This migration adds support for:
//   - AmbientTranscript nodes (ephemeral, 30-min TTL)
//   - ExtractedElement nodes (ephemeral, tied to session)
//   - Enhanced Session properties for ambient workflow
//   - Enhanced AuditLog properties for ambient metadata
//   - New relationships for ambient data flow
//   - Extended TTL cleanup for ambient nodes
//
// Next Steps:
//   1. Implement ambient listening service in application
//   2. Integrate speech-to-text (Whisper/Azure Speech)
//   3. Implement clinical extraction pipeline
//   4. Build provider review interface
// ============================================================================
