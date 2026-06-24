"""
History Section Cleaners

Utilities to clean LLM meta-commentary from synthesized text.

The LLM (especially on smaller local Ollama models) regularly leaks:
  - Markdown headers ("**Patient Name:** [Not Provided]")
  - Meta-preamble ("Based on the provided clinical data context, I will...")
  - Closing notes ("Note:** This rewritten HPI narrative...")
  - Bracketed template placeholders ("[List of current medications including ...]")
  - Word-doubling ("previously previously elevated PSA, now declining, now declining")

Real clinical prose contains none of these patterns. Strip them
deterministically AFTER the LLM call.
"""

import re


# Lines to drop entirely (LLM scaffolding / Markdown leakage). Each
# entry is a (regex, description) pair.
_LINE_DROP_PATTERNS = (
    # Markdown emphasis or "**Label:** value" formatting — real notes
    # never contain ** in section bodies.
    re.compile(r'^\s*\*\*[^\n]*\*\*\s*$'),
    re.compile(r'^\s*\*\*[^*]+\*\*\s*[:=].*$'),
    re.compile(r'^[A-Za-z][A-Za-z\s]+:\*\*.*$'),  # "Patient Name:** ..."
    # Family-history "no info" boilerplate
    re.compile(r'^\s*[-*]?\s*(?:Unknown\s+medical\s+history|'
               r'No\s+information\s+provided[^\n]*|'
               r'Medical\s+history\s+(?:unknown|not\s+(?:provided|available|known))|'
               r'Health\s+status\s+(?:unknown|not\s+(?:provided|available|known)))\s*\.?\s*$',
               re.IGNORECASE),
    # Family-history orphan parent labels with no real content
    re.compile(r'^\s*(?:Father|Mother|Brother|Sister|Sibling|'
               r'Maternal|Paternal)\s*:\s*$', re.IGNORECASE),
    # Redundant section header echoed inside section body
    re.compile(r'^\s*(?:Family\s+History|Social\s+History|Past\s+Medical\s+History|'
               r'Past\s+Surgical\s+History|Sexual\s+History|Dietary\s+History|'
               r'Allergies|Medications)\s*:\s*$', re.IGNORECASE),
    # Numbered/labeled scaffolding lines — drop ANY "Label: ..." line
    # whose label is demographic metadata already in the banner. The
    # LLM occasionally echoes these as the first line(s) of an HPI:
    # "Patient Name: Manuel Ytuarte", "Age: 79 years old", "DOB: ...",
    # "Patient: Mr. Holder".
    re.compile(r'^\s*\*?\*?\s*(?:Patient(?:\s+Name|\s+ID)?|MRN|Name|'
               r'Age|Sex|Gender|DOB|Date\s+of\s+(?:Birth|Note|Service)|'
               r'Visit\s+Date|Encounter\s+Date|Provider|Note\s+Title|'
               r'Local\s+Title|Standard\s+Title|Author|Encounter|'
               r'Race|Ethnicity|Address|Phone|Insurance)\s*:\*?\*?'
               r'.*$', re.IGNORECASE),
    # Trailing LLM "Note:" disclaimer — broader catch. Any line that
    # starts with "Note:" / "Note " / "**Note:**" and contains
    # rewritten/synthesized/followed-the-rules language is LLM
    # scaffolding, not clinical content.
    re.compile(r'^\s*\*?\*?Note\s*[:]\s*\*?\*?\s*(?:'
               r'(?:The|This)\s+(?:rewritten|synthesized|combined|generated|'
               r'narrative|entry|HPI)|'
               r'I\s+(?:have|\'ve)\s+(?:followed|adhered|complied|maintained)|'
               r'(?:All|Every)\s+(?:rules|guidelines|requirements)).*$',
               re.IGNORECASE),
    # Meta-preamble lines — drop only lines that end with a colon
    # (the genuine preamble shape "Here is the rewritten HPI:" /
    # "Based on the provided data, here is:") so we don't accidentally
    # drop a sentence that begins with one of these words but contains
    # real content. Inline scaffolding mid-paragraph is handled by the
    # fragment-cleanup pass below.
    re.compile(r"^\s*(?:Here\s+(?:is|are)|Here's|"
               r"Based\s+on|"
               r"I\s+(?:will|'ll|have|'ve|am\s+going\s+to|can|need\s+to)|"
               r"Let\s+me|"
               r"After\s+(?:reviewing|analyzing|considering)|"
               r"The\s+following\s+(?:is|are)|"
               r"Below\s+(?:is|are))\b[^\n]*:\s*\*?\*?\s*$",
               re.IGNORECASE),
    # Bracketed template-placeholder leftovers — the LLM occasionally
    # echoes the prompt instructions inside brackets.
    re.compile(r'^\s*\[(?:List|Insert|Describe|Provide|TBD|Placeholder|'
               r'Add|Enter|To\s+be\s+(?:documented|completed|determined|'
               r'filled)|If\s+applicable|Optional|N/A|Not\s+available|'
               r'Not\s+provided|Not\s+documented|Specify|See\s+(?:above|'
               r'below|HPI)|Note\s*:|Patient[\'s]?\s+[A-Za-z\s]+|'
               r'Current\s+medication|If\s+the\s+patient)[^\]]*\]\s*$',
               re.IGNORECASE),
    # Divider lines
    re.compile(r'^\s*(?:---+|===+|\*\*\*+|___+)\s*$'),
)


