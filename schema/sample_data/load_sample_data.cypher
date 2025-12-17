// ============================================================================
// VAUCDA Sample Data Insertion
// ============================================================================
// Purpose: Populate database with sample medical knowledge for testing
// Note: Embeddings in this file are placeholder vectors - replace with
//       actual embeddings from sentence-transformers/all-MiniLM-L6-v2
// ============================================================================

// ============================================================================
// SECTION 1: CLINICAL CONCEPTS
// ============================================================================

CREATE (pc:ClinicalConcept {
    id: 'cc-001-prostate-cancer',
    name: 'Prostate Adenocarcinoma',
    icd10_code: 'C61',
    snomed_code: '399068003',
    description: 'Malignant neoplasm of the prostate gland',
    category: 'prostate',
    synonyms: ['Prostate Cancer', 'Prostatic Carcinoma', 'PCa'],
    embedding: [0.023, -0.145, 0.089] + [0.0] * 765,  // Placeholder 768-dim
    created_at: datetime()
});

CREATE (bph:ClinicalConcept {
    id: 'cc-002-bph',
    name: 'Benign Prostatic Hyperplasia',
    icd10_code: 'N40.0',
    snomed_code: '266569009',
    description: 'Non-malignant enlargement of the prostate gland',
    category: 'voiding',
    synonyms: ['BPH', 'Prostate Enlargement', 'Benign Prostatic Hypertrophy'],
    embedding: [0.012, -0.098, 0.134] + [0.0] * 765,
    created_at: datetime()
});

CREATE (rcc:ClinicalConcept {
    id: 'cc-003-rcc',
    name: 'Renal Cell Carcinoma',
    icd10_code: 'C64',
    snomed_code: '41607009',
    description: 'Malignant neoplasm arising from renal tubular epithelium',
    category: 'kidney',
    synonyms: ['RCC', 'Kidney Cancer', 'Renal Cancer'],
    embedding: [0.045, -0.167, 0.078] + [0.0] * 765,
    created_at: datetime()
});

CREATE (stones:ClinicalConcept {
    id: 'cc-004-nephrolithiasis',
    name: 'Nephrolithiasis',
    icd10_code: 'N20.0',
    snomed_code: '95570007',
    description: 'Kidney stones; urolithiasis',
    category: 'stones',
    synonyms: ['Kidney Stones', 'Renal Calculi', 'Urolithiasis'],
    embedding: [0.067, -0.123, 0.145] + [0.0] * 765,
    created_at: datetime()
});

// Create relationships between concepts
MATCH (bph:ClinicalConcept {id: 'cc-002-bph'})
MATCH (pc:ClinicalConcept {id: 'cc-001-prostate-cancer'})
CREATE (bph)-[:RELATED_TO {
    relationship: 'differential_diagnosis',
    strength: 0.75
}]->(pc);


// ============================================================================
// SECTION 2: CALCULATORS
// ============================================================================

CREATE (capra:Calculator {
    name: 'CAPRA Score',
    category: 'prostate_cancer',
    description: 'Cancer of the Prostate Risk Assessment score for predicting recurrence after radical prostatectomy',
    algorithm: '{
        "inputs": ["psa", "gleason_primary", "gleason_secondary", "clinical_stage", "percent_positive_cores", "age"],
        "scoring": {
            "psa": {"<=6": 0, "6-10": 1, "10-20": 2, "20-30": 3, ">30": 4},
            "gleason": {"primary>=4 OR secondary>=4": 3, "secondary 4/5": 1, "else": 0},
            "stage": {"T1c/T2a": 0, "T2b/T2c": 1, "T3a": 2},
            "cores": {">=34%": 1, "else": 0}
        },
        "max_score": 10
    }',
    validation_refs: ['Cooperberg MR, et al. Cancer 2006;107:2276-2283'],
    input_schema: '{
        "type": "object",
        "properties": {
            "psa": {"type": "number", "minimum": 0, "maximum": 1000},
            "gleason_primary": {"type": "integer", "minimum": 1, "maximum": 5},
            "gleason_secondary": {"type": "integer", "minimum": 1, "maximum": 5},
            "clinical_stage": {"type": "string", "enum": ["T1c", "T2a", "T2b", "T2c", "T3a"]},
            "percent_positive_cores": {"type": "number", "minimum": 0, "maximum": 100},
            "age": {"type": "integer", "minimum": 18, "maximum": 120}
        },
        "required": ["psa", "gleason_primary", "gleason_secondary", "clinical_stage", "percent_positive_cores"]
    }',
    output_schema: '{
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
            "risk_category": {"type": "string", "enum": ["Low", "Intermediate", "High"]},
            "five_year_rfs": {"type": "number"},
            "interpretation": {"type": "string"}
        }
    }',
    version: '1.0',
    created_at: datetime(),
    updated_at: datetime()
});

