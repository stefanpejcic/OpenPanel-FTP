"""
ftp.py

https://git.devnet.rs/stefan/2083/-/blob/8bde157a32c9350d58edef652cb8b1265fbd9721/modules/ftp.py

"""
from flask_babel import Babel, _ # https://python-babel.github.io/flask-babel/
from flask import Flask, g, session, redirect, request, render_template, jsonify, flash
import re
import os
import mysql.connector
from functools import wraps
import subprocess
from subprocess import getoutput, check_output
import shlex
import importlib
import random
import string
import json
from pathlib import Path

#openadmin
from app import app
from app import login_required_route, log_user_action, query_username_by_id, get_container_port, get_server_ip
from modules.core.webserver import get_config_file_path, get_php_version_preference
from modules.core.config import php_version_for_phpmyadmin_in_containers

# Constants
MAX_FTP_ACCOUNTS_PER_USER = 5  # Default limit
DEFAULT_QUOTA_SOFT = 1024  # 1GB in MB (UI only, not enforced)
DEFAULT_QUOTA_HARD = 2048  # 2GB in MB (UI only, not enforced)
FTP_USERS_DIR = "/etc/openpanel/ftp/users"

# Create directories if they don't exist
os.makedirs(FTP_USERS_DIR, exist_ok=True)

def get_max_ftp_accounts(username):
    """Get the maximum number of FTP accounts allowed for a user"""
    # This could be fetched from a database or config file
    # For now, use the default constant
    return MAX_FTP_ACCOUNTS_PER_USER

def count_user_ftp_accounts(username):
    """Count the number of FTP accounts owned by a user"""
    user_dir = os.path.join(FTP_USERS_DIR, username)
    if not os.path.exists(user_dir):
        return 0

    user_list_file = os.path.join(user_dir, "users.list")
    if not os.path.exists(user_list_file):
        return 0

    with open(user_list_file, "r") as f:
        account_count = sum(1 for line in f if line.strip())

    return account_count

def can_create_ftp_account(username):
    """Check if a user can create more FTP accounts"""
    current_count = count_user_ftp_accounts(username)
    max_accounts = get_max_ftp_accounts(username)
    return current_count < max_accounts

def validate_ftp_path(username, folder_path):
    """Validate that the FTP path is valid for this user"""
    # Ensure path starts with /home/{username}
    user_home = f"/home/{username}"
    if not folder_path.startswith(user_home):
        return False, f"Path must be within your home directory ({user_home})"

    # Check if path exists
    if not os.path.exists(folder_path):
        try:
            os.makedirs(folder_path, exist_ok=True)
        except:
            return False, "Could not create directory"

    return True, ""

def create_ftp_account(openpanel_username, ftp_username, password, folder, quota_soft=DEFAULT_QUOTA_SOFT, quota_hard=DEFAULT_QUOTA_HARD):
    """Create a new FTP account for a user"""
    if not can_create_ftp_account(openpanel_username):
        return False, f"Maximum FTP accounts ({get_max_ftp_accounts(openpanel_username)}) reached"

    valid, message = validate_ftp_path(openpanel_username, folder)
    if not valid:
        return False, message

    # Prepare user directory
    user_dir = os.path.join(FTP_USERS_DIR, openpanel_username)
    os.makedirs(user_dir, exist_ok=True)

    # Append to users.list
    user_list_file = os.path.join(user_dir, "users.list")
    with open(user_list_file, "a") as f:
        f.write(f"{ftp_username}|{password}|{folder}\n")

    # Restart FTP service to apply changes
    try:
        subprocess.run(["docker", "restart", "openadmin_ftp"], check=True)
    except subprocess.SubprocessError:
        # Don't fail if Docker container isn't running
        pass

    return True, "FTP account created successfully"

def delete_ftp_account(openpanel_username, ftp_username):
    """Delete an FTP account"""
    user_list_file = os.path.join(FTP_USERS_DIR, openpanel_username, "users.list")

    if not os.path.exists(user_list_file):
        return False, "User list file not found"

    # Read existing accounts
    with open(user_list_file, "r") as f:
        lines = f.readlines()

    # Filter out the account to delete
    new_lines = []
    found = False
    for line in lines:
        if line.strip() and line.split('|', 2)[0] == ftp_username:
            found = True
        else:
            new_lines.append(line)

    if not found:
        return False, "FTP account not found"

    # Write back filtered accounts
    with open(user_list_file, "w") as f:
        f.writelines(new_lines)

    # Restart FTP service to apply changes
    try:
        subprocess.run(["docker", "restart", "openadmin_ftp"], check=True)
    except subprocess.SubprocessError:
        # Don't fail if Docker container isn't running
        pass

    return True, "FTP account deleted successfully"

