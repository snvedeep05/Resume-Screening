import os
import json
from groq import Groq
from prompts.resume_extraction_prompt import RESUME_EXTRACTION_PROMPT

_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = Groq(api_key=api_key)
    return _client


def extract_resume_data(resume_text: str) -> dict:
    response = get_client().chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": RESUME_EXTRACTION_PROMPT},
            {"role": "user", "content": resume_text}
        ],
        temperature=0.1
    )

    content = response.choices[0].message.content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("AI did not return valid JSON")
