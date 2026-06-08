"""ELLIPSE English-proficiency rubric, structured for prompting.

Source: ELL_Rubrics.docx from the ELLIPSE Corpus (Crossley et al.), an
open-source rubric used by trained human raters to score English Language
Learner writing. Scores run 1 (lowest) to 5 (highest) in 0.5 increments on an
overall holistic dimension plus six analytic dimensions.
"""
from __future__ import annotations

SCALE_MIN = 1.0
SCALE_MAX = 5.0
SCALE_STEP = 0.5

# Analytic dimension keys -> human label.
DIMENSIONS: dict[str, str] = {
    "overall": "Overall",
    "cohesion": "Cohesion",
    "syntax": "Syntax",
    "vocabulary": "Vocabulary",
    "phraseology": "Phraseology",
    "grammar": "Grammar",
    "conventions": "Conventions",
}

# Band descriptors, verbatim-faithful to the ELLIPSE rubric.
BANDS: dict[str, dict[int, str]] = {
    "overall": {
        5: "Native-like facility with syntactic variety, appropriate word choice and phrases, well-controlled organization, and precise grammar/conventions; rare inaccuracies that do not impede communication.",
        4: "Facility with syntactic variety and a range of words/phrases; controlled organization; accuracy in grammar and conventions; occasional inaccuracies that rarely impede communication.",
        3: "Facility limited to common structures and generic vocabulary; organization generally controlled though connections sometimes absent; errors in grammar, syntax, and usage that impede communication in some cases.",
        2: "Inconsistent facility in sentence formation, word choice, and mechanics; organization partially developed but may be missing or unsuccessful; communication impeded in many instances.",
        1: "A limited range of familiar words/phrases loosely strung together; frequent errors in grammar and usage; communication impeded in most cases.",
    },
    "cohesion": {
        5: "Text organization consistently well controlled using a variety of effective devices (reference, transitions) to connect ideas across sentences and paragraphs; appropriate overlap of ideas.",
        4: "Organization generally well controlled; a range of cohesive devices used appropriately to connect ideas; generally appropriate overlap of ideas.",
        3: "Organization generally controlled; cohesive devices used but limited in type; some repetitive, mechanical, or faulty cohesion within/between sentences and paragraphs.",
        2: "Organization only partially developed with a lack of logical sequencing; some basic cohesive devices used but with inaccuracy or repetition.",
        1: "No clear control of organization; cohesive devices absent or unsuccessful; presentation of ideas unclear.",
    },
    "syntax": {
        5: "Flexible, effective use of a full range of syntactic structures (simple, compound, complex); rare minor, negligible errors in sentence formation.",
        4: "Appropriate use of a variety of syntactic structures; occasional errors or inappropriateness in sentence formation.",
        3: "Simple, compound, and complex structures present though range may be limited; some apparent errors, especially in more complex sentences.",
        2: "Some sentence variation used; many sentence-structure problems.",
        1: "Pervasive, basic errors in sentence structure and word order that cause confusion.",
    },
    "vocabulary": {
        5: "Wide range of vocabulary flexibly and effectively used to convey precise meaning; skillful use of topic-related and less common words; rare negligible inaccuracies.",
        4: "Sufficient range for flexibility and precision; appropriate use of topic-related terms and less common lexical items.",
        3: "Minimally adequate range for the topic; no precise use of subtle meanings; topic terms used occasionally; attempts at less common vocabulary with some inaccuracy.",
        2: "Narrow range conveying basic meaning; topic terms used inappropriately; errors in word formation/choice that may distort meaning.",
        1: "Limited vocabulary often inappropriately used; little attempt to use topic-related terms.",
    },
    "phraseology": {
        5: "Flexible, effective use of a variety of phrases (idioms, collocations, lexical bundles) to convey precise and subtle meaning; rare negligible inaccuracies.",
        4: "Appropriate use of a variety of phrases; occasional inaccuracies and colloquialisms.",
        3: "Evident use of phrases but without much variety; some inaccuracies.",
        2: "Narrow range of phrases conveying basic meaning; many repetitions and/or misuses.",
        1: "Memorized chunks or simple phrasal patterns predominate; many repetitions and misuses.",
    },
    "grammar": {
        5: "Command of grammar and usage with few or no errors.",
        4: "Minimal errors in grammar and usage.",
        3: "Errors in grammar and syntax and usage; communication impeded in some cases.",
        2: "Many errors in grammar and usage.",
        1: "Errors in grammar and usage throughout.",
    },
    "conventions": {
        5: "Consistent use of appropriate conventions; spelling, capitalization, and punctuation errors nonexistent or negligible.",
        4: "Generally consistent conventions; spelling/capitalization/punctuation errors few and not distracting.",
        3: "Conventions present but inconsistent; noticeable spelling/capitalization/punctuation errors.",
        2: "Variable use of conventions; spelling, capitalization, and punctuation errors frequent and distracting.",
        1: "Minimal use of conventions; spelling, capitalization, and punctuation errors throughout.",
    },
}

KEY_TERMS = (
    "Phrase: multi-word units. "
    "Grammar: rules by which words change form (word classes, morphology like plural/possessive/3rd-person). "
    "Syntax: structuring sentences (coordinating clauses, building noun/verb/prep phrases, passives, relative clauses). "
    "Cohesive device: links between items in a text (conjunctions, transitions, repetition, pronoun anaphora). "
    "Collocations: words often used together (save time, fast food). "
    "Lexical bundles: common but non-idiomatic units (there is). "
    "Idioms: meaning not deducible from individual words (kick the bucket)."
)

# Categories an annotation may be tagged with (drives UI color + filtering).
ANNOTATION_TYPES = [
    "thesis",        # argument / main claim
    "evidence",      # support, examples, reasoning
    "organization",  # structure, paragraphing, flow
    "cohesion",      # transitions, linking, reference
    "vocabulary",    # word choice
    "grammar",       # grammar / usage
    "syntax",        # sentence structure
    "conventions",   # spelling, punctuation, capitalization
    "style",         # tone, voice, concision
    "praise",        # something done well — reinforce it
]


def rubric_as_text() -> str:
    """Render the full rubric as a compact text block for the system prompt."""
    lines = ["ENGLISH PROFICIENCY SCORING RUBRIC (ELLIPSE, 1-5, 0.5 steps)\n"]
    for key, label in DIMENSIONS.items():
        lines.append(f"## {label}")
        for band in (5, 4, 3, 2, 1):
            lines.append(f"  {band}: {BANDS[key][band]}")
        lines.append("")
    lines.append("KEY TERMS: " + KEY_TERMS)
    return "\n".join(lines)
