import pdfplumber
from docx import Document
import os
from services.resume_ai_extractor import extract_resume_data

def extract_text_from_pdf(path: str) -> str:
    text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text.append(page_text)
    return "\n".join(text)


def extract_text_from_docx(path: str) -> str:
    doc = Document(path)
    return "\n".join([para.text for para in doc.paragraphs])


def process_single_resume(resume_path: str) -> dict:
    if resume_path.lower().endswith(".pdf"):
        resume_text = extract_text_from_pdf(resume_path)
    elif resume_path.lower().endswith(".docx"):
        resume_text = extract_text_from_docx(resume_path)
    else:
        raise Exception("Unsupported format")

    if not resume_text.strip():
        raise Exception("Empty resume content")

    # 🔥 AI extraction step
    extracted_data = extract_resume_data(resume_text)
    print("AI extracted:", extracted_data)


    return {
        "resume_file": os.path.basename(resume_path),
        "extracted_data": extracted_data
    }
