export const meta = {
  name: 'assess-tumor-notes',
  description: 'Accuracy-assess each generated Tumor-clinic note vs its source input; return per-section findings + root-cause hypotheses',
  phases: [{ title: 'Assess' }],
}

// args = { inputDir, outputDir, patients:[...] }  OR
//        { groups: [{inputDir, outputDir, patients:[...]}, ...] }
const A = typeof args === 'string' ? JSON.parse(args) : args
// Normalize to a flat list of {inputDir, outputDir, patient} work items.
const groups = Array.isArray(A.groups)
  ? A.groups
  : [{ inputDir: A.inputDir, outputDir: A.outputDir, patients: A.patients }]
const work = []
for (const g of groups) {
  if (!Array.isArray(g.patients)) {
    throw new Error('each group needs a patients array; got ' + JSON.stringify(g).slice(0, 160))
  }
  for (const p of g.patients) work.push({ inputDir: g.inputDir, outputDir: g.outputDir, patient: p })
}

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['patient', 'overall_quality', 'findings'],
  properties: {
    patient: { type: 'string' },
    overall_quality: {
      type: 'string',
      enum: ['acceptable', 'minor_issues', 'major_issues', 'unusable'],
      description: 'Holistic clinical-accuracy grade of the generated note',
    },
    one_line_summary: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['section', 'category', 'severity', 'description', 'root_cause_hypothesis'],
        properties: {
          section: {
            type: 'string',
            enum: ['CC', 'HPI', 'IPSS', 'PMH', 'PSH', 'SOCIAL', 'FAMILY', 'SEXUAL',
                   'ALLERGIES', 'MEDICATIONS', 'PSA', 'PATHOLOGY', 'IMAGING', 'LABS',
                   'ROS', 'PE', 'ASSESSMENT', 'PLAN', 'PROBLEM_LIST', 'OTHER'],
          },
          category: {
            type: 'string',
            enum: ['omission', 'hallucination', 'wrong_entry', 'internal_contradiction',
                   'context_blind_recommendation', 'stale_data', 'formatting', 'other'],
            description: 'omission=important source fact missing; hallucination=claim not in source; '
              + 'wrong_entry=value present but incorrect; context_blind_recommendation=plan contradicts '
              + 'the patient history; stale_data=old value presented as current',
          },
          severity: { type: 'string', enum: ['critical', 'major', 'minor'] },
          description: { type: 'string', description: 'What is wrong, specifically' },
          evidence_source: { type: 'string', description: 'Quote/locator from the INPUT supporting this' },
          evidence_note: { type: 'string', description: 'Quote from the generated NOTE showing the error' },
          root_cause_hypothesis: {
            type: 'string',
            description: 'Which pipeline component likely caused this (e.g. "HPI v2 GroundTruth blind to narrative treatment history", "CC keyword filter false positive", "extractor failed on VistA format", "A&P prompt ignores treatment status"). Be specific.',
          },
        },
      },
    },
  },
}

const PROMPT = (w) => `You are a board-certified urologist auditing an AI-generated urology clinic note for CLINICAL ACCURACY against its source record. Today's date is 2026-06-24.

Source input file (the ground truth — a VistA clinic-prep extract, may be large): ${w.inputDir}/${w.patient}
Generated note file (the AI output to audit): ${w.outputDir}/${w.patient}

Steps:
1. Read the GENERATED NOTE fully (it is short).
2. Read the SOURCE INPUT. It is large and contains years of records; use it to verify the note's claims and to find IMPORTANT clinical facts the note OMITTED.
3. Audit every section. Focus on these high-value error classes the user reported:
   - HPI that TRUNCATES or OMITS important facts (treatment history, metastases, current regimen, PSA trajectory, key diagnoses).
   - CC with WRONG entries (a complaint/diagnosis the patient does not have, e.g. "nephrolithiasis" for a patient with no stone history).
   - HALLUCINATIONS in HPI / Assessment / Plan (values, treatments, findings not in the source).
   - Recommendations that CONTRADICT the patient's history (e.g. recommending PSA screening for a man s/p prostatectomy on palliative care; biopsy for already-diagnosed metastatic disease; active surveillance for someone already treated).
   - Internal contradictions (HPI says X, Assessment says not-X), stale data presented as current.

Rules for findings:
- Only report REAL errors you can substantiate from the source. Do not invent issues. Quote source evidence.
- For each finding, give a specific root_cause_hypothesis pointing at a likely pipeline component.
- If the note is accurate, return an empty findings array with overall_quality="acceptable".
- Be thorough but precise. Prefer fewer, well-substantiated findings over speculation.

Return ONLY the structured object.`

const results = await pipeline(
  work,
  (w) => agent(PROMPT(w), { label: `assess:${w.patient}`, phase: 'Assess', schema: FINDINGS_SCHEMA })
)

const ok = results.filter(Boolean)
// Aggregate
const byCategory = {}, bySection = {}, byRootCause = {}, byQuality = {}
let totalFindings = 0, criticalCount = 0
for (const r of ok) {
  byQuality[r.overall_quality] = (byQuality[r.overall_quality] || 0) + 1
  for (const f of (r.findings || [])) {
    totalFindings++
    if (f.severity === 'critical') criticalCount++
    byCategory[f.category] = (byCategory[f.category] || 0) + 1
    bySection[f.section] = (bySection[f.section] || 0) + 1
    const rc = (f.root_cause_hypothesis || 'unknown').slice(0, 120)
    byRootCause[rc] = (byRootCause[rc] || 0) + 1
  }
}

return {
  patients_assessed: ok.length,
  total_findings: totalFindings,
  critical_findings: criticalCount,
  quality_distribution: byQuality,
  by_category: byCategory,
  by_section: bySection,
  by_root_cause: Object.fromEntries(Object.entries(byRootCause).sort((a, b) => b[1] - a[1])),
  per_patient: ok.map((r) => ({
    patient: r.patient,
    quality: r.overall_quality,
    summary: r.one_line_summary,
    findings: r.findings,
  })),
}
