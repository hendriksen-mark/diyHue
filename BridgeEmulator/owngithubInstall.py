#!/usr/bin/env python3
import shutil
import tempfile
import zipfile
import subprocess
import requests
from pathlib import Path
import logging
import argparse
import socket
from typing import Optional
import yaml

import logManager

logger: logging.Logger = logManager.logger.get_logger(__name__)

class GitHubInstaller:
    """
    Pure Python implementation for updating the server from GitHub releases.
    """
    def __init__(self, **kwargs):
        self.server_path: Path = Path(kwargs.get("running_path", "/opt/hue-emulator"))
        self.config_path: Path = Path(kwargs.get("config_path", "/opt/hue-emulator/config"))
        self.branch: str = kwargs.get("branch", "test")
        self.ui_repo_owner: str = kwargs.get("ui_repo_owner", "hendriksen-mark")
        self.ui_repo_name: str = kwargs.get("ui_repo_name", "diyHueUI")
        self.repo_owner: str = kwargs.get("repo_owner", "hendriksen-mark")
        self.repo_name: str = kwargs.get("repo_name", "diyHue")
        self.temp_dir: Optional[Path] = None

    def install_updates(self) -> bool:
        """
        Install updates from GitHub based on the state.

        Args:
            state: The update state ("allreadytoinstall" or "anyreadytoinstall")
            branch: The branch to download from
        Returns:
            bool: True if installation was successful, False otherwise
        """
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                self.temp_dir = Path(temp_dir)
                if not self._install_system_dependencies():
                    logger.error("_install_system_dependencies failed. Continuing update process.")
                if not self._install_server_update(self.branch):
                    logger.error("_install_server_update failed. Aborting update process.")
                    return False
                # Always install UI update
                if not self._install_ui_update():
                    logger.error("_install_ui_update failed. Aborting update process.")
                    return False
                if not self.update_yaml_config():
                    logger.error("update_yaml_config failed. Check branch configuration.")
            return True
        except Exception as e:
            logger.error(f"Error during update installation: {e}")
            return False

    def _install_server_update(self, branch: str) -> bool:
        """Install server update from GitHub."""
        try:
            # Download server archive
            server_url = f"https://github.com/{self.repo_owner}/{self.repo_name}/archive/{branch}.zip"
            server_zip_path = self.temp_dir / f"{self.repo_name}.zip"

            logger.info(f"Downloading diyHue update from {server_url}")
            if not self._download_file(server_url, server_zip_path):
                logger.error(f"Failed to download diyHue update from {server_url} to {server_zip_path}")
                return False

            # Extract archive
            extract_dir = self.temp_dir / f"{self.repo_name}_extract"
            if not self._extract_zip(server_zip_path, extract_dir):
                logger.error(f"Failed to extract diyHue zip {server_zip_path} to {extract_dir}")
                return False

            server_zip_path.unlink()  # Remove zip file

            # Find the extracted directory
            extracted_dirs = list(extract_dir.glob(f"{self.repo_name}-*"))
            if not extracted_dirs:
                logger.error("Could not find extracted diyHue directory")
                logger.error(f"Checked in {extract_dir}, found: {[str(d) for d in extract_dir.iterdir()]}")
                return False

            server_source = extracted_dirs[0]

            # Update pip and install requirements
            if not self._update_python_dependencies(server_source / "requirements.txt"):
                logger.error(f"Failed to update Python dependencies from {server_source / 'requirements.txt'}")
                return False
            
            if not self._backup_and_clean_install():
                logger.error("Failed to backup and clean install")
                return False

            # Remove old local logManager directory if it exists (now a package)
            old_logmanager_path = self.server_path / "logManager"
            if old_logmanager_path.exists():
                shutil.rmtree(old_logmanager_path)
                logger.info("Removed old local logManager directory (now using package)")

            # Copy server files
            files_to_copy = [
                "BridgeEmulator/flaskUI",
                "BridgeEmulator/functions",
                "BridgeEmulator/lights",
                "BridgeEmulator/sensors",
                "BridgeEmulator/HueObjects",
                "BridgeEmulator/services",
                "BridgeEmulator/configManager",
                "BridgeEmulator/HueEmulator3.py",
                "BridgeEmulator/openssl.conf",
                "BridgeEmulator/owngithubInstall.py",
            ]

            for item in files_to_copy:
                source = server_source / item
                # Extract just the filename/dirname from the BridgeEmulator path
                item_name = Path(item).name
                dest = self.server_path / item_name

                if source.exists():
                    if source.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(source, dest)
                    else:
                        shutil.copy2(source, dest)
                    logger.debug(f"Copied {item} to server directory")
                else:
                    logger.warning(f"Source file/directory not found: {source}")

            return True

        except Exception as e:
            logger.error(f"Error installing diyHue update: {e}")
            return False

    def _install_ui_update(self) -> bool:
        """Install UI update from GitHub releases."""
        try:
            # Download UI archive
            ui_url = f"https://github.com/{self.ui_repo_owner}/{self.ui_repo_name}/releases/latest/download/{self.ui_repo_name}-release.zip"
            ui_zip_path = self.temp_dir / "diyHueUI.zip"

            logger.info(f"Downloading UI update from {ui_url}")
            if not self._download_file(ui_url, ui_zip_path):
                logger.error(f"Failed to download UI update from {ui_url} to {ui_zip_path}")
                return False

            # Extract UI archive
            ui_extract_dir = self.temp_dir / self.ui_repo_name
            ui_extract_dir.mkdir(exist_ok=True)

            if not self._extract_zip(ui_zip_path, ui_extract_dir):
                logger.error(f"Failed to extract UI zip {ui_zip_path} to {ui_extract_dir}")
                return False

            ui_zip_path.unlink()  # Remove zip file

            # Copy UI files
            ui_source = ui_extract_dir / "dist"
            if not ui_source.exists():
                logger.error("UI dist directory not found in extracted archive")
                logger.error(f"Checked in {ui_extract_dir}, found: {[str(d) for d in ui_extract_dir.iterdir()]}")
                return False

            # Copy index.html
            index_source = ui_source / "index.html"
            index_dest = self.server_path / "flaskUI" / "templates" / "index.html"
            if index_source.exists():
                shutil.copy2(index_source, index_dest)
                logger.debug("Copied UI index.html")
            else:
                logger.error(f"index.html not found at {index_source}")

            # Copy assets (merge instead of replace to preserve existing server assets)
            assets_source = ui_source / "assets"
            assets_dest = self.server_path / "flaskUI" / "assets"
            if assets_source.exists():
                # Ensure destination directory exists
                assets_dest.mkdir(parents=True, exist_ok=True)

                asset_items = list(assets_source.iterdir())
                if not asset_items:
                    logger.error(f"No items found in {assets_source}.")
                    return False

                # Copy only the files from the UI update, preserving existing assets
                for item in asset_items:
                    dest_item = assets_dest / item.name
                    success_copy = ""
                    if item.is_dir():
                        if dest_item.exists():
                            shutil.rmtree(dest_item)
                        success_copy = shutil.copytree(item, dest_item)
                    else:
                        success_copy = shutil.copy2(item, dest_item)
                    if success_copy != dest_item:
                        logger.error(f"Failed to copy {item} to {dest_item}")
                        return False
                    logger.debug(f"Copied UI {'directory' if item.is_dir() else 'file'} {item.name}")

                logger.debug("Merged UI assets with existing assets")
            else:
                logger.error(f"UI assets directory not found at {assets_source}")

            return True

        except Exception as e:
            logger.error(f"Error installing UI update: {e}")
            return False

    def _download_file(self, url: str, dest_path: Path) -> bool:
        """Download a file from URL to destination path."""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.debug(f"Downloaded {url} to {dest_path}")
            return True

        except requests.RequestException as e:
            logger.error(f"Error downloading {url}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading {url} to {dest_path}: {e}")
            return False

    def _extract_zip(self, zip_path: Path, extract_to: Path) -> bool:
        """Extract a zip file to the specified directory."""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)

            logger.debug(f"Extracted {zip_path} to {extract_to}")
            return True

        except zipfile.BadZipFile as e:
            logger.error(f"Error extracting {zip_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error extracting {zip_path} to {extract_to}: {e}")
            return False

    def _backup_and_clean_install(self) -> bool:
        """
        Make a temporary backup of config folder and log files,
        remove the running folder for fresh install, then restore backups.
        """
        try:
            backup_dir = self.temp_dir / "hue-emulator_backup"
            log_backup_dir = self.temp_dir / "log_backup"

            logger.info("Making backup of config and log files...")

            # Backup config folder
            if self.config_path.exists():
                shutil.copytree(self.config_path, backup_dir)
                logger.debug(f"Backed up config folder to {backup_dir}")
            else:
                logger.warning(f"Config folder not found at {self.config_path}")

            # Backup log files
            log_backup_dir.mkdir(exist_ok=True)
            log_files = list(self.server_path.glob("*.log*"))
            for log_file in log_files:
                if log_file.is_file():
                    shutil.copy2(log_file, log_backup_dir)
                    logger.debug(f"Backed up log file {log_file.name}")

            if log_files:
                logger.debug(f"Backed up {len(log_files)} log files to {log_backup_dir}")
            else:
                logger.debug("No log files found to backup")

            # Remove all contents of running folder for fresh install (except config)
            logger.info("Removing existing installation for fresh install...")
            for item in self.server_path.iterdir():
                # Skip config directory if it's inside server_path
                if item == self.config_path:
                    logger.debug(f"Skipping config directory: {item}")
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            logger.debug("Removed all existing files from server directory (except config)")

            # Restore config folder (only if it was backed up and config_path is different from existing)
            if backup_dir.exists() and not self.config_path.exists():
                shutil.copytree(backup_dir, self.config_path)
                logger.debug("Restored config folder")
            elif backup_dir.exists() and self.config_path.exists():
                logger.debug("Config folder already exists, skipping restore")
            else:
                logger.debug("No config backup to restore")

            # Restore log files
            if log_backup_dir.exists():
                for log_file in log_backup_dir.iterdir():
                    if log_file.is_file():
                        shutil.copy2(log_file, self.server_path)
                        logger.debug(f"Restored log file {log_file.name}")

            logger.info("Backup and clean install completed successfully")
            return True

        except Exception as e:
            logger.error(f"Error during backup and clean install: {e}")
            return False

    def _update_python_dependencies(self, requirements_path: Path) -> bool:
        """Update pip and install requirements."""
        try:
            # Update pip
            pip_result = subprocess.run([
                "python3", "-m", "pip", "install", "--upgrade", "pip", "--break-system-packages"
            ], check=True, capture_output=True, text=True)

            if pip_result.stdout:
                logger.debug(f"pip update output: {pip_result.stdout.strip()}")
            if pip_result.stderr:
                logger.error(f"pip update error: {pip_result.stderr.strip()}")

            # Install requirements
            if requirements_path.exists():
                try:
                    dep_result = subprocess.run([
                        "pip3", "install", "-r", str(requirements_path),
                        "--no-cache-dir", "--break-system-packages"
                    ], check=True, capture_output=True, text=True)
                    if dep_result.stdout:
                        logger.debug(f"pip install output: {dep_result.stdout.strip()}")
                    if dep_result.stderr:
                        logger.error(f"pip install error: {dep_result.stderr.strip()}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Error installing requirements from {requirements_path}: {e}")
                    logger.error(f"stdout: {e.stdout}")
                    logger.error(f"stderr: {e.stderr}")
                    return False
            else:
                logger.warning(f"Requirements file not found: {requirements_path}")

            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Error updating pip: {e}")
            logger.error(f"stdout: {e.stdout}")
            logger.error(f"stderr: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error updating Python dependencies: {e}")
            return False

    def _install_system_dependencies(self) -> bool:
        """Install required system dependencies based on the detected package manager."""
        try:
            logger.info("Installing system dependencies...")

            # Check for apt (Debian-based)
            apt_check = subprocess.run(['which', 'apt'], capture_output=True, text=True)
            if apt_check.returncode == 0:
                logger.info("Detected apt package manager (Debian-based)")
                packages = [
                    'unzip', 'python3', 'python3-pip', 'openssl', 'git',
                    'bluez', 'bluetooth', 'libcoap3-bin', 'faketime'
                ]
                cmd = ['apt-get', 'install', '-y'] + packages

                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    logger.info("System dependencies installed successfully")
                    if result.stdout:
                        logger.debug(f"apt install output: {result.stdout.strip()}")
                    return True
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to install dependencies with apt: {e}")
                    if e.stderr:
                        logger.error(f"apt error: {e.stderr.strip()}")
                    return False

            # Check for pacman (Arch Linux)
            pacman_check = subprocess.run(['which', 'pacman'], capture_output=True, text=True)
            if pacman_check.returncode == 0:
                logger.info("Detected pacman package manager (Arch Linux)")

                # Update package database
                try:
                    subprocess.run(['pacman', '-Syq', '--noconfirm'], check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to update pacman database: {e}")
                    return False

                # Install packages
                packages = [
                    'unzip', 'python3', 'python-pip', 'gnu-netcat', 
                    'libcoap', 'faketime', 'git', 'openssl', 'bluez', 'bluetooth'
                ]
                cmd = ['pacman', '-Sq', '--noconfirm'] + packages

                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    logger.info("System dependencies installed successfully")
                    if result.stdout:
                        logger.debug(f"pacman install output: {result.stdout.strip()}")
                    return True
                except subprocess.CalledProcessError as e:
                    logger.error(f"Failed to install dependencies with pacman: {e}")
                    if e.stderr:
                        logger.error(f"pacman error: {e.stderr.strip()}")
                    return False

            # No supported package manager found
            logger.warning("Unable to detect supported package manager (apt or pacman)")
            logger.warning("Please ensure the following packages are installed manually:")
            logger.warning("- unzip, python3, python3-pip, openssl, bluez, bluetooth")
            logger.warning("- libcoap3-bin (or libcoap), faketime, gnu-netcat (arch)")
            return True  # Don't fail the update, just warn

        except Exception as e:
            logger.error(f"Unexpected error installing system dependencies: {e}")
            return False

    def update_yaml_config(self):
        """
        Update the YAML configuration file with the current server configuration.
        """
        try:
            config_path = self.server_path / "config" / "config.yaml"
            if not config_path.exists():
                logger.error(f"Configuration file not found: {config_path}")
                return False

            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}

            if 'system' not in config:
                config['system'] = {}
            config['system']['branch'] = self.branch

            with open(config_path, 'w') as f:
                yaml.safe_dump(config, f, default_flow_style=False)

            logger.info("YAML configuration updated successfully.")
            return True
        except yaml.YAMLError as e:
            logger.error(f"Error updating YAML configuration: {e}")
            return False
        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating YAML configuration: {e}")
            return False

