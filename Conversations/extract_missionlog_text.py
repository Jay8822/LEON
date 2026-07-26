import pdfplumber

input_file = r"C:\Users\jaypr\Desktop\AI Stack\Conversations\Marquez-MissionLog-v3-1.pdf"
output_file = "mission_log_extracted.text"

with pdfplumber.open(input_file) as pdf:
    with open(output_file, "w", encoding="utf-8") as out:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text:
                out.write(f"--- PAGE {page_num} ---\n")
                out.write(text)
                out.write("\n\n")

print("Text extraction complete. Output saved to:", output_file)
