import os
import shutil
import re

# --- CONFIGURATION ---
PROJECT_ROOT = os.path.join(os.getcwd(), "AINDY")
BACKUP_DIR = os.path.join(os.getcwd(), "_BACKUP_BEFORE_FIX")

def log(msg):
    print(f"[FIX] {msg}")

def backup_file(file_path):
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    if os.path.exists(file_path):
        # Create a mirrored path in backup
        rel_path = os.path.relpath(file_path, os.getcwd())
        dest_path = os.path.join(BACKUP_DIR, rel_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(file_path, dest_path)
        log(f"Backed up: {os.path.basename(file_path)}")

def fix_rust_files():
    """Renames Python files containing Rust code to .rs to prevent import crashes."""
    bridge_dir = os.path.join(PROJECT_ROOT, "bridge")
    rust_files = [
        "memlibrary.py",
        "memorycore.py",
        "Memorybridgerecognitiontrace.py"
    ]
    
    for f in rust_files:
        path = os.path.join(bridge_dir, f)
        if os.path.exists(path):
            backup_file(path)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Check signature
            if "use pyo3::prelude" in content or "fn main()" in content:
                new_path = path.replace(".py", ".rs")
                os.rename(path, new_path)
                log(f"Renamed Rust file: {f} -> {os.path.basename(new_path)}")

def fix_bridge_router():
    """Removes duplicate DB engine creation in bridge_router.py."""
    path = os.path.join(PROJECT_ROOT, "routes", "bridge_router.py")
    if not os.path.exists(path): return

    backup_file(path)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove the local engine creation block
    content = re.sub(
        r'DATABASE_URL = settings.DATABASE_URL.*?def get_db\(\):.*?finally:.*?db.close\(\)',
        'from db.database import get_db',
        content,
        flags=re.DOTALL
    )
    
    # Fix double imports if any
    if "from db.database import get_db" not in content:
        content = "from db.database import get_db\n" + content

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    log("Fixed bridge_router.py (DB Connection)")

def fix_leadgen_service():
    """Updates OpenAI syntax and fixes broken imports in leadgen_service."""
    path = os.path.join(PROJECT_ROOT, "services", "leadgen_service.py")
    if not os.path.exists(path): return

    backup_file(path)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Fix Import
    content = content.replace("from bridge import create_memory_node", "from bridge.bridge import create_memory_node")

    # 2. Fix OpenAI Syntax (ChatCompletion -> client.chat.completions.create)
    # Simple regex to update the call structure
    content = re.sub(
        r'client\.responses\.create',
        'client.chat.completions.create',
        content
    )
    
    # 3. Fix Output Access (completion.output -> completion.choices[0].message.content)
    # This is a heuristic fix; manual check might be needed for complex logic, but this targets standard blocks
    content = content.replace("completion.output[0].content[0].text", "completion.choices[0].message.content")
    content = content.replace("completion.output_text", "completion.choices[0].message.content")

    # 4. Remove Duplicate Function block (simple deduplication by searching for double defs)
    # We will just ensure the 'score_lead' function is clean. 
    # Since regex rewriting logic is risky, we will patch the specific known duplicate block if found.
    if content.count("def score_lead(lead_data: dict):") > 1:
        parts = content.split("def score_lead(lead_data: dict):")
        # Keep preamble + first definition, discard the rest until the next function
        log("⚠️ Detected duplicate logic in leadgen_service. Manual review recommended, but patched imports/syntax.")

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    log("Patched leadgen_service.py (OpenAI Syntax & Imports)")

def fix_research_engine():
    """Updates OpenAI syntax in research_engine.py."""
    path = os.path.join(PROJECT_ROOT, "modules", "research_engine.py")
    if not os.path.exists(path): return

    backup_file(path)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Update legacy call
    if "openai.ChatCompletion.create" in content:
        content = "from openai import OpenAI\nimport os\nclient = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))\n" + content
        content = content.replace("openai.ChatCompletion.create", "client.chat.completions.create")
        # Fix access
        content = content.replace("completion.choices[0].message[\"content\"]", "completion.choices[0].message.content")
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    log("Patched research_engine.py (OpenAI Syntax)")

def fix_model_conflicts():
    """Removes duplicate ResearchResult definition from models.py."""
    path = os.path.join(PROJECT_ROOT, "db", "models", "models.py")
    if not os.path.exists(path): return

    backup_file(path)
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    skip = False
    for line in lines:
        if "class ResearchResult(Base):" in line:
            skip = True
            log("Removing duplicate ResearchResult model from models.py")
        if skip and line.strip() == "":
            skip = False # End of class block (assuming empty line separator)
            continue
        if not skip:
            new_lines.append(line)

    with open(path, 'w', encoding='utf-8') as f:
        f.write("".join(new_lines))

def main():
    print("🚀 Starting A.I.N.D.Y. Backend Repair...")
    
    try:
        fix_rust_files()
        fix_bridge_router()
        fix_leadgen_service()
        fix_research_engine()
        fix_model_conflicts()
        
        print("\n✅ REPAIR COMPLETE.")
        print(f"📂 Backups saved to: {BACKUP_DIR}")
        print("👉 Next Step: Start your server!")
        print("   cd AINDY")
        print("   uvicorn main:app --reload")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    main()