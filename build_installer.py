"""
Momento Installer Executable Builder
Compresses the standalone desktop distribution (dist/Momento/) into an embedded payload
and compiles installer.py into a single, self-extracting setup executable: dist/Momento-Setup.exe.
"""

import sys
import os
import zipfile
import subprocess
import shutil
import argparse
import time


def compress_distribution(dist_dir: str, zip_path: str):
    """Compress contents of dist_dir into zip_path with maximum compression."""
    print(f"\nCompressing payload from: {dist_dir} ...")
    start_time = time.time()
    
    total_files = 0
    total_uncompressed = 0
    
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dist_dir)
                zip_out.write(full_path, rel_path)
                total_files += 1
                total_uncompressed += os.path.getsize(full_path)
                
    elapsed = round(time.time() - start_time, 2)
    compressed_size = os.path.getsize(zip_path)
    
    uncompressed_mb = round(total_uncompressed / (1024 * 1024), 2)
    compressed_mb = round(compressed_size / (1024 * 1024), 2)
    ratio = round((1 - (compressed_size / total_uncompressed)) * 100, 1) if total_uncompressed > 0 else 0
    
    print(f"Compressed {total_files} files in {elapsed}s.")
    print(f"  Uncompressed payload: {uncompressed_mb} MB")
    print(f"  Compressed payload:   {compressed_mb} MB ({ratio}% reduction)")
    return zip_path


def build_installer_executable(clean: bool = True):
    """Build the single-file Momento-Setup.exe using PyInstaller."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dist_momento = os.path.join(base_dir, "dist", "Momento")
    installer_script = os.path.join(base_dir, "installer.py")
    payload_zip = os.path.join(base_dir, "installer_payload.zip")

    # 1. Verify source distribution exists
    if not os.path.isdir(dist_momento) or not os.path.exists(os.path.join(dist_momento, "Momento.exe")):
        print(f"Distribution folder not found at {dist_momento}.")
        print("Running build_desktop.py to generate Momento desktop app first...")
        import build_desktop
        build_desktop.build_executable(clean=clean)

    if not os.path.isdir(dist_momento):
        print("Error: Could not locate or build dist/Momento directory.")
        sys.exit(1)

    # 2. Compress dist/Momento into installer_payload.zip
    compress_distribution(dist_momento, payload_zip)

    try:
        # 3. Clean previous installer build files if requested
        build_dir = os.path.join(base_dir, "build", "Momento-Setup")
        if clean and os.path.exists(build_dir):
            try:
                shutil.rmtree(build_dir)
            except Exception as e:
                print(f"Warning: Could not clear {build_dir}: {e}")

        # 4. Invoke PyInstaller for single-file installer
        print("\n=======================================================")
        print("  Compiling Single-File Setup Executable (Momento-Setup.exe)")
        print("=======================================================\n")

        # PyInstaller add-data syntax: source;dest on Windows, source:dest on Unix
        sep = ";" if sys.platform == "win32" else ":"
        add_data_arg = f"{payload_zip}{sep}."

        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--windowed",
            "--name",
            "Momento-Setup",
            "--add-data",
            add_data_arg,
            installer_script,
            "--noconfirm",
            "--distpath",
            os.path.join(base_dir, "dist"),
            "--workpath",
            os.path.join(base_dir, "build"),
        ]

        result = subprocess.run(cmd, cwd=base_dir)

        if result.returncode != 0:
            print(f"\nInstaller build failed with exit code: {result.returncode}")
            sys.exit(result.returncode)

        # 5. Check output
        setup_exe = os.path.join(base_dir, "dist", "Momento-Setup.exe" if sys.platform == "win32" else "Momento-Setup")

        if os.path.exists(setup_exe):
            size_mb = round(os.path.getsize(setup_exe) / (1024 * 1024), 2)
            print("\n=======================================================")
            print("  Installer Packaging Succeeded!")
            print(f"  Installer Binary:    {setup_exe}")
            print(f"  Installer File Size: {size_mb} MB")
            print("=======================================================")
            print("\nHow to deploy / install Momento:")
            print(f"  1. Distribute '{os.path.basename(setup_exe)}' to any Windows user.")
            print("  2. Double-click to launch the graphical setup wizard.")
            print("  3. Or run silently from command line: Momento-Setup.exe /S\n")
            return setup_exe
        else:
            print(f"\nError: Expected setup executable not found at {setup_exe}")
            sys.exit(1)

    finally:
        # Clean up temporary installer payload archive
        if os.path.exists(payload_zip):
            try:
                os.remove(payload_zip)
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="Package Momento into a Single-File Setup Executable")
    parser.add_argument("--no-clean", action="store_true", help="Do not remove build cache before compiling")
    args = parser.parse_args()

    build_installer_executable(clean=not args.no_clean)


if __name__ == "__main__":
    main()