CREATE (ipss:Calculator {
    name: 'IPSS Calculator',
    category: 'male_voiding',
    description: 'International Prostate Symptom Score for assessing lower urinary tract symptoms',
    algorithm: '{
        "inputs": ["incomplete_emptying", "frequency", "intermittency", "urgency", "weak_stream", "straining", "nocturia"],
        "scoring": {"range": [0, 5], "total": "sum of all inputs"},
        "max_score": 35
    }',
    validation_refs: ['Barry MJ, et al. J Urol 1992;148:1549-1557'],
    input_schema: '{
        "type": "object",
        "properties": {
            "incomplete_emptying": {"type": "integer", "minimum": 0, "maximum": 5},
            "frequency": {"type": "integer", "minimum": 0, "maximum": 5},
            "intermittency": {"type": "integer", "minimum": 0, "maximum": 5},
            "urgency": {"type": "integer", "minimum": 0, "maximum": 5},
            "weak_stream": {"type": "integer", "minimum": 0, "maximum": 5},
            "straining": {"type": "integer", "minimum": 0, "maximum": 5},
            "nocturia": {"type": "integer", "minimum": 0, "maximum": 5}
        },
        "required": ["incomplete_emptying", "frequency", "intermittency", "urgency", "weak_stream", "straining", "nocturia"]
    }',
    output_schema: '{
        "type": "object",
        "properties": {
            "total_score": {"type": "integer", "minimum": 0, "maximum": 35},
            "symptom_severity": {"type": "string", "enum": ["Mild", "Moderate", "Severe"]},
            "interpretation": {"type": "string"}
        }
    }',
    version: '1.0',
    created_at: datetime(),
    updated_at: datetime()
});

CREATE (renal:Calculator {
    name: 'RENAL Nephrometry Score',
    category: 'kidney_cancer',
    description: 'Standardized classification system for renal masses to assess surgical complexity',
    algorithm: '{
        "components": {
            "R": "Radius (maximal diameter in cm)",
            "E": "Exophytic/Endophytic properties",
            "N": "Nearness to collecting system or sinus (mm)",
            "A": "Anterior/Posterior location",
            "L": "Location relative to polar lines"
        },
        "scoring": "Sum of R, E, N components (4-12 points) + descriptor (A/P, x/h)"
    }',
    validation_refs: ['Kutikov A, Urology 2009;74:1260-1265'],
    input_schema: '{
        "type": "object",
        "properties": {
            "radius_cm": {"type": "number", "minimum": 0},
            "exophytic": {"type": "string", "enum": [">=50%", "<50%", "Endophytic"]},
            "nearness_mm": {"type": "number", "minimum": 0},
            "location_ap": {"type": "string", "enum": ["Anterior", "Posterior"]},
            "location_polar": {"type": "string", "enum": ["Upper", "Interpolar", "Lower"]}
        }
    }',
    output_schema: '{
        "type": "object",
        "properties": {
            "total_score": {"type": "integer", "minimum": 4, "maximum": 12},
            "complexity": {"type": "string", "enum": ["Low", "Moderate", "High"]},
            "descriptor": {"type": "string"}
        }
    }',
    version: '1.0',
    created_at: datetime(),
    updated_at: datetime()
});

