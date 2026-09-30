"""
Momento Desktop Executable Builder
Automates PyInstaller bundling of the Momento desktop app into a standalone package.
"""

import sys
import os
import shutil
import subprocess
import argparse


def clean_build_artifacts():
    """Remove previous build and dist directories."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for folder in ['build', 'dist']:
        folder_path = os.path.join(base_dir, folder)
        if os.path.exists(folder_path):
            print(f"Cleaning existing {folder}/ directory...")
            try:
                shutil.rmtree(folder_path)
            except Exception as e:
                print(f"Warning: Could not completely remove {folder}/: {e}")


def check_prerequisites():
    """Check that PyInstaller and required dependencies are installed."""
    try:
        import PyInstaller
        print(f"PyInstaller found: version {PyInstaller.__version__}")
    except ImportError:
        print("Error: PyInstaller is not installed in the active environment.")
        print("Run: pip install pyinstaller")
        sys.exit(1)

    try:
        import webview
        print("pywebview found: ready for native desktop window packaging")
    except ImportError:
        print("Warning: pywebview not found. Desktop will fallback to system browser.")


def build_executable(clean: bool = True):
    """Run PyInstaller with Momento.spec."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec_path = os.path.join(base_dir, "Momento.spec")

    if not os.path.exists(spec_path):
        print(f"Error: Specification file not found at {spec_path}")
        sys.exit(1)

    if clean:
        clean_build_artifacts()

    print("\n=======================================================")
    print("  Starting Momento Desktop Application Build")
    print(f"  Target Spec: {spec_path}")
    print("=======================================================\n")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        spec_path,
        "--noconfirm"
    ]

    result = subprocess.run(cmd, cwd=base_dir)

    if result.returncode != 0:
        print(f"\nBuild failed with exit code: {result.returncode}")
        sys.exit(result.returncode)

    # Check executable output
    output_dir = os.path.join(base_dir, "dist", "Momento")
    exe_path = os.path.join(output_dir, "Momento.exe" if sys.platform == "win32" else "Momento")

    if os.path.exists(exe_path):
        size_mb = round(os.path.getsize(exe_path) / (1024 * 1024), 2)
        print("\n=======================================================")
        print("  Build Succeeded!")
        print(f"  Executable location: {exe_path}")
        print(f"  Distribution folder: {output_dir}")
        print(f"  Executable size:     {size_mb} MB")
        print("=======================================================")
        print("\nTo launch Momento as a standalone native desktop app:")
        print(f"  Double-click: {exe_path}")
        print(f"  Or run via terminal: .\\dist\\Momento\\Momento.exe\n")
        return exe_path
    else:
        print(f"\nWarning: Expected executable not found at {exe_path}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Build Momento Standalone Desktop App")
    parser.add_argument("--no-clean", action="store_true", help="Do not remove build/dist before building")
    args = parser.parse_args()

    check_prerequisites()
    build_executable(clean=not args.no_clean)


if __name__ == "__main__":
    main()
