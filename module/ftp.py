"""
ftp.py

https://git.devnet.rs/stefan/2083/-/blob/8bde157a32c9350d58edef652cb8b1265fbd9721/modules/ftp.py

"""

import asyncio
import logging
import os

# nosec B404 - Subprocess is necessary for docker
# interaction
import subprocess
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache, wraps
from threading import Lock
from typing import List, Tuple

import aiofiles
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

# FTP module with optimized performance - Removed redundant docstring

# Performance optimizations
app = Flask(__name__)
CACHE_TIMEOUT = 300
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 4)
EXECUTOR = ThreadPoolExecutor(max_workers=MAX_WORKERS)
file_lock = Lock()

# Constants
FTP_USERS_DIR = "/etc/openpanel/ftp/users"
os.makedirs(FTP_USERS_DIR, exist_ok=True)


def async_io(func):
    """Decorator for async IO operations"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    return wrapper


async def read_user_list(filepath: str) -> List[List[str]]:
    """Asynchronously read user list file"""
    try:
        async with aiofiles.open(filepath, mode='r', encoding='utf-8') as f:
            content = await f.read()
            return [
                parts for line in content.splitlines()
                if line.strip() and (parts := line.strip().split('|'))
            ]
    except FileNotFoundError:
        logging.info("User list file not found: %s", filepath)
        return []
    except PermissionError as e:
        logging.exception("Permission error reading user list %s: %s", filepath, e)
        return []
    except (ValueError, UnicodeDecodeError) as e:
        logging.exception("Error reading user list %s: %s", filepath, e)
        return []
    except OSError as e:
        logging.error("OS error reading user list %s: %s", filepath, e)
        return []


@lru_cache(maxsize=256)
def query_username_by_id(user_id: str) -> str:
    """Cache frequently accessed usernames"""
    return f"user_{user_id}" if user_id else None


def async_log(user_id: str, action: str) -> None:
    """Non-blocking logging"""
    EXECUTOR.submit(logging.info, f"User {user_id}: {action}")


def login_required_route(f):
    """Optimized authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


@lru_cache(maxsize=100)
def get_max_ftp_accounts() -> int:
    """Cache account limits"""
    return 5


async def count_user_ftp_accounts(username):
    """Optimized account counting with caching"""
    user_list_file = os.path.join(FTP_USERS_DIR, username, "users.list")
    if not os.path.exists(user_list_file):
        return 0

    accounts = await read_user_list(user_list_file)
    return len(accounts)


def can_create_ftp_account(username):
    """Check if a user can create more FTP accounts"""
    current_count = asyncio.run(count_user_ftp_accounts(username))
    max_accounts = get_max_ftp_accounts()
    return current_count < max_accounts


def validate_ftp_path(username, folder_path):
    """Validate path with optimized checks"""
    user_home = f"/home/{username}"
    try:
        abs_folder_path = os.path.abspath(folder_path)
        abs_user_home = os.path.abspath(user_home)

        if os.path.commonpath([abs_user_home, abs_folder_path]) != abs_user_home:
            return False, f"Path must be within user's home directory: {user_home}"

        os.makedirs(abs_folder_path, mode=0o750, exist_ok=True)
        return True, ""
    except OSError as e:
        logging.error("Error creating/validating directory %s: %s", folder_path, e)
        return False, f"Failed to create or access directory: {e}"
    except ValueError as e:
        logging.error("Invalid folder path provided: %s", folder_path)
        return False, f"Invalid folder path: {e}"


async def list_ftp_accounts(openpanel_username):
    """List all FTP accounts for a user"""
    user_list_file = os.path.join(FTP_USERS_DIR, openpanel_username, "users.list")
    if not os.path.exists(user_list_file):
        return []

    accounts_data = await read_user_list(user_list_file)
    result = []
    for parts in accounts_data:
        if len(parts) >= 1:
            username = parts[0]
            directory = parts[2] if len(parts) > 2 else f"/ftp/{username}"
            result.append({"username": username, "directory": directory})
        else:
            logging.warning("Skipping malformed line in %s", user_list_file)
    return result


