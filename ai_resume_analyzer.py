import os
from openai import OpenAI
from dotenv import load_dotenv

# Load .env only for local development
load_dotenv()

# Read API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY environment variable is not set")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)


def analyze_resume(resume_text):
    prompt = f"""
You are an AI recruitment assistant.

From the resume text below, extract:
1. Technical skills
2. Projects with technologies used
3. Experience level (Beginner / Intermediate / Advanced)

Return STRICT JSON in this format:
{{
  "skills": ["skill1", "skill2"],
  "projects": [
    {{
      "title": "Project Name",
      "technologies": ["tech1", "tech2"]
    }}
  ],
  "experience_level": "Beginner/Intermediate/Advanced"
}}

Resume Text:
\"\"\"
{resume_text}
\"\"\"
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a precise JSON-only response generator."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    # Return ONLY the model output (JSON string)
    return response.choices[0].message.content