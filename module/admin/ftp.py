"""Admin FTP management module with optimized performance"""
import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache, wraps
from typing import Dict, List, Tuple

import aiofiles
from flask import Flask, flash, redirect, render_template, session

# Import moved to top level
from module.ftp import delete_ftp_account

app = Flask(__name__)
app.config.from_envvar("OPENPANEL_CONFIG", silent=True)

# Performance optimizations
MAX_WORKERS = 4
EXECUTOR = ThreadPoolExecutor(max_workers=MAX_WORKERS)
FTP_USERS_DIR = "/etc/openpanel/ftp/users"


@lru_cache(maxsize=128)
def admin_required(f):
    """Optimized admin authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated_function


async def read_user_list(filepath: str) -> List[List[str]]:
    """Asynchronously read user list file"""
    try:
        async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
            content = await f.read()
            return [
                line.strip().split('|')
                for line in content.splitlines()
                if line.strip()
            ]
    except FileNotFoundError:
        logging.info("User list file not found: %s", filepath)
        return []
    except OSError as e:
        logging.error("OS error reading user list %s: %s", filepath, e)
        return []
    except (UnicodeDecodeError, ValueError) as e:
        logging.exception("Data error reading user list %s: %s", filepath, e)
        return []


async def get_all_ftp_accounts() -> List[Dict]:
    """List all FTP accounts across users with optimized async IO"""
    accounts = []
    if not os.path.exists(FTP_USERS_DIR):
        logging.info("FTP users directory not found: %s", FTP_USERS_DIR)
        return []

    try:
        user_dirs = [d for d in os.scandir(FTP_USERS_DIR) if d.is_dir()]
    except OSError as e:
        logging.error("Error scanning FTP users directory %s: %s", FTP_USERS_DIR, e)
        return []

    tasks = []
    for user_dir in user_dirs:
        user_list_path = os.path.join(user_dir.path, "users.list")
        if os.path.isfile(user_list_path):
            tasks.append(read_user_list(user_list_path))
        else:
            logging.debug("No users.list found in %s", user_dir.path)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, user_accounts_or_exc in enumerate(results):
        user_dir_name = user_dirs[i].name
        if isinstance(user_accounts_or_exc, Exception):
            logging.error(
                "Failed to read accounts for user %s: %s",
                user_dir_name,
                user_accounts_or_exc
            )
            continue

        user_accounts = user_accounts_or_exc
        for parts in user_accounts:
            if len(parts) >= 1:
                username = parts[0]
                directory = parts[2] if len(parts) > 2 else f"/ftp/{username}"
                accounts.append({
                    "owner": user_dir_name,
                    "username": username,
                    "directory": directory
                })
            else:
                logging.warning(
                    "Skipping malformed line in user list for %s", user_dir_name
                )

    return accounts


async def delete_user_ftp_accounts(username: str) -> Tuple[bool, str]:
    """Delete all FTP accounts for a user with optimized IO"""
    user_dir = os.path.join(FTP_USERS_DIR, username)

    try:
        if not os.path.exists(user_dir):
            return True, "No FTP accounts directory found for user."

        user_list_file = os.path.join(user_dir, "users.list")
        if os.path.exists(user_list_file):
            try:
                os.unlink(user_list_file)
                logging.info("Deleted user list file: %s", user_list_file)
            except OSError as e:
                logging.error("Error deleting user list file %s: %s", user_list_file, e)

        try:
            os.rmdir(user_dir)
            logging.info("Removed user directory: %s", user_dir)
            return True, "FTP accounts and directory deleted successfully."
        except OSError as e:
            logging.error("Error removing user directory %s: %s", user_dir, e)
            return False, f"Failed to remove user directory: {e}. It might not be empty or permissions are wrong."

    except (PermissionError, FileNotFoundError) as e:
        logging.exception("Error deleting FTP accounts for %s:", username)
        return False, f"Error while deleting FTP accounts: {str(e)}"


@app.route("/admin/ftp", methods=["GET"])
@admin_required
def admin_ftp_dashboard():
    """Admin FTP dashboard with async data loading"""
    try:
        accounts = asyncio.run(get_all_ftp_accounts())
        return render_template(
            "admin/ftp/dashboard.html",
            accounts=accounts,
            total_accounts=len(accounts)
        )
    except (asyncio.CancelledError, OSError, ValueError) as e:
        logging.exception("Error loading admin FTP dashboard:")
        flash(f"Failed to load FTP accounts: {str(e)}", "error")
        return redirect("/admin")


@app.route("/admin/ftp/delete/<owner>/<username>", methods=["POST"])
@admin_required
def admin_ftp_delete_account(owner: str, username: str):
    """Delete FTP account as admin with optimized error handling"""
    if not owner or not username:
        flash("Invalid owner or username provided.", "error")
        return redirect("/admin/ftp")

    try:
        success, message = delete_ftp_account(owner, username)
        if success:
            flash(f"FTP account '{username}' for owner '{owner}' deleted successfully. {message}", "success")
        else:
            flash(f"Error deleting FTP account '{username}' for '{owner}': {message}", "error")
    except (OSError, PermissionError, FileNotFoundError) as e:
        logging.exception("System error during admin FTP account deletion:")
        flash(f"A system error occurred while deleting the account: {str(e)}", "error")

    return redirect("/admin/ftp")