def getIpAddress() -> Optional[str]:
    """
    Get the local IP address by connecting to an external server.

    Returns:
        Optional[str]: The local IP address or None if an error occurs.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except socket.error as e:
        logger.error(f"Socket error: {e}")
        return None

def fetch_github_branches(repo_owner: str, repo_name: str) -> list[str]:
    """Fetch branch names from GitHub API."""
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/branches"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        branches = [b["name"] for b in response.json()]
        return branches
    except Exception as e:
        logger.error(f"Could not fetch branches from GitHub: {e}")
        # Fallback to defaults
        return ["main", "dev"]

def select_branch_interactively(branches: list[str]) -> str:
    """Prompt user to select a branch from a list."""
    print("\033[36mPlease select a branch to install\033[0m")
    for i, branch in enumerate(branches, 1):
        if branch in ("main", "master"):
            print(f"[{i}] {branch} - most stable Release")
        elif branch in ("dev", "development"):
            print(f"[{i}] {branch} - test latest features and fixes - Work in Progress!")
        else:
            print(f"[{i}] {branch}")
    try:
        selection = int(input("I go with Nr.: "))
        if 1 <= selection <= len(branches):
            return branches[selection - 1]
        else:
            print(f"Invalid selection. Using default: {branches[0]}")
            return branches[0]
    except Exception:
        print(f"Invalid input. Using default: {branches[0]}")
        return branches[0]

def is_docker_environment():
    """Check if we're running in a Docker container."""
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read() or 'containerd' in f.read()
    except FileNotFoundError:
        return False