// Link calculators to clinical concepts
MATCH (capra:Calculator {name: 'CAPRA Score'})
MATCH (pc:ClinicalConcept {id: 'cc-001-prostate-cancer'})
CREATE (capra)-[:APPLIES_TO {applicability: 'primary'}]->(pc);

MATCH (ipss:Calculator {name: 'IPSS Calculator'})
MATCH (bph:ClinicalConcept {id: 'cc-002-bph'})
CREATE (ipss)-[:APPLIES_TO {applicability: 'primary'}]->(bph);

MATCH (renal:Calculator {name: 'RENAL Nephrometry Score'})
MATCH (rcc:ClinicalConcept {id: 'cc-003-rcc'})
CREATE (renal)-[:APPLIES_TO {applicability: 'primary'}]->(rcc);


// ============================================================================
// SECTION 3: GUIDELINES
// ============================================================================

CREATE (nccn_prostate:Guideline {
    id: '550e8400-e29b-41d4-a716-446655440001',
    title: 'NCCN Clinical Practice Guidelines in Oncology: Prostate Cancer',
    organization: 'NCCN',
    publication_date: date('2024-01-15'),
    category: 'prostate',
    version: 'Version 1.2024',
    content: 'The NCCN Prostate Cancer Panel updates these guidelines on an annual basis. This version includes updated recommendations for risk stratification using PSA, Gleason score, and clinical stage. Very low-risk disease is defined as clinical stage T1c AND Gleason score ≤6 AND PSA <10 ng/mL AND fewer than 3 positive biopsy cores AND ≤50% cancer in each core AND PSA density <0.15 ng/mL/g. Low-risk disease includes clinical stage T1-T2a AND Gleason score ≤6 AND PSA <10 ng/mL. Intermediate-risk encompasses clinical stage T2b-T2c OR Gleason score 7 OR PSA 10-20 ng/mL. High-risk disease is defined as clinical stage T3a OR Gleason score 8-10 OR PSA >20 ng/mL...',
    embedding: [0.034, -0.178, 0.092] + [0.0] * 765,  // Placeholder
    url: 'https://www.nccn.org/professionals/physician_gls/pdf/prostate.pdf',
    created_at: datetime(),
    updated_at: datetime()
});

CREATE (aua_bph:Guideline {
    id: '550e8400-e29b-41d4-a716-446655440002',
    title: 'AUA Guideline: Management of Benign Prostatic Hyperplasia',
    organization: 'AUA',
    publication_date: date('2021-09-01'),
    category: 'voiding',
    version: '2021',
    content: 'The American Urological Association guideline provides evidence-based recommendations for the diagnosis and treatment of benign prostatic hyperplasia (BPH) and lower urinary tract symptoms (LUTS). Initial evaluation should include medical history, physical examination including digital rectal examination (DRE), and urinalysis. The International Prostate Symptom Score (IPSS) questionnaire should be administered to assess symptom severity and impact on quality of life. Mild symptoms (IPSS 0-7) may be managed with watchful waiting. Moderate to severe symptoms (IPSS ≥8) warrant consideration of medical therapy including alpha-blockers, 5-alpha reductase inhibitors, or combination therapy...',
    embedding: [0.056, -0.134, 0.167] + [0.0] * 765,
    url: 'https://www.auanet.org/guidelines/bph',
    created_at: datetime(),
    updated_at: datetime()
});

// Link guidelines to concepts
MATCH (nccn:Guideline {id: '550e8400-e29b-41d4-a716-446655440001'})
MATCH (pc:ClinicalConcept {id: 'cc-001-prostate-cancer'})
CREATE (nccn)-[:COVERS {
    detail_level: 'comprehensive',
    section: 'Risk Stratification'
}]->(pc);

MATCH (aua:Guideline {id: '550e8400-e29b-41d4-a716-446655440002'})
MATCH (bph:ClinicalConcept {id: 'cc-002-bph'})
CREATE (aua)-[:COVERS {
    detail_level: 'comprehensive',
    section: 'Diagnosis and Treatment'
}]->(bph);

