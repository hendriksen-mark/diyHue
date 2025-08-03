import shutil
import tempfile
import zipfile
import subprocess
import requests
from pathlib import Path
from typing import Any

import configManager
import logManager

bridgeConfig: dict[str, Any] = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)

class GitHubInstaller:
    """
    Pure Python implementation for updating the server from GitHub releases.
    """
    
    def __init__(self):
        self.server_path = Path(configManager.bridgeConfig.runningDir)
        self.config_path = Path(configManager.bridgeConfig.configDir)
        self.temp_dir = None
        
    def install_updates(self, state: str, branch: str) -> bool:
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
                if state == "allreadytoinstall":
                    bridgeConfig["config"]["swupdate2"]["state"] = "transferring"
                    logging.info("Installing server + UI update")
                    if not self._install_server_update(branch):
                        logging.error("_install_server_update failed. Aborting update process.")
                        return False
                else:
                    logging.info("Installing UI update only")
                # Set state to installing after download/transfer
                bridgeConfig["config"]["swupdate2"]["state"] = "transferring"
                # Always install UI update
                if not self._install_ui_update():
                    logging.error("_install_ui_update failed. Aborting update process.")
                    return False
            logging.info("Update installation completed successfully")
            return True
        except Exception as e:
            logging.error(f"Error during update installation: {e}")
            return False
    
    def _install_server_update(self, branch: str) -> bool:
        """Install server update from GitHub."""
        try:
            # Download server archive
            # server_url = f"https://github.com/diyhue/diyhue/archive/{branch}.zip"
            server_url = f"https://github.com/hendriksen-mark/diyhue/archive/{branch}.zip"
            server_zip_path = self.temp_dir / "diyHue.zip"
            
            logging.info(f"Downloading diyHue update from {server_url}")
            if not self._download_file(server_url, server_zip_path):
                logging.error(f"Failed to download diyHue update from {server_url} to {server_zip_path}")
                return False
            
            bridgeConfig["config"]["swupdate2"]["state"] = "installing"
            
            # Extract archive
            extract_dir = self.temp_dir / "diyHue_extract"
            if not self._extract_zip(server_zip_path, extract_dir):
                logging.error(f"Failed to extract diyHue zip {server_zip_path} to {extract_dir}")
                return False
            
            server_zip_path.unlink()  # Remove zip file
            
            # Find the extracted directory
            extracted_dirs = list(extract_dir.glob("diyHue-*"))
            if not extracted_dirs:
                logging.error("Could not find extracted diyHue directory")
                logging.error(f"Checked in {extract_dir}, found: {[str(d) for d in extract_dir.iterdir()]}")
                return False
            
            server_source = extracted_dirs[0]

            if not self._install_system_dependencies():
                logging.error("_install_system_dependencies failed. Continuing update process.")
            
            # Update pip and install requirements
            if not self._update_python_dependencies(server_source / "requirements.txt"):
                logging.error(f"Failed to update Python dependencies from {server_source / 'requirements.txt'}")
                return False

            # Make backup and clean install
            if not self._backup_and_clean_install():
                logging.error("Failed to backup and clean install")
                return False

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
                "BridgeEmulator/openssl.conf"
            ]
            
            for item in files_to_copy:
                source = server_source / item
                item_name = Path(item).name
                dest = self.server_path / item_name
                
                if source.exists():
                    if source.is_dir():
                        if dest.exists():
                            shutil.rmtree(dest)
                        shutil.copytree(source, dest)
                    else:
                        shutil.copy2(source, dest)
                    logging.debug(f"Copied {item} to server directory")
                else:
                    logging.warning(f"Source file/directory not found: {source}")

            return True
            
        except Exception as e:
            logging.error(f"Error installing diyHue update: {e}")
            return False
    
    def _install_ui_update(self) -> bool:
        """Install UI update from GitHub releases."""
        try:
            # Download UI archive
            # ui_url = "https://github.com/diyhue/diyHueUI/releases/latest/download/DiyHueUI-release.zip"
            ui_url = "https://github.com/hendriksen-mark/diyHueUI/releases/latest/download/DiyHueUI-release.zip"
            ui_zip_path = self.temp_dir / "diyHueUI.zip"

            logging.info(f"Downloading UI update from {ui_url}")
            if not self._download_file(ui_url, ui_zip_path):
                logging.error(f"Failed to download UI update from {ui_url} to {ui_zip_path}")
                return False
            
            bridgeConfig["config"]["swupdate2"]["state"] = "installing"
            
            # Extract UI archive
            ui_extract_dir = self.temp_dir / "diyHueUI"
            ui_extract_dir.mkdir(exist_ok=True)
            
            if not self._extract_zip(ui_zip_path, ui_extract_dir):
                logging.error(f"Failed to extract UI zip {ui_zip_path} to {ui_extract_dir}")
                return False
            
            ui_zip_path.unlink()  # Remove zip file
            
            # Copy UI files
            ui_source = ui_extract_dir / "dist"
            if not ui_source.exists():
                logging.error("UI dist directory not found in extracted archive")
                logging.error(f"Checked in {ui_extract_dir}, found: {[str(d) for d in ui_extract_dir.iterdir()]}")
                return False
            
            # Copy index.html
            index_source = ui_source / "index.html"
            index_dest = self.server_path / "flaskUI" / "templates" / "index.html"
            if index_source.exists():
                shutil.copy2(index_source, index_dest)
                logging.debug("Copied UI index.html")
            else:
                logging.error(f"index.html not found at {index_source}")
            
            # Copy assets (merge instead of replace to preserve existing server assets)
            assets_source = ui_source / "assets"
            assets_dest = self.server_path / "flaskUI" / "assets"
            if assets_source.exists():
                # Ensure destination directory exists
                assets_dest.mkdir(parents=True, exist_ok=True)

                asset_items = list(assets_source.iterdir())
                if not asset_items:
                    logging.error(f"No items found in {assets_source}.")
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
                        logging.error(f"Failed to copy {item} to {dest_item}")
                        return False
                    logging.debug(f"Copied UI {'directory' if item.is_dir() else 'file'} {item.name}")

                logging.debug("Merged UI assets with existing assets")
            else:
                logging.error(f"UI assets directory not found at {assets_source}")
            
            return True
            
        except Exception as e:
            logging.error(f"Error installing UI update: {e}")
            return False
    
    def _download_file(self, url: str, dest_path: Path) -> bool:
        """Download a file from URL to destination path."""
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logging.debug(f"Downloaded {url} to {dest_path}")
            return True
            
        except requests.RequestException as e:
            logging.error(f"Error downloading {url}: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error downloading {url} to {dest_path}: {e}")
            return False
    
    def _extract_zip(self, zip_path: Path, extract_to: Path) -> bool:
        """Extract a zip file to the specified directory."""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            
            logging.debug(f"Extracted {zip_path} to {extract_to}")
            return True
            
        except zipfile.BadZipFile as e:
            logging.error(f"Error extracting {zip_path}: {e}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error extracting {zip_path} to {extract_to}: {e}")
            return False

    def _backup_and_clean_install(self) -> bool:
        """
        Make a temporary backup of config folder and log files, 
        remove the running folder for fresh install, then restore backups.
        """
        try:
            backup_dir = self.temp_dir / "hue-emulator_backup"
            log_backup_dir = self.temp_dir / "log_backup"

            logging.info("Making backup of config and log files...")

            # Backup config folder
            if self.config_path.exists():
                shutil.copytree(self.config_path, backup_dir)
                logging.debug(f"Backed up config folder to {backup_dir}")
            else:
                logging.warning(f"Config folder not found at {self.config_path}")

            # Backup log files
            log_backup_dir.mkdir(exist_ok=True)
            log_files = list(self.server_path.glob("*.log*"))
            for log_file in log_files:
                if log_file.is_file():
                    shutil.copy2(log_file, log_backup_dir)
                    logging.debug(f"Backed up log file {log_file.name}")

            if log_files:
                logging.debug(f"Backed up {len(log_files)} log files to {log_backup_dir}")
            else:
                logging.debug("No log files found to backup")

            # Remove all contents of running folder for fresh install
            logging.info("Removing existing installation for fresh install...")
            for item in self.server_path.iterdir():
                # Skip config directory if it's inside server_path
                if item == self.config_path:
                    logging.debug(f"Skipping config directory: {item}")
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            logging.debug("Removed all existing files from server directory (except config)")

            # Restore config folder
            if backup_dir.exists() and not self.config_path.exists():
                shutil.copytree(backup_dir, self.config_path)
                logging.debug("Restored config folder")
            elif backup_dir.exists() and self.config_path.exists():
                logging.debug("Config folder already exists, skipping restore")
            else:
                logging.debug("No config backup to restore")

            # Restore log files
            if log_backup_dir.exists():
                for log_file in log_backup_dir.iterdir():
                    if log_file.is_file():
                        shutil.copy2(log_file, self.server_path)
                        logging.debug(f"Restored log file {log_file.name}")

            logging.info("Backup and clean install completed successfully")
            return True

        except Exception as e:
            logging.error(f"Error during backup and clean install: {e}")
            return False

    def _update_python_dependencies(self, requirements_path: Path) -> bool:
        """Update pip and install requirements."""
        try:
            # Update pip
            subprocess.run([
                "python3", "-m", "pip", "install", "--upgrade", "pip", "--break-system-packages"
            ], check=True, capture_output=True, text=True)
            
            # Install requirements
            if requirements_path.exists():
                try:
                    subprocess.run([
                        "pip3", "install", "-r", str(requirements_path), 
                        "--no-cache-dir", "--break-system-packages"
                    ], check=True, capture_output=True, text=True)
                    logging.debug("Updated Python dependencies")
                except subprocess.CalledProcessError as e:
                    logging.error(f"Error installing requirements from {requirements_path}: {e}")
                    logging.error(f"stdout: {e.stdout}")
                    logging.error(f"stderr: {e.stderr}")
                    return False
            else:
                logging.warning(f"Requirements file not found: {requirements_path}")
            
            return True
        
        except subprocess.CalledProcessError as e:
            logging.error(f"Error updating pip: {e}")
            logging.error(f"stdout: {e.stdout}")
            logging.error(f"stderr: {e.stderr}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error updating Python dependencies: {e}")
            return False

    def _install_system_dependencies(self) -> bool:
        """Install required system dependencies based on the detected package manager."""
        try:
            logging.info("Installing system dependencies...")
            
            # Check for apt (Debian-based)
            apt_check = subprocess.run(['which', 'apt'], capture_output=True, text=True)
            if apt_check.returncode == 0:
                logging.info("Detected apt package manager (Debian-based)")
                packages = [
                    'unzip', 'python3', 'python3-pip', 'openssl', 'git',
                    'bluez', 'bluetooth', 'libcoap3-bin', 'faketime'
                ]
                cmd = ['apt-get', 'install', '-y'] + packages
                
                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    logging.info("System dependencies installed successfully")
                    if result.stdout:
                        logging.debug(f"apt install output: {result.stdout.strip()}")
                    return True
                except subprocess.CalledProcessError as e:
                    logging.error(f"Failed to install dependencies with apt: {e}")
                    if e.stderr:
                        logging.error(f"apt error: {e.stderr.strip()}")
                    return False
            
            # Check for pacman (Arch Linux)
            pacman_check = subprocess.run(['which', 'pacman'], capture_output=True, text=True)
            if pacman_check.returncode == 0:
                logging.info("Detected pacman package manager (Arch Linux)")

                # Update package database
                try:
                    subprocess.run(['pacman', '-Syq', '--noconfirm'], check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    logging.error(f"Failed to update pacman database: {e}")
                    return False
                
                # Install packages
                packages = [
                    'unzip', 'python3', 'python-pip', 'gnu-netcat', 
                    'libcoap', 'faketime', 'git', 'openssl', 'bluez', 'bluetooth'
                ]
                cmd = ['pacman', '-Sq', '--noconfirm'] + packages
                
                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    logging.info("System dependencies installed successfully")
                    if result.stdout:
                        logging.debug(f"pacman install output: {result.stdout.strip()}")
                    return True
                except subprocess.CalledProcessError as e:
                    logging.error(f"Failed to install dependencies with pacman: {e}")
                    if e.stderr:
                        logging.error(f"pacman error: {e.stderr.strip()}")
                    return False
            
            # No supported package manager found
            logging.warning("Unable to detect supported package manager (apt or pacman)")
            logging.warning("Please ensure the following packages are installed manually:")
            logging.warning("- unzip, python3, python3-pip, openssl, bluez, bluetooth , git")
            logging.warning("- libcoap3-bin (or libcoap), faketime, gnu-netcat (arch)")
            return False
            
        except Exception as e:
            logging.error(f"Unexpected error installing system dependencies: {e}")
            return False

def install_github_updates(state: str, branch: str) -> bool:
    """
    Install updates from GitHub.
    
    Args:
        state: The update state ("allreadytoinstall" or "anyreadytoinstall")
        branch: The branch to download from
        
    Returns:
        bool: True if installation was successful, False otherwise
    """
    installer = GitHubInstaller()
    return installer.install_updates(state, branch)
