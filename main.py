import subprocess
import os
from bot import run_bot

LOG_FILE = "agent_reasoning.log"

def open_log_viewer():
    """Open a separate terminal window to view the agent reasoning log"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(script_dir, LOG_FILE)

    # Create empty log file if it doesn't exist
    if not os.path.exists(log_path):
        open(log_path, 'w').close()

    # Open a new PowerShell window that tails the log
    # Use escaped quotes for paths with spaces
    escaped_path = log_path.replace("'", "''")

    subprocess.Popen(
        f'start powershell -NoExit -Command "Get-Content \'{escaped_path}\' -Wait -Tail 50"',
        shell=True
    )
    print(f"📋 Opened log viewer for: {LOG_FILE}")


if __name__ == '__main__':
    print("🚀 Starting Personal Assistant Bot...")
    print("=" * 50)

    # Open log viewer in separate terminal
    open_log_viewer()

    # Run the bot
    run_bot()
