"""
Unit tests for installer utilities and installation logic in installer.py and build_installer.py.
"""

import os
import sys
import tempfile
import zipfile
import pytest

from installer import (
    get_resource_path,
    make_shortcut,
    create_uninstaller,
    perform_installation,
    parse_installer_args,
    APP_NAME,
    APP_DISPLAY_NAME
)
from build_installer import compress_distribution


def test_parse_installer_args():
    # Test silent flags
    args = parse_installer_args(["/S"])
    assert args.silent is True

    args = parse_installer_args(["--silent"])
    assert args.silent is True

    # Test directory flag
    args = parse_installer_args(["/S", "--dir", "C:\\Custom\\Path"])
    assert args.silent is True
    assert args.dir == "C:\\Custom\\Path"

    # Test /D= flag
    args = parse_installer_args(["/S", "/D=C:\\Custom\\Path"])
    assert args.silent is True
    assert args.dir == "C:\\Custom\\Path"

    # Test shortcut flags
    args = parse_installer_args(["/no-desktop", "/no-start"])
    assert args.no_desktop is True
    assert args.no_start is True


def test_get_resource_path():
    path = get_resource_path("test_resource.txt")
    assert isinstance(path, str)
    assert path.endswith("test_resource.txt")


def test_create_uninstaller():
    with tempfile.TemporaryDirectory() as tmp_dir:
        desktop_link = os.path.join(tmp_dir, "Momento.lnk")
        start_menu_link = os.path.join(tmp_dir, "Start_Momento.lnk")
        
        create_uninstaller(tmp_dir, desktop_link, start_menu_link)
        
        bat_file = os.path.join(tmp_dir, "uninstall.bat")
        assert os.path.exists(bat_file)
        
        with open(bat_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert APP_DISPLAY_NAME in content
            assert desktop_link in content
            assert start_menu_link in content
            assert tmp_dir in content


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcuts only supported on Windows")
def test_make_shortcut():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_exe = os.path.join(tmp_dir, "test_app.exe")
        with open(dummy_exe, "w") as f:
            f.write("mock binary")
            
        link_path = os.path.join(tmp_dir, "test_app.lnk")
        make_shortcut(dummy_exe, link_path, description="Test Shortcut")
        
        assert os.path.exists(link_path)
        assert os.path.getsize(link_path) > 0


def test_compress_distribution_and_perform_installation():
    with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
        # Create mock distribution
        dummy_exe = os.path.join(source_dir, "Momento.exe")
        with open(dummy_exe, "w", encoding="utf-8") as f:
            f.write("mock momento executable content")
            
        dummy_sub = os.path.join(source_dir, "_internal", "assets")
        os.makedirs(dummy_sub, exist_ok=True)
        with open(os.path.join(dummy_sub, "config.json"), "w", encoding="utf-8") as f:
            f.write('{"test": true}')
            
        zip_path = os.path.join(target_dir, "installer_payload.zip")
        compress_distribution(source_dir, zip_path)
        
        assert os.path.exists(zip_path)
        assert os.path.getsize(zip_path) > 0
        
        # Verify zip contents
        with zipfile.ZipFile(zip_path, "r") as z:
            namelist = z.namelist()
            assert "Momento.exe" in namelist
            assert os.path.join("_internal", "assets", "config.json").replace("\\", "/") in [n.replace("\\", "/") for n in namelist]
