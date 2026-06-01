import subprocess
import sqlite3

# VULNERABILITY 1: Command injection
def run_command(user_input):
    result = subprocess.run(f'echo {user_input}', shell=True, capture_output=True)
    return result.stdout

# VULNERABILITY 2: SQL injection  
def get_user(username):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute(f'SELECT * FROM users WHERE username = "{username}"')
    return cursor.fetchall()

# VULNERABILITY 3: Hardcoded AWS secret
AWS_SECRET_KEY = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
