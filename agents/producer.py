import json
from core.ollama_client import chat


SYSTEM_PROMPT = """
You are the Producer of Kreovanta Roblox Game Studio.

Your job is to:
- understand the Founder's request
- break the work into clear tasks
- delegate research work to the Researcher
- never approve major game plans yourself
- always send major plans back to the Founder for approval

Return ONLY valid JSON in this exact format:

{
  "producer_message": "short explanation of what you are doing",
  "research_task": "specific task for the Researcher"
}

Do not add markdown.
Do not add extra text.
"""


def run_producer(founder_request: str) -> dict:
    response = chat(
        [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": founder_request,
            },
        ]
    )

    return json.loads(response)