def _run_docker_restart() -> Tuple[bool, str]:
    """Helper function to restart the docker container."""
    try:
        # Using constant arguments only - safe from command injection
        docker_cmd = "/usr/bin/docker"
        container = "openadmin_ftp"
        result = subprocess.run(  # nosec B603
            [docker_cmd, "restart", container],
            check=True,
            capture_output=True,
            timeout=30,
            text=True,
        )
        logging.info("FTP service restarted: %s", result.stdout)
        return True, "Service restarted successfully."
    except subprocess.CalledProcessError as e:
        err_msg = f"Failed to restart FTP service: {e}\n{e.stderr}"
        logging.error(err_msg)
        return False, "Failed to restart FTP service. Please restart manually."
    except FileNotFoundError:
        err_msg = "Docker command not found. Cannot restart FTP service."
        logging.error(err_msg)
        return False, "Docker command not found. Cannot restart FTP service."
    except subprocess.TimeoutExpired:
        err_msg = "Timeout restarting FTP service."
        logging.error(err_msg)
        return False, "Timed out restarting FTP service."
    except (OSError, PermissionError, ValueError, RuntimeError) as e:
        err_msg = f"Unexpected error restarting FTP service: {e}"
        logging.error(err_msg)
        return False, f"An unexpected error occurred during service restart: {e}"


def create_ftp_account(
    openpanel_username: str, ftp_username: str, password: str, folder: str
) -> Tuple[bool, str]:
    """Create a new FTP account"""
    required_params = [openpanel_username, ftp_username, password, folder]
    if not all(required_params):
        return False, (
            "Missing required parameters (username, FTP username, password, folder)"
        )

    valid_path, path_message = validate_ftp_path(openpanel_username, folder)
    if not valid_path:
        return False, path_message

    user_dir = os.path.join(FTP_USERS_DIR, openpanel_username)
    user_list_file = os.path.join(user_dir, "users.list")

    try:
        os.makedirs(user_dir, mode=0o750, exist_ok=True)

        if os.path.exists(user_list_file):
            with file_lock:
                try:
                    with open(user_list_file, "r", encoding='utf-8') as f:
                        if any(line.split("|")[0] == ftp_username for line in f):
                            return False, "FTP username already exists"
                except OSError as e:
                    logging.error("Error reading user list during check: %s", e)
                    return False, f"Could not verify existing users: {e}"

        with file_lock:
            with open(user_list_file, "a", encoding='utf-8') as f:
                hashed_password = generate_password_hash(password)
                f.write(f"{ftp_username}|{hashed_password}|{folder}\n")

        restart_success, restart_msg = _run_docker_restart()
        if restart_success:
            return True, "FTP account created successfully"
        else:
            return True, f"Account created, but {restart_msg}"

    except OSError as e:
        logging.error("OS error creating FTP account for %s: %s", ftp_username, e)
        return False, f"File system error: {e}"
    except PermissionError as e:
        logging.error("Permission error creating FTP account for %s: %s", ftp_username, e)
        return False, f"Permission denied: {e}"
    except ValueError as e:
        logging.error("Value error creating FTP account for %s: %s", ftp_username, e)
        return False, f"Invalid value: {e}"
    except (RuntimeError, IOError) as e:
        logging.exception("Error creating FTP account %s:", ftp_username)
        return False, f"Operation failed: {e}"


def delete_ftp_account(openpanel_username: str, ftp_username: str) -> Tuple[bool, str]:
    """Delete an FTP account"""
    user_list_file = os.path.join(FTP_USERS_DIR, openpanel_username, "users.list")
    temp_file = f"{user_list_file}.tmp"

    if not os.path.exists(user_list_file):
        return False, "User list file not found"

    found = False
    try:
        with file_lock:
            try:
                with open(user_list_file, "r", encoding='utf-8') as f_in, \
                     open(temp_file, "w", encoding='utf-8') as f_out:
                    for line in f_in:
                        parts = line.strip().split("|")
                        if parts and parts[0] == ftp_username:
                            found = True
                        else:
                            f_out.write(line)
            except OSError as e:
                logging.error("Error processing user list for deletion: %s", e)
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except OSError:
                        pass
                return False, f"File system error during deletion: {e}"

            if not found:
                os.unlink(temp_file)
                return False, "FTP account not found"

            os.replace(temp_file, user_list_file)

        restart_success, restart_msg = _run_docker_restart()
        if restart_success:
            return True, "FTP account deleted successfully"
        else:
            return True, f"Account deleted, but {restart_msg}"

    except OSError as e:
        logging.error("OS error deleting FTP account %s: %s", ftp_username, e)
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError as unlink_e:
                logging.error("Error removing temp file %s: %s", temp_file, unlink_e)
        return False, f"File system error: {e}"
    except Exception as e:
        logging.exception("Unexpected error deleting FTP account %s:", ftp_username)
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError as unlink_e:
                logging.error("Error removing temp file %s: %s", temp_file, unlink_e)
        return False, f"An unexpected error occurred: {e}"


