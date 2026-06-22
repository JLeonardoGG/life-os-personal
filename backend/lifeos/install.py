from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
from pathlib import Path

from lifeos.config import get_settings

LABEL = "com.lifeos.personal"


def launch_agent_path() -> Path:
    return Path("~/Library/LaunchAgents/com.lifeos.personal.plist").expanduser()


def build_launch_agent() -> dict:
    settings = get_settings()
    python = settings.project_root / ".venv" / "bin" / "python"
    if not python.exists():
        raise RuntimeError("No existe .venv. Ejecuta primero scripts/install-local.command")
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            "-m",
            "uvicorn",
            "lifeos.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(settings.port),
        ],
        "WorkingDirectory": str(settings.project_root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Interactive",
        "StandardOutPath": str(settings.logs_dir / "lifeos.out.log"),
        "StandardErrorPath": str(settings.logs_dir / "lifeos.err.log"),
        "EnvironmentVariables": {
            "LIFE_OS_DATA_DIR": str(settings.data_dir),
            "PATH": f"{settings.project_root / '.venv' / 'bin'}:/usr/bin:/bin:/usr/sbin:/sbin",
        },
    }


def install_launch_agent(load: bool = True) -> Path:
    path = launch_agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        plistlib.dump(build_launch_agent(), handle, sort_keys=True)
    path.chmod(0o600)
    if load:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(path)], check=False, capture_output=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
        subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], check=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Instala Life OS como servicio local de macOS.")
    parser.add_argument("--no-load", action="store_true", help="Escribe el plist sin iniciarlo.")
    args = parser.parse_args()
    path = install_launch_agent(load=not args.no_load)
    print(f"LaunchAgent instalado: {path}")
    print("Life OS: http://127.0.0.1:8765")