# Sentence-level patterns to drop (LLM scaffolding mid-paragraph).
_SENTENCE_DROP_PATTERNS = (
    re.compile(r'\bBased\s+on\s+the\s+(?:provided|above|clinical)\s+'
               r'(?:data|information|context)[^.]*?(?:I\s+(?:will|\'ll|'
               r'have)|the\s+following|here\s+is)[^.]*\.', re.IGNORECASE),
    re.compile(r'\bI\s+(?:will|\'ll|have)\s+(?:create|generate|provide|'
               r'compile|present|synthesize|rewrite|combine|summarize)\s+'
               r'(?:a|an|the)?\s*[^.]*\.', re.IGNORECASE),
    re.compile(r'\bThis\s+(?:rewritten|synthesized|combined|generated)\s+'
               r'(?:HPI|narrative|note|entry|section|summary)[^.]*\.',
               re.IGNORECASE),
    re.compile(r'\bThe\s+(?:rewritten|synthesized|combined|generated)\s+'
               r'(?:HPI|narrative|note|entry|section|summary)[^.]*\.',
               re.IGNORECASE),
    re.compile(r'\bThe\s+(?:above|following)\s+(?:HPI|narrative|note|entry|'
               r'section|summary)\s+(?:synthesizes|includes|contains|'
               r'reflects|incorporates)[^.]*\.', re.IGNORECASE),
    # Trailing "Note: I have/I've followed all the rules..." sentence —
    # appears mid-paragraph as a sentence boundary.
    re.compile(r"\bNote\s*:\s*I(?:\s+have|'ve)?\s+(?:followed|adhered|"
               r"complied|maintained|incorporated|synthesized|"
               r"rewritten|generated|created)[^.]*\.", re.IGNORECASE),
    # Bare "I have followed the guidelines/rules/requirements/
    # instructions provided..." — same meta-commentary leak as the
    # Note: variant but without the Note: prefix (Holder failure mode).
    # Match REGARDLESS of trailing period (catches mid-sentence
    # truncations: "I have followed the guidelines provided to generate"
    # with no terminal punctuation).
    re.compile(r"(?:^|[.!?]\s+)I(?:\s+have|'ve)\s+(?:followed|adhered\s+to|"
               r"complied\s+with|maintained|incorporated|synthesized|"
               r"rewritten|generated|created)\s+"
               r"(?:all\s+(?:of\s+)?)?(?:the\s+)?"
               r"(?:rules|guidelines|requirements|instructions|"
               r"directives|protocol|specifications)"
               r"[^.!?]*(?:[.!?]|$)",
               re.IGNORECASE),
    re.compile(r'\bNote\s*:\s*(?:The|This)\s+(?:rewritten|synthesized|'
               r'combined|generated)\s+(?:HPI|narrative|note|entry)[^.]*\.',
               re.IGNORECASE),
    # LLM editorializing about clinical relevance — strip these as
    # they're meta-commentary, not clinical content.
    re.compile(r'\bHowever,?\s+this\s+(?:is|was)\s+not\s+(?:directly\s+)?'
               r'relevant\s+to[^.]*\.', re.IGNORECASE),
    re.compile(r'\bThis\s+(?:is|was)\s+not\s+(?:directly\s+)?relevant\s+to[^.]*\.',
               re.IGNORECASE),
    # Orphan "This represents X" sentence when the antecedent for
    # "this" is unclear. The LLM occasionally drops a one-clause
    # interpretation at the start of the HPI ("This represents
    # biochemical progression.") with no prior sentence providing the
    # subject. Drop when "represents biochemical progression" /
    # "represents biochemical recurrence" / "represents disease
    # progression" appears (these are conclusory phrases that need
    # full clinical context, not floating one-liners).
    re.compile(r'\bThis\s+represents\s+(?:biochemical\s+(?:progression|'
               r'recurrence|response)|disease\s+(?:progression|response)|'
               r'castrate\s+resistance|treatment\s+failure)\s*\.',
               re.IGNORECASE),
)