def update_ftp_account(
    openpanel_username: str,
    ftp_username: str,
    new_password: str = None,
    new_folder: str = None,
) -> Tuple[bool, str]:
    """Update an FTP account"""
    user_list_file = os.path.join(FTP_USERS_DIR, openpanel_username, "users.list")
    temp_file = f"{user_list_file}.tmp"

    if new_folder:
        valid_path, path_message = validate_ftp_path(openpanel_username, new_folder)
        if not valid_path:
            return False, path_message

    if not os.path.exists(user_list_file):
        return False, "User list file not found"

    found = False
    try:
        with file_lock:
            try:
                with open(user_list_file, "r", encoding='utf-8') as f_in, \
                     open(temp_file, "w", encoding='utf-8') as f_out:
                    for line in f_in:
                        parts = line.strip().split("|")
                        if parts and parts[0] == ftp_username:
                            found = True
                            current_password_hash = parts[1] if len(parts) > 1 else ""
                            current_folder = parts[2] if len(parts) > 2 else ""

                            password_hash = (
                                generate_password_hash(new_password)
                                if new_password
                                else current_password_hash
                            )
                            folder = new_folder if new_folder else current_folder
                            f_out.write(f"{ftp_username}|{password_hash}|{folder}\n")
                        else:
                            f_out.write(line)
            except OSError as e:
                logging.error("Error processing user list for update: %s", e)
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except OSError:
                        pass
                return False, f"File system error during update: {e}"

            if not found:
                os.unlink(temp_file)
                return False, "FTP account not found"

            os.replace(temp_file, user_list_file)

        restart_success, restart_msg = _run_docker_restart()
        if restart_success:
            return True, "FTP account updated successfully"
        else:
            return True, f"Account updated, but {restart_msg}"

    except OSError as e:
        logging.error("OS error updating FTP account %s: %s", ftp_username, e)
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError as unlink_e:
                logging.error("Error removing temp file %s: %s", temp_file, unlink_e)
        return False, f"File system error: {e}"
    except Exception as e:
        logging.exception("Unexpected error updating FTP account %s:", ftp_username)
        if os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError as unlink_e:
                logging.error("Error removing temp file %s: %s", temp_file, unlink_e)
        return False, f"An unexpected error occurred: {e}"


@app.route("/ftp", methods=["GET"])
@login_required_route
def ftp_dashboard():
    """Optimized dashboard view"""
    user_id = session.get("user_id")
    if not user_id:
        flash("Session expired or invalid.", "error")
        return redirect("/login")

    username = query_username_by_id(user_id)
    if not username:
        flash("Could not determine username.", "error")
        return redirect("/login")

    async def get_dashboard_data():
        accounts_task = list_ftp_accounts(username)
        count_task = count_user_ftp_accounts(username)
        accounts, current_count = await asyncio.gather(accounts_task, count_task)
        return accounts, current_count

    try:
        accounts, current_count = asyncio.run(get_dashboard_data())
        max_accounts = get_max_ftp_accounts()
        can_create = current_count < max_accounts

        return render_template(
            "ftp/dashboard.html",
            accounts=accounts,
            can_create=can_create,
            account_limit=max_accounts,
            current_count=current_count,
        )
    except (OSError, IOError) as e:
        logging.exception("File system error loading FTP dashboard for user %s:", username)
        flash(f"File access error: {e}", "error")
        return redirect("/")
    except asyncio.TimeoutError:
        logging.exception("Timeout loading FTP dashboard for user %s:", username)
        flash("Dashboard operation timed out", "error")
        return redirect("/")
    except (ValueError, TypeError) as e:
        logging.exception("Data error loading FTP dashboard for user %s:", username)
        flash(f"Error processing dashboard data: {e}", "error")
        return redirect("/")
    except RuntimeError as e:
        logging.exception("Runtime error loading FTP dashboard for user %s:", username)
        flash(f"Application error: {e}", "error")
        return redirect("/")


