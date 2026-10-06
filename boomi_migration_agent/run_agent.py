import os
import sys
import subprocess
from dotenv import load_dotenv

def main():
    # Load environment variables from the workspace root .env
    load_dotenv()
    
    # Propagate GEMINI_API_KEY to GOOGLE_API_KEY if needed by ADK
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        os.environ["GOOGLE_API_KEY"] = gemini_key
        
    # Verify we have the required keys
    if not os.getenv("GOOGLE_API_KEY"):
        print("Warning: GOOGLE_API_KEY / GEMINI_API_KEY is not set in your .env or environment.")
        
    # Get the directory of this run script
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Parse query arguments
    query = "Scan legacy database components and generate an audit report."
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        
    print(f"Starting Boomi Migration Agent with query: '{query}'")
    
    # Build command to execute Google ADK CLI run
    cmd = [sys.executable, "-m", "google.adk.cli", "run", agent_dir, query]
    
    # Run in subprocess with current environment variables
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
