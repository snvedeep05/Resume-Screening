RESUME_EXTRACTION_PROMPT = """
You are an information extraction system.

Extract structured information from the given resume text.
Return ONLY valid JSON. Do not include explanations.

The JSON must STRICTLY follow this schema and MUST include ALL keys.

{
  "personal_details": {
    "full_name": string,
    "email": string,
    "phone": string | null
  },

  "skills": [string],

  "education": [
    {
      "degree": string,
      "field": string,
      "institution": string,
      "passed_out_year": number | null
    }
  ],

  "projects": [
    {
      "title": string,
      "domain": string,
      "tech_stack": [string]
    }
  ],

  "experience_years": number,

  "passed_out_year": number | null
}

RULES:
- Output ONLY valid JSON
- Do NOT add explanations
- Do NOT add markdown
- Do NOT rename keys
- Use empty lists if information is missing
- Use null for phone if not found
- Extract email ONLY if explicitly present
- Do NOT hallucinate names, emails, degrees, or companies
- Infer project domains conservatively (e.g. "web", "backend", "ai", "ml")
- "passed_out_year" (top-level) is the year the candidate completed or is expected to complete their most recent degree (B.Tech or equivalent). Extract from graduation year, passing year, or expected graduation year mentioned in the resume. Use null if not found.
- For each education entry, "passed_out_year" is the year that specific degree was or will be completed. Use null if not mentioned.
"""