# Rubric labels the LLM occasionally echoes back from its instructions
# as self-evaluation prose at the end of the HPI. These are highly
# distinctive — no real clinical narrative uses any of them. When one
# appears, everything from that label onwards is meta-commentary.
#
# Seen in production (Woods, 2026-06-23): "...Current vs prior treatment:
# The patient's current treatment status is accurately reflected...
# Post-treatment narrative arc: ... Non-redundancy: ... Medication
# mentions: ..."
_RUBRIC_LEAK_LABEL_RE = re.compile(
    r"\s*\b(?:"
    r"Current\s+vs\.?\s+prior\s+treatment|"
    r"Post-treatment\s+narrative\s+arc|"
    r"Narrative\s+arc|"
    r"Non-redundancy|"
    r"Non\s+redundancy|"
    r"Medication\s+mentions|"
    r"Clinical\s+accuracy|"
    r"Treatment\s+status\s+accuracy|"
    r"Temporal\s+anchors?|"
    r"Specific\s+dates?\s+only|"
    r"Cleanup\s+notes?"
    r")\s*:",
    re.IGNORECASE,
)

# Trailing "I hope this..." / "Hope this..." closing remarks the LLM
# emits as a polite sign-off after the rubric leak. Truncation often
# leaves bare "I hope" with no terminal punctuation.
_TRAILING_SIGNOFF_RE = re.compile(
    r"(?:^|\s)(?:I\s+hope|Hope\s+(?:this|that)|Hopefully|Please\s+let\s+me\s+know)"
    r"[^.!?]*(?:[.!?]|$)",
    re.IGNORECASE,
)


def _strip_rubric_leak(text: str) -> str:
    """Truncate at first rubric-label echo (e.g. "Non-redundancy:").

    These labels never appear in real clinical narrative — they're the
    LLM regurgitating sections from its instruction rubric as a
    self-evaluation block. Everything from the first label onwards is
    meta-commentary and must be removed.
    """
    if not text:
        return text
    m = _RUBRIC_LEAK_LABEL_RE.search(text)
    if m:
        text = text[:m.start()].rstrip()
    # Strip any trailing polite sign-off ("I hope this helps.")
    text = _TRAILING_SIGNOFF_RE.sub('', text).rstrip()
    return text


