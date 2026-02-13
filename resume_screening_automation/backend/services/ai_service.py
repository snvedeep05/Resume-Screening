import os
import json
from groq import Groq
from prompts.recruiter_prompt import JOB_CONFIG_PROMPT

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def normalize_scoring_weights(weights: dict) -> dict:
    total = sum(weights.values())

    # Case 1: AI returned 0–1 scale (floats like 0.3)
    if total <= 1.5:
        return {k: int(v * 100) for k, v in weights.items()}

    # Case 2: Integers but not summing to 100
    if total != 100:
        return {
            k: int((v / total) * 100)
            for k, v in weights.items()
        }

    return weights


def generate_job_config(job_description: str) -> dict:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": JOB_CONFIG_PROMPT},
            {"role": "user", "content": job_description}
        ],
        temperature=0.2
    )

    content = response.choices[0].message.content.strip()

    try:
        job_config = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("AI did not return valid JSON")

    # 🔒 ENFORCE SCORING WEIGHTS RULES HERE
    if "scoring_weights" in job_config:
        job_config["scoring_weights"] = normalize_scoring_weights(
            job_config["scoring_weights"]
        )

    return job_config


