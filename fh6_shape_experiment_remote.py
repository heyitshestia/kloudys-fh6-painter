import argparse
import base64
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SYNC_FILES = (
    "fh6_shape_experiment.py",
    "fh6_probe.py",
    "main.py",
)


def run_checked(cmd, input_text=None, cwd=None):
    print("$", " ".join(cmd), flush=True)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True if input_text is not None else None,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def powershell_path(path):
    return str(path).replace("/", "\\")


def powershell_quote(value):
    return "'" + value.replace("'", "''") + "'"


def powershell_encoded(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def upload_file(host, local_path, remote_path):
    remote_spec = f"{host}:/C:/{remote_path[3:].replace('\\', '/')}"
    run_checked(["scp", "-i", "/home/hestia/.ssh/id_ed25519", str(local_path), remote_spec])


def sync_files(host, remote_root):
    for relative in SYNC_FILES:
        local_path = ROOT / relative
        remote_path = powershell_path(Path(remote_root) / relative)
        upload_file(host, local_path, remote_path)


def remote_python_command(remote_root, remote_args, python_cmd):
    script_path = powershell_path(Path(remote_root) / "fh6_shape_experiment.py")
    joined = " ".join(powershell_quote(arg) for arg in remote_args)
    return f"& {python_cmd} {powershell_quote(script_path)} {joined}"


def parse_args():
    parser = argparse.ArgumentParser(description="Run FH6 shape experiments on the Windows machine over SSH.")
    parser.add_argument("--host", default="hestia@192.168.0.241")
    parser.add_argument("--remote-root", default=r"C:\Users\Hestia\Desktop\forza-painter-fh6-main")
    parser.add_argument("--python-cmd", default="py -3")
    parser.add_argument("--no-sync", action="store_true", help="Skip uploading local experiment/probe/importer files before running.")
    parser.add_argument("remote_args", nargs=argparse.REMAINDER, help="Arguments forwarded to fh6_shape_experiment.py on Windows.")
    return parser.parse_args()


def main():
    args = parse_args()
    remote_args = args.remote_args
    if remote_args and remote_args[0] == "--":
        remote_args = remote_args[1:]
    if not remote_args:
        raise SystemExit("Pass the remote fh6_shape_experiment.py arguments after --.")

    if not args.no_sync:
        sync_files(args.host, args.remote_root)

    command = remote_python_command(args.remote_root, remote_args, args.python_cmd)
    run_checked(
        ["ssh", "-i", "/home/hestia/.ssh/id_ed25519", args.host, "powershell", "-NoProfile", "-EncodedCommand", powershell_encoded(command)]
    )


if __name__ == "__main__":
    main()
