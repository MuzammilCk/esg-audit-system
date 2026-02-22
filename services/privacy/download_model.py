
import subprocess
import sys

def download_model():
    subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_lg"])

if __name__ == "__main__":
    download_model()
