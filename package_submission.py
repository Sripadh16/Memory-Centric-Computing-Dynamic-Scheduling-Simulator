"""
Packaging script for project submission.
Creates:
1. 'submittion/' folder containing all source code, experiments, dashboard, tests, scripts, and documentation.
2. 'submittion.zip' archive ready for academic submission.
Excludes: .git, __pycache__, .pytest_cache, temporary files.
"""

import os
import shutil
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SUBMISSION_DIR = os.path.join(PROJECT_ROOT, "CA assignment")
ZIP_FILE_PATH = os.path.join(PROJECT_ROOT, "CA assignment.zip")

# Elements to include
ITEMS_TO_COPY = [
    ("simulator", True),
    ("dashboard", True),
    ("experiments", True),
    ("tests", True),
    ("run_experiments.py", False),
    ("run_dashboard.py", False),
    ("generate_documentation.py", False),
    ("MemCentric_Sim_Architecture_Report.docx", False),
    ("README.md", False),
    ("ARCHITECTURE_REPORT.md", False),
    (".gitignore", False),
]

def clean_pycache(directory):
    """Recursively delete __pycache__ directories."""
    for root, dirs, files in os.walk(directory, topdown=False):
        for d in dirs:
            if d == "__pycache__" or d == ".pytest_cache":
                full_path = os.path.join(root, d)
                shutil.rmtree(full_path, ignore_errors=True)

def package():
    print("=" * 60)
    print("Packaging MemCentric-Sim for Submission")
    print("=" * 60)

    # 1. Reset / create submittion folder
    if os.path.exists(SUBMISSION_DIR):
        shutil.rmtree(SUBMISSION_DIR)
    os.makedirs(SUBMISSION_DIR, exist_ok=True)
    print(f"Created folder: {SUBMISSION_DIR}")

    # 2. Copy items
    for item_name, is_dir in ITEMS_TO_COPY:
        src = os.path.join(PROJECT_ROOT, item_name)
        dst = os.path.join(SUBMISSION_DIR, item_name)
        if not os.path.exists(src):
            print(f"Warning: {src} does not exist, skipping.")
            continue
        if is_dir:
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git*'))
            clean_pycache(dst)
            print(f"Copied directory: {item_name}/ -> submittion/{item_name}/")
        else:
            shutil.copy2(src, dst)
            print(f"Copied file: {item_name} -> submittion/{item_name}")

    # 3. Create submittion.zip
    if os.path.exists(ZIP_FILE_PATH):
        os.remove(ZIP_FILE_PATH)

    print(f"\nCreating ZIP archive: {ZIP_FILE_PATH}...")
    with zipfile.ZipFile(ZIP_FILE_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SUBMISSION_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, SUBMISSION_DIR)
                # Store under root of zip or under submittion/
                archive_name = os.path.join("submittion", rel_path)
                zf.write(file_path, archive_name)
    
    zip_size_mb = os.path.getsize(ZIP_FILE_PATH) / (1024 * 1024)
    print(f"Successfully generated {ZIP_FILE_PATH} ({zip_size_mb:.2f} MB)")

    # Also list contents summary
    print("\nSubmission Package Summary:")
    file_count = 0
    total_size = 0
    for root, dirs, files in os.walk(SUBMISSION_DIR):
        for f in files:
            file_count += 1
            total_size += os.path.getsize(os.path.join(root, f))
    print(f"Total files in submission: {file_count}")
    print(f"Uncompressed size: {total_size / (1024 * 1024):.2f} MB")
    print("=" * 60)

if __name__ == "__main__":
    package()