// Link calculator to guideline
MATCH (capra:Calculator {name: 'CAPRA Score'})
MATCH (nccn:Guideline {id: '550e8400-e29b-41d4-a716-446655440001'})
CREATE (capra)-[:IMPLEMENTS {
    version: 'Version 1.2024',
    validated: true
}]->(nccn);


// ============================================================================
// SECTION 4: LITERATURE
// ============================================================================

CREATE (damico_psa:Literature {
    title: 'Prostate-specific antigen velocity and the risk of death from prostate cancer after radical prostatectomy',
    authors: ["D'Amico AV", "Chen MH", "Roehl KA", "Catalona WJ"],
    journal: 'JAMA',
    pubmed_id: '15546998',
    doi: '10.1001/jama.292.18.2237',
    abstract: 'CONTEXT: Prostate-specific antigen (PSA) velocity, the rate of change in PSA over time, may improve detection of clinically significant prostate cancer. OBJECTIVE: To determine if PSA velocity measured during the year before prostate cancer diagnosis predicts death from prostate cancer after radical prostatectomy. DESIGN, SETTING, AND PARTICIPANTS: Retrospective cohort study of 1095 men with clinically localized prostate cancer treated with radical prostatectomy between 1988 and 2002. PSA velocity was calculated using at least 3 PSA measurements obtained during the year prior to diagnosis. RESULTS: PSA velocity >2.0 ng/mL per year in the year before diagnosis was significantly associated with prostate cancer-specific death...',
    full_text: null,
    embedding: [0.067, -0.145, 0.123] + [0.0] * 765,
    publication_year: 2004,
    keywords: ['PSA velocity', 'prostate cancer', 'radical prostatectomy', 'prognosis'],
    created_at: datetime()
});

CREATE (barry_ipss:Literature {
    title: 'The American Urological Association symptom index for benign prostatic hyperplasia',
    authors: ['Barry MJ', 'Fowler FJ Jr', 'O\'Leary MP', 'Bruskewitz RC', 'Holtgrewe HL', 'Mebust WK', 'Cockett AT'],
    journal: 'Journal of Urology',
    pubmed_id: '1279218',
    doi: '10.1016/S0022-5347(17)36966-5',
    abstract: 'PURPOSE: We developed and validated a symptom index to assess the severity of obstructive and irritative voiding symptoms in men with benign prostatic hyperplasia (BPH). MATERIALS AND METHODS: A 7-item questionnaire (AUA Symptom Index) was developed based on input from urologists and validated in 108 men with BPH and 35 age-matched controls. Questions assess incomplete emptying, frequency, intermittency, urgency, weak stream, straining, and nocturia. Each item is scored 0-5 for a total score range of 0-35. RESULTS: The index demonstrated excellent test-retest reliability and internal consistency. Scores correlated significantly with physician assessments of symptom severity...',
    full_text: null,
    embedding: [0.089, -0.156, 0.134] + [0.0] * 765,
    publication_year: 1992,
    keywords: ['IPSS', 'AUA symptom index', 'BPH', 'lower urinary tract symptoms', 'questionnaire'],
    created_at: datetime()
});

// Link literature to guidelines
MATCH (lit:Literature {doi: '10.1001/jama.292.18.2237'})
MATCH (g:Guideline {id: '550e8400-e29b-41d4-a716-446655440001'})
CREATE (g)-[:REFERENCES {
    citation_type: 'evidence',
    strength: 'high'
}]->(lit);

MATCH (lit:Literature {doi: '10.1016/S0022-5347(17)36966-5'})
MATCH (g:Guideline {id: '550e8400-e29b-41d4-a716-446655440002'})
CREATE (g)-[:REFERENCES {
    citation_type: 'primary',
    strength: 'high'
}]->(lit);


// ============================================================================
// SECTION 5: DOCUMENT CHUNKS (RAG Content)
// ============================================================================