def try_systemctl_restart():
    """Try to restart using systemctl with appropriate permissions."""
    # In Docker, try without sudo first (often running as root)
    commands_to_try = [
        ['systemctl', 'restart', 'hue-emulator.service'],
        ['sudo', 'systemctl', 'restart', 'hue-emulator.service']
    ]

    for cmd in commands_to_try:
        try:
            restart_result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if restart_result.returncode == 0:
                logger.info(f"diyHue restarted successfully using: {' '.join(cmd)}")
                return True
            else:
                logger.debug(f"Command '{' '.join(cmd)}' failed: {restart_result.stderr}")
        except FileNotFoundError:
            logger.debug(f"Command not found: {cmd[0]}")
            continue
        except subprocess.TimeoutExpired:
            logger.warning(f"Command '{' '.join(cmd)}' timed out")
            continue
        except Exception as e:
            logger.debug(f"Error with command '{' '.join(cmd)}': {e}")
            continue
    return False

def main():
    # Defaults
    REPO_OWNER = "hendriksen-mark"
    REPO_NAME = "diyHue"
    UI_REPO_OWNER = "hendriksen-mark"
    UI_REPO_NAME = "diyhueui"
    RUNNING_PATH = "/opt/hue-emulator"
    CONFIG_PATH = "/opt/hue-emulator/config"

    # Parse arguments
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", type=str, help="Server IP address", default=getIpAddress())
    ap.add_argument("--port", type=int, help="Port diyHue is running on", default=80)
    ap.add_argument("--repo_owner", type=str, help="GitHub repository owner", default=REPO_OWNER)
    ap.add_argument("--repo_name", type=str, help="GitHub repository name", default=REPO_NAME)
    ap.add_argument("--branch", type=str, help="Branch to install")
    ap.add_argument("--ui_repo_owner", type=str, help="UI GitHub repository owner", default=UI_REPO_OWNER)
    ap.add_argument("--ui_repo_name", type=str, help="UI GitHub repository name", default=UI_REPO_NAME)
    ap.add_argument("--debug", action='store_true', help="Enables debug output", default=False)
    ap.add_argument("--running_path", help="Set running location", type=str, default=RUNNING_PATH)
    ap.add_argument("--config_path", help="Set config location", type=str, default=CONFIG_PATH)

    args = ap.parse_args()

    ip = args.ip
    port = args.port
    repo_owner = args.repo_owner
    repo_name = args.repo_name
    branch = args.branch
    ui_repo_owner = args.ui_repo_owner
    ui_repo_name = args.ui_repo_name
    debug = args.debug
    running_path = args.running_path
    config_path = args.config_path

    if debug:
        logManager.logger.configure_logger("DEBUG")
    else:
        logManager.logger.configure_logger("INFO")

    logger.info(f"Starting update process for {repo_owner}/{repo_name} on branch {branch}")
    logger.info(f"Debug logging {'enabled' if debug else 'disabled'}!")
    logger.debug(f"Running path: {running_path}")
    logger.debug(f"IP: {ip}:{port}")
    logger.debug(f"UI Repo: {ui_repo_owner}/{ui_repo_name}")

    try:
        response = requests.get(f"http://{ip}:{port}/save", stream=True)
        response.raise_for_status()
        if response.status_code == 200:
            logger.info("Config saved successfully, proceeding with update...")
        else:
            logger.error(f"diyHue returned status code {response.status_code}, config not saved.")
    except Exception as e:
        logger.error(f"Error occurred while saving config: {e}")

    # Interactive branch selection if not provided
    if not branch:
        branches = fetch_github_branches(repo_owner, repo_name)
        branch = select_branch_interactively(branches)
    logger.info(f"Selected branch: {branch}")

    installer = GitHubInstaller(
        running_path=running_path,
        config_path=config_path,
        ui_repo_owner=ui_repo_owner,
        ui_repo_name=ui_repo_name,
        repo_name=repo_name,
        repo_owner=repo_owner,
        branch=branch
    )

    update_output = installer.install_updates()
    if not update_output:
        logger.error("Update installation failed. Exiting.")
        logger.error("Try to start diyHue...")
    else:
        logger.info("Update installation completed successfully.")
        logger.info(f"Restarting diyHue...")

    try:
        in_docker = is_docker_environment()
        logger.debug(f"Docker environment detected: {in_docker}")

        # Try systemctl restart
        if try_systemctl_restart():
            return  # Successfully restarted

        # Fallback to HTTP restart endpoint
        logger.info("Systemctl restart failed, trying HTTP restart endpoint...")
        response = requests.get(f"http://{ip}:{port}/restart", stream=True, timeout=5)
        logger.info("diyHue restart initiated via HTTP endpoint")

    except requests.exceptions.RequestException as e:
        # This is expected when the server restarts and closes the connection
        logger.info(f"diyHue restart initiated (connection closed as expected): {e}")
    except Exception as e:
        logger.error(f"Error occurred while restarting diyHue: {e}")
        in_docker = is_docker_environment()
        if in_docker:
            logger.info("In Docker environment: You may need to restart the container manually")

if __name__ == "__main__":
    main()