# This IS the urology clinic — cross-specialty referral framing must be
# stripped from HPI prose. The LLM sometimes carries forward language
# from source clinical notes that frame urologic management as a
# referral from / to "urology" as if urology were a separate service:
#
#   "Our plan would be for androgen ablation by urology..." (Woods, v1)
#   "Patient referred to urology for evaluation of elevated PSA"
#   "Will obtain urology consult"
#
# All of these read awkwardly in a urology clinic note. Strip the
# offending phrasing or rewrite to first-person/active voice.
_UROLOGY_REFERRAL_PATTERNS = (
    # "by urology" / "by the urology service" / "by the urology team"
    (re.compile(r"\s+by\s+(?:the\s+)?urology(?:\s+(?:service|team|clinic|department))?\b",
                re.IGNORECASE), ""),
    # "to urology" in referral context — only strip when preceded by
    # referral verbs to avoid stripping legitimate "transferred to
    # urology for" in a non-urology note.
    (re.compile(r"\b(?:refer(?:red)?|sent|forwarded|consulted)\s+to\s+(?:the\s+)?urology(?:\s+(?:service|team|clinic))?\b",
                re.IGNORECASE), "evaluated"),
    # "urology consult" / "consult urology" / "urology consultation"
    (re.compile(r"\b(?:will\s+(?:obtain|get|request|order)\s+(?:a\s+)?)?urology\s+consult(?:ation)?\b",
                re.IGNORECASE), "urologic evaluation"),
    (re.compile(r"\b(?:will\s+)?consult\s+urology\b", re.IGNORECASE),
     "perform urologic evaluation"),
    # "urology will follow up" / "urology to follow" / "urology to evaluate"
    (re.compile(r"\burology\s+(?:will\s+|to\s+)(?:follow(?:\s+up)?|evaluate|see|manage)\b",
                re.IGNORECASE), "we will continue to manage"),
    # "follow up with urology" / "f/u with urology"
    (re.compile(r"\b(?:follow(?:\s*[-/]?\s*up)?|f/u)\s+with\s+(?:the\s+)?urology\b",
                re.IGNORECASE), "follow up with us"),
)


def strip_urology_referral_framing(text: str) -> str:
    """Strip cross-specialty referral language from HPI prose.

    See _UROLOGY_REFERRAL_PATTERNS for the patterns. This is a
    post-processor for v1-LLM-generated HPIs that carry forward
    multi-specialty narrative from source notes."""
    if not text:
        return text
    for pat, repl in _UROLOGY_REFERRAL_PATTERNS:
        text = pat.sub(repl, text)
    # Collapse any double-spaces / dangling spaces from substitutions
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([.,;])", r"\1", text)
    return text.strip()


# Trailing-fragment cleanup applied AFTER sentence drops. Removes
# orphan tokens like "Here is," "Mr." (no name), "The patient,"
# that survive the broader cleanup.
_FRAGMENT_CLEANUP_PATTERNS = (
    # "Mr. LAST,FIRST" / "Mr. LAST,FIRST MIDDLE JR" — VistA name format
    # leaked into prose. Replace with "The patient" so the HPI doesn't
    # read like a database dump.
    (re.compile(r"\bMr\.\s+[A-Z]+,[A-Z][A-Z\s]+\b(?=[\s,])",
                re.IGNORECASE), "The patient"),
    # Same for last-name-first format without honorific at start of sentence
    (re.compile(r"(^|\.\s+)[A-Z]+,[A-Z][A-Z\s]+(?=\s+(?:is|was|has|had|"
                r"returns|reports|denies|complains)\b)",
                re.IGNORECASE), r"\1The patient"),
    # "Here is, foo" / "Here is the rewritten HPI, foo" → "Foo"
    (re.compile(r"^Here(?:'s|\s+(?:is|are))[^.A-Z0-9]*?[,:]\s*", re.IGNORECASE), ""),
    # "Based on the provided clinical data context, Mr. Smith..." → "Mr. Smith..."
    # — drop the meta clause leading up to the first comma.
    (re.compile(r"^Based\s+on\s+(?:the\s+)?(?:provided|above|available|"
                r"given|clinical)[^.,]*?,\s*", re.IGNORECASE), ""),
    # "Mr., a 65-year-old" / "Ms., a 53-year-old" (placeholder name was
    # stripped) → "The patient, a 65-year-old". Anchored to start-of-
    # text (allowing optional leading whitespace) OR start-of-sentence
    # (after period+space).
    (re.compile(r"(^\s*|\.\s+)(Mr|Ms|Mrs|Dr)\.?\s*,\s+", re.IGNORECASE),
     r"\1The patient, "),
    # "Mr. <verb-like-word>" / "Mr. He" / "Mr. She" with no name
    # between honorific and pronoun/verb. The LLM often produces
    # "Today, Mr. He has been experiencing..." when the name placeholder
    # was stripped. Replace "Mr. He" → "He", "Mr. She" → "She".
    (re.compile(r"(^|[\s,.])(?:Mr|Ms|Mrs|Dr)\.?\s+(?=(?:He|She|They|It)\b)",
                re.IGNORECASE),
     r"\1"),
    (re.compile(r",\s+(?:Mr|Ms|Mrs|Dr)\.?\s+"
                r"(?=(?:has|is|was|will|had|reports|returns|comes|presents|"
                r"denies|complains|notes|states|describes|completed|"
                r"underwent|received|started|stopped|continues)\b)",
                re.IGNORECASE),
     ", the patient "),
    (re.compile(r"(^|\.\s+)(?:Mr|Ms|Mrs|Dr)\.?\s+"
                r"(?=(?:has|is|was|will|had|reports|returns|comes|presents|"
                r"denies|complains|notes|states|describes|completed|"
                r"underwent|received|started|stopped|continues)\b)",
                re.IGNORECASE),
     r"\1The patient "),
)


