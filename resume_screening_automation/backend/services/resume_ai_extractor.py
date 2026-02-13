import os
import json
from groq import Groq
from backend.prompts.resume_extraction_prompt import RESUME_EXTRACTION_PROMPT

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def extract_resume_data(resume_text: str) -> dict:
    response = client.chat.completions.create(
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
