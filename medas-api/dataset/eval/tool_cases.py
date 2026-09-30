"""The tool-calling cases run by run_tool_eval.py.

Each case names the tool that must be called (None: no tool at all) and, in
params, {argument: keywords} that must all appear, case-insensitively, in that
tool's calls (None skips the check). attachments are the PDFs sent with the
message.
"""

from langchain_agent.documents import Attachment

RECORD_ID = "pat_7f3c9a21-4be8-4d0f-9c17-2a6e5b8d41f0"
SEARCH = "search_patient_record"
ADD = "add_patient_document"
LETTER = Attachment("letter.pdf", b"%PDF-1.4")
LAB = Attachment("blood_test_2026.pdf", b"%PDF-1.4")


def case(query, difficulty, tool=None, params=None, attachments=()):
    return {
        "query": query,
        "expected_tool": tool,
        "expected_params": params,
        "attachments": attachments,
        "difficulty": difficulty,
    }


test_cases = [
    # -- Easy: clear intent, obvious tool --
    case(
        "What medications am I currently taking?",
        "easy",
        SEARCH,
        {"query": ["medication"]},
    ),
    case("Am I allergic to ibuprofen?", "easy", SEARCH, {"query": ["ibuprofen"]}),
    case(
        "upload file requested: letter.pdf",
        "easy",
        ADD,
        {"document": ["letter.pdf"]},
        [LETTER],
    ),
    # -- Medium: indirect phrasing, misleading keywords --
    case(
        "The new pills make my chest feel a bit tight after meals.",
        "medium",
        SEARCH,
        {"query": ["chest"]},
    ),
    case(
        "Here are my latest blood results (blood_test_2026.pdf), "
        "can you keep them with my file?",
        "medium",
        ADD,
        {"document": ["blood_test_2026.pdf"]},
        [LAB],
    ),
    case(
        "Did I ever have a reaction like this before? My throat itches.",
        "medium",
        SEARCH,
    ),
    case("What does hypertension mean?", "medium"),
    # -- Hard: blended intents, a missing file --
    case(
        "I attached my discharge letter, letter.pdf. Store it, then tell me "
        "whether it changes which drugs I should avoid.",
        "hard",
        ADD,
        {"document": ["letter.pdf"]},
        [LETTER],
    ),
    case(
        "I took aspirin and now my lips are swelling. What am I on already?",
        "hard",
        SEARCH,
        {"query": ["allerg"]},
    ),
    # Nothing by that name was attached; the tool must be asked (and will
    # refuse), not skipped.
    case("upload file requested: report.pdf", "hard", ADD, None, [LETTER]),
    # -- Edge cases: no tool should be called --
    case("Thanks, that is all!", "edge_case"),
    case("Tell me a joke.", "edge_case"),
    case("What medications is my sister taking?", "edge_case"),
    case("How do I book an appointment with my GP?", "edge_case"),
]