def list_ftp_accounts(openpanel_username):
    """List all FTP accounts for a user"""
    user_list_file = os.path.join(FTP_USERS_DIR, openpanel_username, "users.list")

    if not os.path.exists(user_list_file):
        return []

    accounts = []
    with open(user_list_file, "r") as f:
        for line in f:
            if line.strip():
                parts = line.strip().split('|', 2)
                account = {
                    "username": parts[0],
                    "directory": parts[2] if len(parts) > 2 else f"/ftp/{parts[0]}"
                }
                accounts.append(account)

    return accounts

def update_ftp_account(openpanel_username, ftp_username, new_password=None, new_folder=None):
    """Update an existing FTP account"""
    user_list_file = os.path.join(FTP_USERS_DIR, openpanel_username, "users.list")

    if not os.path.exists(user_list_file):
        return False, "User list file not found"

    # Read existing accounts
    with open(user_list_file, "r") as f:
        lines = f.readlines()

    # Update the specified account
    new_lines = []
    found = False
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue

        parts = line.strip().split('|', 2)
        if parts[0] == ftp_username:
            found = True
            # Keep original values if new ones not provided
            password = new_password if new_password is not None else parts[1]
            folder = new_folder if new_folder is not None else (parts[2] if len(parts) > 2 else f"/ftp/{ftp_username}")

            # Validate folder if changed
            if new_folder is not None:
                valid, message = validate_ftp_path(openpanel_username, new_folder)
                if not valid:
                    return False, message

            new_lines.append(f"{ftp_username}|{password}|{folder}\n")
        else:
            new_lines.append(line)

    if not found:
        return False, "FTP account not found"

    # Write back updated accounts
    with open(user_list_file, "w") as f:
        f.writelines(new_lines)

    # Restart FTP service to apply changes
    try:
        subprocess.run(["docker", "restart", "openadmin_ftp"], check=True)
    except subprocess.SubprocessError:
        # Don't fail if Docker container isn't running
        pass

    return True, "FTP account updated successfully"

# OpenPanel/OpenAdmin Flask routes

@app.route('/ftp', methods=['GET'])
@login_required_route
def ftp_dashboard():
    """FTP Dashboard"""
    username = query_username_by_id(session.get('user_id'))
    accounts = list_ftp_accounts(username)

    can_create = can_create_ftp_account(username)
    account_limit = get_max_ftp_accounts(username)
    current_count = count_user_ftp_accounts(username)

    return render_template('ftp/dashboard.html',
                          accounts=accounts,
                          can_create=can_create,
                          account_limit=account_limit,
                          current_count=current_count)

@app.route('/ftp/create', methods=['GET', 'POST'])
@login_required_route
def ftp_create_account():
    """Create FTP Account Form"""
    username = query_username_by_id(session.get('user_id'))

    if request.method == 'POST':
        ftp_username = request.form.get('ftp_username')
        password = request.form.get('password')
        folder = request.form.get('folder')

        success, message = create_ftp_account(username, ftp_username, password, folder)

        if success:
            flash("FTP account created successfully", "success")
            log_user_action(session.get('user_id'), f"Created FTP account: {ftp_username}")
            return redirect('/ftp')
        else:
            flash(f"Error creating FTP account: {message}", "error")

    # GET request or failed POST
    return render_template('ftp/create_account.html',
                          home_dir=f"/home/{username}",
                          can_create=can_create_ftp_account(username))

@app.route('/ftp/delete/<ftp_username>', methods=['POST'])
@login_required_route
def ftp_delete_account(ftp_username):
    """Delete FTP Account"""
    username = query_username_by_id(session.get('user_id'))

    success, message = delete_ftp_account(username, ftp_username)

    if success:
        log_user_action(session.get('user_id'), f"Deleted FTP account: {ftp_username}")
        flash("FTP account deleted successfully", "success")
    else:
        flash(f"Error deleting FTP account: {message}", "error")

    return redirect('/ftp')

@app.route('/ftp/edit/<ftp_username>', methods=['GET', 'POST'])
@login_required_route
def ftp_edit_account(ftp_username):
    """Edit FTP Account"""
    username = query_username_by_id(session.get('user_id'))

    if request.method == 'POST':
        new_password = request.form.get('password')
        new_folder = request.form.get('folder')

        success, message = update_ftp_account(username, ftp_username,
                                            new_password, new_folder)

        if success:
            log_user_action(session.get('user_id'), f"Updated FTP account: {ftp_username}")
            flash("FTP account updated successfully", "success")
            return redirect('/ftp')
        else:
            flash(f"Error updating FTP account: {message}", "error")

    # For GET request, load current account details
    accounts = list_ftp_accounts(username)
    account = next((a for a in accounts if a['username'] == ftp_username), None)

    if not account:
        flash("FTP account not found", "error")
        return redirect('/ftp')

    return render_template('ftp/edit_account.html',
                          account=account,
                          home_dir=f"/home/{username}")
