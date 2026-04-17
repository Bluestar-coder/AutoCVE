from __future__ import annotations

NO_TOOLS_PREAMBLE = """CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.

- Do NOT use Read, Bash, Grep, Glob, Edit, Write, or ANY other tool.
- You already have all the context you need in the conversation above.
- Tool calls will be REJECTED and will waste your only turn; you will fail the task.
- Your entire response must be plain text: an <analysis> block followed by a <summary> block.

"""

NO_TOOLS_TRAILER = """
Do not call any tools. Return only plain text with one <analysis> block and one <summary> block.
""".lstrip("\n")

_DETAILED_ANALYSIS_INSTRUCTION_BASE = """Before providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts and ensure you've covered all necessary points. In your analysis process:

1. Chronologically analyze each message and section of the conversation. For each section thoroughly identify:
   - The user's explicit requests and intents
   - Your approach to addressing the user's requests
   - Key decisions, technical concepts and code patterns
   - Specific details like:
     - file names
     - full code snippets
     - function signatures
     - file edits
   - Errors that you ran into and how you fixed them
   - Pay special attention to specific user feedback that you received, especially if the user told you to do something differently.
2. Double-check for technical accuracy and completeness, addressing each required element thoroughly."""

_DETAILED_ANALYSIS_INSTRUCTION_PARTIAL = """Before providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts and ensure you've covered all necessary points. In your analysis process:

1. Analyze the recent messages chronologically. For each section thoroughly identify:
   - The user's explicit requests and intents
   - Your approach to addressing the user's requests
   - Key decisions, technical concepts and code patterns
   - Specific details like:
     - file names
     - full code snippets
     - function signatures
     - file edits
   - Errors that you ran into and how you fixed them
   - Pay special attention to specific user feedback that you received, especially if the user told you to do something differently.
2. Double-check for technical accuracy and completeness, addressing each required element thoroughly."""

BASE_COMPACT_PROMPT = f"""Your task is to create a detailed summary of the conversation so far, paying close attention to the user's explicit requests and your previous actions.
This summary should be thorough in capturing technical details, code patterns, and architectural decisions that would be essential for continuing development work without losing context.

{_DETAILED_ANALYSIS_INSTRUCTION_BASE}

Your summary should include the following sections:

1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections
4. Errors and fixes
5. Problem Solving
6. All user messages
7. Pending Tasks
8. Current Work
9. Optional Next Step
"""

PARTIAL_COMPACT_PROMPT = f"""Your task is to create a detailed summary of the RECENT portion of the conversation - the messages that follow earlier retained context. The earlier messages are being kept intact and do NOT need to be summarized. Focus your summary on what was discussed, learned, and accomplished in the recent messages only.

{_DETAILED_ANALYSIS_INSTRUCTION_PARTIAL}

Your summary should include the following sections:

1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections
4. Errors and fixes
5. Problem Solving
6. All user messages
7. Pending Tasks
8. Current Work
9. Optional Next Step
"""

PARTIAL_COMPACT_UP_TO_PROMPT = f"""Your task is to create a detailed summary of this conversation. This summary will be placed at the start of a continuing session; newer messages that build on this context will follow after your summary (you do not see them here). Summarize thoroughly so that someone reading only your summary and then the newer messages can fully understand what happened and continue the work.

{_DETAILED_ANALYSIS_INSTRUCTION_BASE}

Your summary should include the following sections:

1. Primary Request and Intent
2. Key Technical Concepts
3. Files and Code Sections
4. Errors and fixes
5. Problem Solving
6. All user messages
7. Pending Tasks
8. Work Completed
9. Context for Continuing Work
"""


def build_compaction_prompt(*, mode: str, custom_instructions: str | None = None) -> str:
    prompt_map = {
        "base": BASE_COMPACT_PROMPT,
        "partial": PARTIAL_COMPACT_PROMPT,
        "partial_up_to": PARTIAL_COMPACT_UP_TO_PROMPT,
    }
    try:
        prompt_body = prompt_map[mode]
    except KeyError as exc:
        raise ValueError(f"Unknown compaction prompt mode: {mode}") from exc

    instructions_block = ""
    if custom_instructions:
        instructions_block = (
            "\n\nAdditional summarization instructions:\n"
            f"{custom_instructions.strip()}\n"
        )
    return f"{NO_TOOLS_PREAMBLE}{prompt_body}{instructions_block}\n{NO_TOOLS_TRAILER}"

def format_compact_summary(summary: str) -> str:
    text = str(summary or "").strip()
    if "<summary>" in text and "</summary>" in text:
        text = text.split("<summary>", 1)[1].split("</summary>", 1)[0].strip()
    if "<analysis>" in text and "</analysis>" in text:
        before = text.split("<analysis>", 1)[0]
        after = text.split("</analysis>", 1)[1] if "</analysis>" in text else ""
        text = f"{before} {after}".strip()
    return text


def get_compact_user_summary_message(summary: str, suppress_follow_up_questions: bool, transcript_path: str | None = None) -> str:
    formatted = format_compact_summary(summary)
    lines = [formatted]
    if transcript_path:
        lines.append(f"Transcript reference: {transcript_path}")
    if not suppress_follow_up_questions:
        lines.append("Follow-up questions may still be needed for unresolved gaps.")
    return "\n\n".join(line for line in lines if line)