# Bracketed placeholder shapes that look like prompt instructions echoed
# into the output. Removed wherever they appear, even mid-sentence.
_INLINE_PLACEHOLDER_RE = re.compile(
    r'\[(?:'
    r'List\s+(?:of\s+)?[^\]]+|'
    r'Insert\s+[^\]]+|'
    r'Describe\s+[^\]]+|'
    r'Provide\s+[^\]]+|'
    r'Specify\s+[^\]]+|'
    # "Patient's Name" / "Patient Name" / "Patient ID" / "Patient DOB"
    # — apostrophe-s is a 2-char unit, NOT a char class. Also catches
    # bare "[Last Name]" / "[First Name]" / "[Full Name]" placeholders.
    r"Patient(?:'s)?\s+[A-Za-z\s]+|"
    r"(?:Last|First|Full|Middle)\s+Name|"
    r"DOB|MRN|Date\s+of\s+(?:Birth|Service)|"
    r'To\s+be\s+(?:documented|completed|determined|filled)[^\]]*|'
    r'If\s+(?:applicable|the\s+patient)[^\]]*|'
    r'Optional[^\]]*|'
    r'Not\s+(?:provided|documented|available|specified)[^\]]*|'
    r'Placeholder[^\]]*|'
    r'TBD[^\]]*|'
    r'N/A[^\]]*|'
    r'See\s+(?:above|below|HPI)[^\]]*|'
    r'Current\s+medication[^\]]*'
    r')\]',
    re.IGNORECASE,
)


# Stripped legacy patterns retained for backward compat with callers
# that haven't switched yet.
_LEGACY_INLINE_PATTERNS = (
    re.compile(r'This entry reflects that ', re.IGNORECASE),
    re.compile(r'This entry reflects ', re.IGNORECASE),
    re.compile(r'\(No information was provided[^)]*\)', re.IGNORECASE),
    re.compile(r'\s+are also mentioned but are less relevant to urologic health',
               re.IGNORECASE),
    re.compile(r'\s+so there is nothing to report', re.IGNORECASE),
)


def _collapse_word_doubling(text: str) -> str:
    """Remove "previously previously" / "now declining, now declining" style
    immediate repetitions the LLM produces when it loses track of state.

    Conservative: only collapses literal repetition of 1-3 word phrases
    that share exact case-insensitive equality."""
    # Pattern A: "word1 word2 word3 word1 word2 word3" (3-word repeat)
    text = re.sub(
        r'\b(\w+(?:\s+\w+){0,2})\s+\1\b',
        r'\1',
        text,
        flags=re.IGNORECASE,
    )
    # Pattern B: ", PHRASE, PHRASE" - duplicated clauses inside lists
    text = re.sub(
        r',\s+(\w+(?:\s+\w+){0,3}),\s+\1\b',
        r', \1',
        text,
        flags=re.IGNORECASE,
    )
    return text


