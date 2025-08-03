#!/usr/bin/env python3
"""
Certificate generation module for diyHue Bridge Emulator.
Converts the functionality of genCert.sh to pure Python.
"""

import os
import sys
import subprocess
import tempfile
import logging

def gen_cert_python(mac_address: str, config_path: str = "/opt/hue-emulator/config", running_path: str = "/opt/hue-emulator") -> bool:
    """
    Generate SSL certificate for the Hue Bridge emulator.
    
    Args:
        mac_address (str): MAC address to use for certificate generation
        config_path (str): Path where the certificate will be stored
        
    Returns:
        bool: True if certificate generation was successful, False otherwise
    """
    try:
        # Convert MAC address from hex to decimal for serial number
        mac_clean = mac_address.strip('\u200e')
        dec_serial = int(mac_clean, 16)
        
        # Ensure config directory exists
        os.makedirs(config_path, exist_ok=True)
        
        # Create temporary files for private key and public certificate
        with tempfile.NamedTemporaryFile(mode='w', suffix='.key', delete=False) as private_key_file, \
             tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False) as public_cert_file:
            
            private_key_path = private_key_file.name
            public_cert_path = public_cert_file.name
        
        try:
            # OpenSSL command equivalent to the bash script
            openssl_cmd = [
                'faketime', '2017-01-01 00:00:00',
                'openssl', 'req', '-new', '-days', '7670',
                '-config', f'{running_path}/openssl.conf',
                '-nodes', '-x509', '-newkey', 'ec',
                '-pkeyopt', 'ec_paramgen_curve:P-256',
                '-pkeyopt', 'ec_param_enc:named_curve',
                '-subj', f'/C=NL/O=Philips Hue/CN={mac_clean}',
                '-keyout', private_key_path,
                '-out', public_cert_path,
                '-set_serial', str(dec_serial)
            ]
            
            # Execute the OpenSSL command
            result = subprocess.run(openssl_cmd, capture_output=True, text=True, check=True)
            
            # Combine private key and public certificate into cert.pem
            cert_pem_path = os.path.join(config_path, 'cert.pem')
            
            with open(cert_pem_path, 'w') as cert_file:
                # Write private key first
                with open(private_key_path, 'r') as private_key:
                    cert_file.write(private_key.read())
                
                # Append public certificate
                with open(public_cert_path, 'r') as public_cert:
                    cert_file.write(public_cert.read())
            
            logging.info(f"Certificate successfully generated at {cert_pem_path}")
            return True
            
        finally:
            # Clean up temporary files
            try:
                os.unlink(private_key_path)
                os.unlink(public_cert_path)
            except OSError:
                pass  # Files might not exist if openssl failed
                
    except ValueError as e:
        logging.error(f"Invalid MAC address format: {mac_address} - {e}")
        return False
    except subprocess.CalledProcessError as e:
        logging.error(f"OpenSSL command failed: {e}")
        logging.error(f"Command output: {e.stdout}")
        logging.error(f"Command error: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"Certificate generation failed: {e}")
        return False

def main():
    """
    Main function for command-line usage.
    Usage: python3 genCert.py <mac_address> [config_path] [running_path]
    """
    if len(sys.argv) < 2:
        print("Usage: python3 genCert.py <mac_address> [config_path] [running_path]")
        print("Example: python3 genCert.py 001788fffe123456 /opt/hue-emulator/config /opt/hue-emulator")
        sys.exit(1)
    
    mac_address = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else "/opt/hue-emulator/config"
    running_path = sys.argv[3] if len(sys.argv) > 3 else "/opt/hue-emulator"

    # Configure basic logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    success = gen_cert_python(mac_address, config_path, running_path)

    if not success:
        print("Certificate generation failed!")
        sys.exit(1)
    else:
        print("Certificate generation completed successfully!")

if __name__ == "__main__":
    main()