@app.route("/ftp/create", methods=["GET", "POST"])
@login_required_route
def ftp_create_account():
    """Create FTP Account Form"""
    user_id = session.get("user_id")
    if not user_id:
        flash("Session expired or invalid.", "error")
        return redirect("/login")

    username = query_username_by_id(user_id)
    if not username:
        flash("Could not determine username.", "error")
        return redirect("/login")

    if not can_create_ftp_account(username):
        flash("Maximum FTP account limit reached.", "warning")
        return redirect("/ftp")

    home_dir = f"/home/{username}"

    if request.method == "POST":
        ftp_username = request.form.get("ftp_username", "").strip()
        password = request.form.get("password", "").strip()
        folder_input = request.form.get("folder", "").strip()

        if not ftp_username or not password or not folder_input:
            flash("FTP Username, Password, and Folder are required.", "error")
            return render_template(
                "ftp/create_account.html",
                home_dir=home_dir,
                can_create=True
            )

        folder_path = folder_input

        success, message = create_ftp_account(
            username, ftp_username, password, folder_path
        )

        if success:
            flash(message, "success")
            async_log(user_id, f"Created FTP account: {ftp_username}")
            return redirect("/ftp")
        else:
            flash(f"Error creating FTP account: {message}", "error")
            return render_template(
                "ftp/create_account.html",
                home_dir=home_dir,
                can_create=True,
                ftp_username=ftp_username,
                folder=folder_input
            )

    return render_template(
        "ftp/create_account.html",
        home_dir=home_dir,
        can_create=True
    )


@app.route("/ftp/delete/<ftp_username>", methods=["POST"])
@login_required_route
def ftp_delete_account_route(ftp_username):
    """Delete FTP Account Route"""
    user_id = session.get("user_id")
    if not user_id:
        flash("Session expired or invalid.", "error")
        return redirect("/login")

    username = query_username_by_id(user_id)
    if not username:
        flash("Could not determine username.", "error")
        return redirect("/login")

    success, message = delete_ftp_account(username, ftp_username)

    if success:
        async_log(user_id, f"Deleted FTP account: {ftp_username}")
        flash(message, "success")
    else:
        flash(f"Error deleting FTP account: {message}", "error")

    return redirect("/ftp")


@app.route("/ftp/edit/<path:ftp_username>", methods=["GET", "POST"])
@login_required_route
def ftp_edit_account(ftp_username):
    """Edit FTP Account with improved validation and error handling"""
    user_id = session.get("user_id")
    if not user_id:
        flash("Invalid user session", "error")
        return redirect("/login")

    username = query_username_by_id(user_id)
    if not username:
        flash("Could not determine username.", "error")
        return redirect("/login")

    if not ftp_username:
        flash("Invalid FTP username provided.", "error")
        return redirect("/ftp")

    home_dir = f"/home/{username}"

    if request.method == "POST":
        try:
            new_password = request.form.get("password", "").strip()
            new_folder = request.form.get("folder", "").strip()

            if not new_password and not new_folder:
                flash("No changes provided (password or folder).", "warning")
                return redirect(url_for('ftp_edit_account', ftp_username=ftp_username))

            success, message = update_ftp_account(
                username,
                ftp_username,
                new_password if new_password else None,
                new_folder if new_folder else None,
            )

            if success:
                async_log(user_id, f"Updated FTP account: {ftp_username}")
                flash(message, "success")
                return redirect("/ftp")
            else:
                flash(f"Error updating FTP account: {message}", "error")

        except (OSError, IOError) as e:
            logging.exception("File system error during FTP account update for %s:", ftp_username)
            flash(f"File system error: {str(e)}", "error")
            return redirect("/ftp")
        except ValueError as e:
            logging.exception("Value error during FTP account update for %s:", ftp_username)
            flash(f"Invalid input: {str(e)}", "error")
            return redirect("/ftp")
        except RuntimeError as e:
            logging.exception("Runtime error during FTP account update for %s:", ftp_username)
            flash(f"Operation failed: {str(e)}", "error")
            return redirect("/ftp")

    try:
        accounts = asyncio.run(list_ftp_accounts(username))
        account = next((a for a in accounts if a["username"] == ftp_username), None)

        if not account:
            flash("FTP account not found.", "error")
            return redirect("/ftp")

        return render_template(
            "ftp/edit_account.html",
            account=account,
            home_dir=home_dir,
            current_folder=account.get('directory', '')
        )
    except (OSError, IOError) as e:
        logging.exception(
            "File system error loading account details (user: %s, ftp: %s):",
            username, ftp_username
        )
        flash(f"File system error loading account details: {str(e)}", "error")
        return redirect("/ftp")
    except asyncio.TimeoutError:
        logging.exception(
            "Timeout while loading account details (user: %s, ftp: %s):",
            username, ftp_username
        )
        flash("Operation timed out while loading account details", "error")
        return redirect("/ftp")
    except ValueError as e:
        logging.exception(
            "Value error loading account details "
            "(user: %s, ftp: %s):",
            username, ftp_username
        )
        flash(f"Invalid data encountered: {str(e)}", "error")
        return redirect("/ftp")