def clean_llm_commentary(text: str) -> str:
    """Strip LLM meta-commentary, Markdown leakage, and template residue.

    Hardened against:
      - Markdown headers ("**Patient Name:** [Not Provided]")
      - Meta intros ("Based on... I will create...")
      - Closing notes ("Note:** This rewritten HPI narrative...")
      - Bracketed prompt-instruction placeholders ("[List of meds]")
      - Word doubling ("previously previously", "now declining, now declining")
    """
    if not text:
        return text

    # Pass 0: rubric-leak truncation. Runs FIRST so the rest of the
    # cleaner doesn't waste cycles on the meta-block, and so subsequent
    # sentence-split logic isn't confused by the label colons.
    text = _strip_rubric_leak(text)

    # Pass 0b: strip cross-specialty urology-referral framing. This IS
    # the urology clinic — "by urology", "urology consult", "refer to
    # urology" etc. must not appear in HPI prose.
    text = strip_urology_referral_framing(text)

    # Pass 1: line-level drops
    out_lines = []
    for line in text.split('\n'):
        if any(p.match(line) for p in _LINE_DROP_PATTERNS):
            continue
        out_lines.append(line)
    text = '\n'.join(out_lines)

    # Pass 1b: drop SENTENCES whose meaningful content is dominated by a
    # bracketed instruction-shaped placeholder. Sentences where the
    # placeholder is the predominant content ("Currently, they reside in
    # a [insert living situation].") become ungrammatical orphans after
    # bracket removal — drop them entirely. Sentences where the bracket
    # is a small inline aside ("He had cysto. [List of meds]. Returns
    # today.") still keep their non-bracket text.
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z\[])', text)
    keep = []
    for s in sentences:
        if not _INLINE_PLACEHOLDER_RE.search(s):
            keep.append(s)
            continue
        # If the placeholder removal leaves <15 chars of meaningful text,
        # OR leaves a dangling preposition / article at the end
        # ("Currently, they reside in a."), drop the sentence entirely.
        stripped = _INLINE_PLACEHOLDER_RE.sub('', s).strip(' .,;:[]')
        if len(stripped) < 15:
            continue
        if re.search(
            r'\b(?:a|an|the|in|on|at|with|for|by|of|to|as|from|about|'
            r'including|such\s+as|that|which|where|when|who)\.?$',
            stripped, re.IGNORECASE,
        ):
            continue
        keep.append(s)
    text = ' '.join(keep)

    # Pass 2: inline placeholder removal (handles any survivors that
    # weren't inside a recognizable sentence boundary).
    text = _INLINE_PLACEHOLDER_RE.sub('', text)

    # Pass 3: sentence-level drops
    for pat in _SENTENCE_DROP_PATTERNS:
        text = pat.sub('', text)

    # Pass 4: legacy inline cleanups
    for pat in _LEGACY_INLINE_PATTERNS:
        text = pat.sub('', text)

    # Pass 4b: fragment cleanup — leftover scaffolding tokens
    for pat, repl in _FRAGMENT_CLEANUP_PATTERNS:
        text = pat.sub(repl, text)

    # Pass 5: collapse word-doubling
    text = _collapse_word_doubling(text)

    # Pass 6: strip stray ** markers and bullet markers, normalize ws
    lines_final = []
    for line in text.split('\n'):
        # Strip lone bullet stars and surrounding whitespace
        line = re.sub(r'\*\*', '', line)  # drop any remaining markdown emphasis
        line = line.lstrip('* \t')
        stripped = line.strip()
        if stripped and stripped not in ('---', '___', '***'):
            lines_final.append(line)
    result = '\n'.join(lines_final)

    # Collapse multiple blank lines and trim
    result = re.sub(r'\n{3,}', '\n\n', result)
    # Collapse stray double-spaces created by sentence drops
    result = re.sub(r'  +', ' ', result)
    # Stray "  ." or "  ," from sentence removal
    result = re.sub(r'\s+([.,;:])', r'\1', result)
    # Strip trailing orphan "Note:" / "Note" labels left after the
    # closing-note sentence was dropped.
    result = re.sub(r'(?:\s|^)\*?\*?Note\s*:?\s*\*?\*?\s*$', '', result,
                    flags=re.IGNORECASE | re.MULTILINE)
    # Strip trailing "Please note that" / "Note that" / "Notice that"
    # incomplete sentences left when the rest got dropped by a
    # sentence-drop pattern.
    result = re.sub(
        r'(?:^|\s)(?:Please\s+note|Note|Notice)\s+that[^.!?]*$',
        '', result, flags=re.IGNORECASE | re.MULTILINE,
    )
    # Strip trailing fragments that begin a sentence but have no
    # period (LLM cut-off): "He continues taking", "The patient is
    # currently", etc. with no terminal punctuation.
    return result.strip()
