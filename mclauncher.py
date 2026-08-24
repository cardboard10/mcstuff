#!/usr/bin/env python3
import os
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile
import urllib.request

# ==============================
# CONFIG
# ==============================
MC_DIR = Path.home() / ".minecraft"
JAVA_PATH = "java"
USERNAME = "<YOUR_USERNAME>"
ACCESS_TOKEN = "<YOUR_ACCESS_TOKEN>"
UUID = "<YOUR_UUID>"
USER_TYPE = "mojang"

# ==============================
# UTILS
# ==============================
def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        print(f"Downloading {url} → {dest}")
        urllib.request.urlretrieve(url, dest)
    else:
        print(f"Already exists: {dest}")

def extract_natives(zip_path, target_dir):
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Extracting natives from {zip_path} → {target_dir}")
    with ZipFile(zip_path, "r") as zipf:
        zipf.extractall(target_dir)

def jar_contains_main(jar_path, main_class):
    if not jar_path.exists():
        return False
    try:
        with ZipFile(jar_path, "r") as zf:
            expected = main_class.replace(".", "/") + ".class"
            return any(expected == f or f.endswith(expected) for f in zf.namelist())
    except:
        return False

def get_main_class(version):
    try:
        parts = version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        if major == 1 and minor < 6:
            return "Minecraft"  # old versions
    except ValueError:
        # Non-numeric or snapshot versions
        pass
    return "net.minecraft.client.main.Main"  # modern versions

def is_old_version(version):
    """Returns True if the version is pre-1.6."""
    try:
        parts = version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        return major == 1 and minor < 6
    except ValueError:
        return False

# ==============================
# MAIN LAUNCHER LOGIC
# ==============================
def fetch_manifest():
    url = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
    manifest = json.loads(urllib.request.urlopen(url).read())
    return manifest

def select_version(manifest):
    versions = [v["id"] for v in manifest["versions"]]
    print("\nAvailable Minecraft Versions:")
    print(", ".join(versions))
    while True:
        version = input("\nEnter the version to launch: ").strip()
        if version in versions:
            return version
        print("Invalid version. Please choose from the list above.")

def fetch_version_json(version):
    manifest = fetch_manifest()
    version_info = next(v for v in manifest["versions"] if v["id"] == version)
    version_json = json.loads(urllib.request.urlopen(version_info["url"]).read())
    return version_json

def download_client_and_libs(version_json, version):
    client_path = MC_DIR / "versions" / version / f"{version}.jar"
    client_url = version_json["downloads"]["client"]["url"]
    download(client_url, client_path)

    lib_paths = []
    native_dir = MC_DIR / "versions" / version / "natives"

    for lib in version_json.get("libraries", []):
        downloads = lib.get("downloads", {})
        artifact = downloads.get("artifact")
        if artifact:
            path = MC_DIR / "libraries" / artifact["path"]
            download(artifact["url"], path)
            lib_paths.append(path)

        # Natives
        natives = lib.get("natives", {})
        classifiers = downloads.get("classifiers", {})
        for os_name in ["linux", "windows", "osx"]:
            if os_name in natives:
                classifier_name = natives[os_name]
                native_info = classifiers.get(f"{classifier_name}.jar")
                if native_info:
                    native_path = MC_DIR / "libraries" / native_info["path"]
                    download(native_info["url"], native_path)
                    extract_natives(native_path, native_dir)
                else:
                    print(f"[INFO] No {os_name} native for {lib.get('name')}, skipping.")

    return client_path, lib_paths, native_dir

def build_classpath(client_path, lib_paths):
    sep = ":" if os.name != "nt" else ";"
    all_paths = [str(p.resolve()) for p in lib_paths] + [str(client_path.resolve())]
    classpath = sep.join(all_paths)
    print("\n[DEBUG] Classpath built:")
    print(classpath)
    return classpath

def build_jvm_args(classpath, native_dir, main_class):
    return [
        JAVA_PATH,
        f"-Djava.library.path={native_dir.resolve()}",
        "-Xmx2G",
        "-cp", classpath,
        main_class,
        "-Dorg.lwjgl.util.Debug=true",
        "-Dorg.lwjgl.util.DebugLoader=true"
    ]

def build_game_args(version_json, version):
    return [
        "--username", USERNAME,
        "--version", version,
        "--gameDir", str(MC_DIR.resolve()),
        "--assetsDir", str((MC_DIR / "assets").resolve()),
        "--assetIndex", version_json["assetIndex"]["id"],
        "--uuid", UUID,
        "--accessToken", ACCESS_TOKEN,
        "--userType", USER_TYPE
    ]

def check_files_exist(client_path, lib_paths, main_class, version):
    missing = []
    if not client_path.exists():
        missing.append(client_path)
    elif not is_old_version(version) and not jar_contains_main(client_path, main_class):
        print(f"[ERROR] Client JAR does not contain {main_class}")
        missing.append(client_path)

    for p in lib_paths:
        if not p.exists():
            missing.append(p)

    if missing:
        print("\n[ERROR] The following required files are missing or invalid:")
        for m in missing:
            print(m)
        if is_old_version(version):
            print("\n[INFO] Pre-1.6 versions may require manual LWJGL natives extraction.")
        return False
    return True

# ==============================
# MAIN
# ==============================
def main():
    manifest = fetch_manifest()
    version = select_version(manifest)
    version_json = fetch_version_json(version)
    main_class = get_main_class(version)

    client_path, lib_paths, native_dir = download_client_and_libs(version_json, version)

    if not check_files_exist(client_path, lib_paths, main_class, version):
        print("\nPlease download missing/corrupted files and try again.")
        return

    classpath = build_classpath(client_path, lib_paths)
    jvm_args = build_jvm_args(classpath, native_dir, main_class)
    game_args = build_game_args(version_json, version)

    print("\nFull Java Launch Command:")
    print(" ".join(jvm_args + game_args))

    print("\nLaunching Minecraft...")
    subprocess.run(jvm_args + game_args)

if __name__ == "__main__":
    main()
