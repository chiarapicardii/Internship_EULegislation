import pymupdf4llm
import pymupdf
import re 
from pathlib import Path
import csv 

#____CLEANING FUNCTIONS_____

def clean_metadata(text):
    if not text: 
        return ""
    text = text.replace('**', '')
    text = re.sub(r'\n+', ' ', text)
    return text.strip()

def clean_text(text):
    if not text: 
        return ""
    text = re.sub(r'<br\s*/?>', '\n', text) #converting <br> to newlines
    text = re.sub(r'\bEN\b', '', text) #deleting the EN
    text = re.sub(r'^\s*\d+\s*$', '', text, flags=re.MULTILINE) #deleting the pg number
    text = re.sub(r'\n{3,}', '\n\n', text) #deleting the multiple newlines
    text = re.sub(r'^\s*\*{3,}\s*$', '', text, flags=re.MULTILINE) #deleting the lines with only *** or more
    return text.strip() 

#____ TABLE EXTRACTION FOR MARKDOWN ____________
def save_table(table_lines, section, stem_name, output_folder, count_dict, saved_files):
    if not section:
        section = "misc"

    logical_rows = [] #lines reconstruted 
    current_row_str = "" #temporary variable to save the table line by line

    for line in table_lines:#iterating through all the lines of the table 
        line_stripped = line.strip()
        if not line_stripped: #if it's empty: skip
            continue 
        if re.match(r'^[\|\s\-:]+$', line_stripped):#if the line contains just -- or || or : it's skipped
            continue #skip markdown formatting 

        if line_stripped.startswith('|'): #the markdown table
            if current_row_str:#if there was alrealy something saved in the variable 
                logical_rows.append(current_row_str)
            current_row_str = line_stripped 
        else: 
            if current_row_str: #otherwise if it doesn't start with | it's a /n inside the table 
                current_row_str += " " + line_stripped #it still needs to be saved 
            else: 
                current_row_str = line_stripped
    
    if current_row_str: 
        logical_rows.append(current_row_str)

    rows = [] #iterating through the rows 
    for row_str in logical_rows: 
        cells = []
        row_str = row_str.strip('|')
        for c in row_str.split('|'):
            c = re.sub(r'<br\s*/?>', ' ', c)
            c = re.sub(r'\*+', '', c)
            c = re.sub(r'_', '', c)  
            c = re.sub(r'\s+', ' ', c).strip()
            cells.append(c)
        
        if any(cells): #if the line has at least one cell, it's added to the rows
            rows.append(cells)

    if not rows: 
        return 
        
    #counter for the saving name 
    count_dict[section] = count_dict.get(section, 0) + 1
    t = count_dict[section] #the num of tables found and saved 
    csv_name = f"{stem_name}_s4{section}_t{t}.csv"

    with open(output_folder / csv_name, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    saved_files.append(csv_name)

def _process_lines(md_content, stem_name, output_folder):
    #this reads the whole document and checks for a table 
    saved_files = []
    table_count_per_section = {}
    lines = md_content.split("\n") #text divided line by line
    cleaned_lines = []
    current_section = "misc"
    table_lines = []
    in_table = False 

    def flush_table(): #middle function to send the lines to save table
        nonlocal table_lines, in_table #function to modify the variable inside this def
        if table_lines: 
            save_table(table_lines, current_section, stem_name, output_folder, table_count_per_section, saved_files)
            table_lines = []
        in_table = False 

    for i, line in enumerate(lines): 
        m = re.match(r'^#{1,3}\s+[_*]*4\.(\d+)', line) #checks line by line and looks for titles like 4.x
        if m: 
            flush_table() #if it finds it it sends it to flush --> save_table
            current_section = m.group(1)
            cleaned_lines.append(line) #updates the section 
            continue 
        is_table_row = line.strip().startswith('|') #boolean: true if the lines starts with |

        if is_table_row: 
            in_table = True 
            table_lines.append(line)
        elif in_table: #if is_table_row = False but we are still inside a table 
            if not line.strip(): 
                next_has_pipe = False #if the line it's empty it still checks the next 3 lines to see if it's true
                for j in range(i + 1, min(i + 4, len(lines))):
                    if lines[j].strip().startswith('|'):
                        next_has_pipe = True 
                        break
                    if lines[j].strip() != "": #if it's text skip
                        break
                if next_has_pipe: #if there is a(empty) line save it 
                    table_lines.append(line)
                else: #it doesn't begin with | and it's not inside a table
                #otherwise the table is over, save the table an add it to cleaned_line
                    flush_table()
                    cleaned_lines.append(line)
            else: 
                table_lines.append(line)
        else: 
            cleaned_lines.append(line)
        
    flush_table()
    return "\n".join(cleaned_lines), saved_files


def process_tables_in_md(md_content, stem_name, output_folder):
    m = re.search(r'^## DIGITAL DIMENSIONS', md_content, re.MULTILINE)
    if m:
        header = md_content[:m.end()] #the only header is the title
        body = md_content[m.end():]
    else:
        header = ""
        body = md_content

    cleaned_body, saved_files = _process_lines(body, stem_name, output_folder)
    return header + cleaned_body, saved_files

#____INJECT TABLE REFS INTO MARKDOWN_____

def inject_table_refs(digital_content, csv_files): 
    #groups the csv by section: _s41_t1.csv → sezione "1"
    section_csvs = {}
    for csv_name in csv_files:
        m = re.search(r'_s4(\w+)_t\d+\.csv$', csv_name)
        if m:
            sec = m.group(1)
            section_csvs.setdefault(sec, []).append(csv_name)

    def replacer(match):
        sec_num = match.group(1)
        heading = match.group(0)
        csvs = section_csvs.get(sec_num, [])
        if csvs: #if it's in the dictionary substitute the table with the link 
            links = "\n".join(f"- [{f}](extracted_tables/{f})" for f in csvs)
            return f"{heading}\n> **Tables:**\n{links}\n"
        return heading

    result = re.sub(
        r'^#{1,3}\s+[_*]*4\.(\d+)[\.\s].*$',
        replacer,
        digital_content,
        flags=re.MULTILINE
    )
    return result

#____MAIN EXTRACTION FUNCTION_____

def extract_content(pdf_path, doc):
    try:
       md_text = pymupdf4llm.to_markdown(pdf_path) 
    except Exception as e:
        return (f"Error extracting text from PDF: {e}")
    
    #_____METADATA EXTRACTION_____
    first_part = md_text[:4000] #it seems to be 4000 characters are enough to scan the cover avoiding to scan the whole document
    
    id_match = re.search(r"(COM\s*\(\d{4}\)\s*\d+(?:\s*final)?)", first_part, re.IGNORECASE)
    doc_id = clean_metadata(id_match.group(1)) if id_match else "ID not found"

    date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", first_part)
    doc_date = clean_metadata(date_match.group(1)) if date_match else "Date not found"

    def extract_title(md_text): 
        #Three cases: 
        #1. The title is clearly state in the 1.1 Finantial statement 
        #2. Pattern on the cover: "Proposal for a" followed by a clear ## md 
        #3. Section with no ## and 

        #1. first case 
        m = re.search(
            r"##\s*\**1\.1\.\s*Title\s*of\s*the\s*proposal[^\n]*\**\n+(.*?)(?=##\s*\**1\.2\.)",
            md_text, re.DOTALL | re.IGNORECASE
        )

        if m:
            t = clean_metadata(m.group(1))
            if len(t) >= 15: 
                return t 
        
        #2.Second case, after the "Proposal for a" pymupdf4llm creates one or more ## heading 
        #or a combination of ## and ** 
        m = re.search(r"Proposal\s+for\s+(?:a\s+)?\n+", md_text, re.IGNORECASE)
        if m: 
            after = md_text[m.end():]
            #This collects all the headings and the bold paragraphs 
            parts = []
            for hm in re.finditer(
            r"^(?:#{1,3}\s+)?\*\*(.+?)\*\*\s*$",
            after, re.MULTILINE
            ):
                line = hm.group(1).strip()
                #stop on the footer (EN) or on the (Text with EEA) 
                if re.match(r"^EN$", line, re.IGNORECASE):
                    break
                if re.match(r"\(Text\s+with|EXPLANATORY|\d+\.\s+CONTEXT", line, re.IGNORECASE):
                    break
                if not line: 
                    continue 
                parts.append(line)
            if parts: 
                t = " ".join(parts)
                if len(t) >= 15: 
                    return t 
        
        #3. Third case fallback on the 1.1. text part without any ## or ** 
        m = re.search(
        r"1\.1\.\s*Title\s*of\s*the\s*proposal[^\n]*\n+(.*?)(?=1\.2\.)",
        md_text, re.DOTALL | re.IGNORECASE
        )
        if m:
            t = clean_metadata(m.group(1))
            if len(t) >= 15:
                return t
        
        return "Title not found"

    title = extract_title(first_part)

    policy_pattern = r"##\s*\**1\.2\.\s*Policy\s*area[^\n]*\**\n+(.*?)(?=##\s*\**1\.3\.)"
    policy_matches = re.findall(policy_pattern, md_text, re.DOTALL | re.IGNORECASE)
    policy_areas = clean_metadata(policy_matches[-1]) if policy_matches else "Policy areas not found"  

    digital_pattern = r"##\s*\**4\.\s*DIGITAL\s*DIMENSIONS[^\n]*\**\n+(.*?)(?=##\s*\**5\.|##\s*\**ANNEX|$)"
    digital_matches = re.findall(digital_pattern, md_text, re.DOTALL | re.IGNORECASE)
    digital_raw = digital_matches[-1] if digital_matches else ""
    digital_content = clean_text(digital_raw) if digital_raw else "Section 'DIGITAL DIMENSIONS' not found."

    final_output = f"""---
id_documento: "{doc_id}"
data: "{doc_date}"
policy_areas: "{policy_areas}"
---

# {title}

## DIGITAL DIMENSIONS

{digital_content}
"""

    return doc_id, final_output

#____EXECUTION_____

def process_folder(input_folder, output_folder):
    input_folder = Path(input_folder)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    tables_folder = output_folder / "extracted_tables"
    tables_folder.mkdir(exist_ok=True)

    pdf_files = list(input_folder.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in {input_folder}")
        return
    
    print(f"Found {len(pdf_files)} PDF files in {input_folder}. Processing...")

    for pdf_file in pdf_files:
        doc = pymupdf.open(pdf_file)
        print(f"Processing {pdf_file.name}...")
        result = extract_content(pdf_file, doc)
        doc.close()

        if isinstance(result, str):
            print(f"  [!] ERRORE: {result}")
            continue

        doc_id, content = result #divides the result in two components 

        if doc_id == "ID not found":
            print(f"  [!] ID non trovato in {pdf_file.name}, skip.")
            continue 

        safe_filename = doc_id.replace(" ", "_").replace("(", "").replace(")", "").replace("/", "-")
        if not safe_filename:
            safe_filename = pdf_file.stem 

        content, csv_files = process_tables_in_md(content, safe_filename, tables_folder) 

        if csv_files:
            print(f"  Extracted {len(csv_files)} table(s) from {pdf_file.name}")
            content = inject_table_refs(content, csv_files)

        output_file = output_folder / f"{safe_filename}.md"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(content) 

        print(f"  Successfully processed {pdf_file.name} -> {output_file.name}") 

original_folder = "COM-proposal-LFDS"
output_folder = "COM-proposals_extracted"

process_folder(original_folder, output_folder)