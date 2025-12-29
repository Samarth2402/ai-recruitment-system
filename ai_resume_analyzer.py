import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return response.choices[0].message.content