// Chunks from NCCN Prostate Cancer guideline
CREATE (chunk1:DocumentChunk {
    id: 'chunk-nccn-prostate-001',
    source_id: '550e8400-e29b-41d4-a716-446655440001',
    source_type: 'Guideline',
    chunk_index: 1,
    content: 'Risk stratification for localized prostate cancer uses three key parameters: PSA level, Gleason score, and clinical stage. Very low-risk disease is defined as clinical stage T1c AND Gleason score ≤6 AND PSA <10 ng/mL AND fewer than 3 positive biopsy cores AND ≤50% cancer in each core AND PSA density <0.15 ng/mL/g.',
    embedding: [0.045, -0.167, 0.098] + [0.0] * 765,
    metadata: {section: 'Risk Stratification', category: 'prostate', page: 5},
    token_count: 78,
    created_at: datetime()
});

CREATE (chunk2:DocumentChunk {
    id: 'chunk-nccn-prostate-002',
    source_id: '550e8400-e29b-41d4-a716-446655440001',
    source_type: 'Guideline',
    chunk_index: 2,
    content: 'Low-risk prostate cancer includes clinical stage T1-T2a AND Gleason score ≤6 AND PSA <10 ng/mL. Patients with low-risk disease are candidates for active surveillance, radical prostatectomy, or radiation therapy. The choice should be based on patient preference, life expectancy, and comorbidities.',
    embedding: [0.052, -0.178, 0.102] + [0.0] * 765,
    metadata: {section: 'Low-Risk Disease', category: 'prostate', page: 6},
    token_count: 65,
    created_at: datetime()
});

CREATE (chunk3:DocumentChunk {
    id: 'chunk-nccn-prostate-003',
    source_id: '550e8400-e29b-41d4-a716-446655440001',
    source_type: 'Guideline',
    chunk_index: 3,
    content: 'Intermediate-risk prostate cancer encompasses clinical stage T2b-T2c OR Gleason score 7 OR PSA 10-20 ng/mL. This risk category can be further subdivided into favorable and unfavorable intermediate-risk based on the presence of additional risk factors. Favorable intermediate-risk has only one intermediate-risk factor and Gleason pattern group 1 or 2.',
    embedding: [0.061, -0.184, 0.115] + [0.0] * 765,
    metadata: {section: 'Intermediate-Risk Disease', category: 'prostate', page: 7},
    token_count: 72,
    created_at: datetime()
});

// Chunks from AUA BPH guideline
CREATE (chunk4:DocumentChunk {
    id: 'chunk-aua-bph-001',
    source_id: '550e8400-e29b-41d4-a716-446655440002',
    source_type: 'Guideline',
    chunk_index: 1,
    content: 'The International Prostate Symptom Score (IPSS) is a validated questionnaire used to assess the severity of lower urinary tract symptoms in men with BPH. The IPSS consists of 7 questions covering incomplete emptying, frequency, intermittency, urgency, weak stream, straining, and nocturia. Each question is scored from 0 (not at all) to 5 (almost always), yielding a total score range of 0-35.',
    embedding: [0.073, -0.145, 0.128] + [0.0] * 765,
    metadata: {section: 'Symptom Assessment', category: 'voiding', page: 8},
    token_count: 85,
    created_at: datetime()
});

CREATE (chunk5:DocumentChunk {
    id: 'chunk-aua-bph-002',
    source_id: '550e8400-e29b-41d4-a716-446655440002',
    source_type: 'Guideline',
    chunk_index: 2,
    content: 'IPSS scores are categorized as mild (0-7), moderate (8-19), or severe (20-35). Patients with mild symptoms may be managed with watchful waiting and lifestyle modifications. Moderate to severe symptoms warrant consideration of medical therapy. First-line pharmacologic options include alpha-adrenergic antagonists (alpha-blockers) and 5-alpha reductase inhibitors (5-ARIs).',
    embedding: [0.081, -0.152, 0.135] + [0.0] * 765,
    metadata: {section: 'Treatment Recommendations', category: 'voiding', page: 12},
    token_count: 79,
    created_at: datetime()
});

// Link chunks to source documents
MATCH (chunk:DocumentChunk {source_id: '550e8400-e29b-41d4-a716-446655440001'})
MATCH (g:Guideline {id: '550e8400-e29b-41d4-a716-446655440001'})
CREATE (chunk)-[:BELONGS_TO {
    chunk_index: chunk.chunk_index,
    section: chunk.metadata.section
}]->(g);

MATCH (chunk:DocumentChunk {source_id: '550e8400-e29b-41d4-a716-446655440002'})
MATCH (g:Guideline {id: '550e8400-e29b-41d4-a716-446655440002'})
CREATE (chunk)-[:BELONGS_TO {
    chunk_index: chunk.chunk_index,
    section: chunk.metadata.section
}]->(g);

// Create sequential chunk relationships
MATCH (c1:DocumentChunk {id: 'chunk-nccn-prostate-001'})
MATCH (c2:DocumentChunk {id: 'chunk-nccn-prostate-002'})
CREATE (c1)-[:NEXT_CHUNK {overlap_tokens: 128}]->(c2);

MATCH (c2:DocumentChunk {id: 'chunk-nccn-prostate-002'})
MATCH (c3:DocumentChunk {id: 'chunk-nccn-prostate-003'})
CREATE (c2)-[:NEXT_CHUNK {overlap_tokens: 128}]->(c3);

MATCH (c4:DocumentChunk {id: 'chunk-aua-bph-001'})
MATCH (c5:DocumentChunk {id: 'chunk-aua-bph-002'})
CREATE (c4)-[:NEXT_CHUNK {overlap_tokens: 128}]->(c5);


// ============================================================================
// SECTION 6: SAMPLE SESSION (Ephemeral - for demonstration only)
// ============================================================================
// NOTE: In production, sessions are created by application and auto-deleted
// after 30 minutes. This is just for testing.

CREATE (sess:Session {
    session_id: 'demo-session-001',
    user_id: 'test-user-001',
    created_at: datetime(),
    expires_at: datetime() + duration({minutes: 30}),
    note_context: 'Sample clinical context for demonstration',
    active: true
});

// Link session to calculator usage
MATCH (sess:Session {session_id: 'demo-session-001'})
MATCH (calc:Calculator {name: 'CAPRA Score'})
CREATE (sess)-[:USED_CALCULATOR {
    timestamp: datetime(),
    result_category: 'intermediate_risk'
}]->(calc);


// ============================================================================
// SECTION 7: SAMPLE AUDIT LOGS
// ============================================================================

CREATE (audit1:AuditLog {
    id: randomUUID(),
    session_hash: 'a3f5d1c2b4e7f8a9d0c1b2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2',
    timestamp: datetime(),
    action_type: 'note_generation',
    user_id: 'test-user-001',
    model_used: 'llama3.1:8b',
    tokens_used: 2048,
    duration_ms: 2340,
    success: true,
    error_code: null
});

CREATE (audit2:AuditLog {
    id: randomUUID(),
    session_hash: 'b4e7f8a9d0c1b2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5',
    timestamp: datetime(),
    action_type: 'calculator_use',
    user_id: 'test-user-001',
    model_used: null,
    tokens_used: null,
    duration_ms: 45,
    success: true,
    error_code: null
});


// ============================================================================
// VERIFICATION QUERIES
// ============================================================================
// Run these after loading to verify data was inserted correctly

// Count all nodes by type
MATCH (n)
RETURN labels(n)[0] AS node_type, count(n) AS count
ORDER BY count DESC;

// Count all relationships by type
MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(r) AS count
ORDER BY count DESC;

// Verify embeddings are populated
MATCH (dc:DocumentChunk)
WHERE dc.embedding IS NOT NULL
RETURN count(dc) AS chunks_with_embeddings;

// Test vector search (placeholder query - requires actual embeddings)
// CALL db.index.vector.queryNodes(
//     'document_chunk_embeddings',
//     5,
//     [0.05, -0.15, 0.10] + [0.0] * 765
// )
// YIELD node, score
// RETURN node.content, score;


// ============================================================================
// END OF SAMPLE DATA LOADING
// ============================================================================
