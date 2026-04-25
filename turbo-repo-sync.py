import xml.etree.ElementTree as ET
import os
import re
import subprocess
import concurrent.futures
import urllib.request
import time

MANIFEST_INPUT = os.getenv('MANIFEST_FILE', '.repo/manifests/default.xml')
DEST_DIR = os.getenv('DEST_DIR', '.')
PROJECT_OVERRIDES_STR = os.getenv('PROJECT_OVERRIDES', '')
INPUT_FILE = '/tmp/aria2_input.txt'

def is_hash(revision):
    return bool(re.match(r'^[0-9a-f]{7,40}$', revision))

def extract_project(zip_name, target_path, linkfiles, copyfiles):
    zip_path = f"/tmp/{zip_name}"
    temp_ext = f"/tmp/ext_{zip_name}"

    if not os.path.exists(zip_path):
        print(f"Error: {zip_path} not found!")
        return

    try:
        os.makedirs(target_path, exist_ok=True)

        # shopt -s dotglob ensures hidden files are moved
        extract_cmd = f'bash -c "shopt -s dotglob && unzip -q {zip_path} -d {temp_ext} && mv {temp_ext}/*/* {target_path}/"'
        subprocess.run(extract_cmd, shell=True, check=True)
        print(f"Extracted -> {target_path}")

        # Handle <copyfile> tags
        for src, dest in copyfiles:
            src_path = os.path.join(target_path, src)
            dest_path = os.path.join(DEST_DIR, dest)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            subprocess.run(['cp', src_path, dest_path], check=True)
            print(f"Copied {src} -> {dest}")

        # Handle <linkfile> tags
        for src, dest in linkfiles:
            src_abs = os.path.join(os.path.abspath(target_path), src)
            dest_path = os.path.join(DEST_DIR, dest)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            # Remove existing file/symlink to avoid FileExistsError
            if os.path.lexists(dest_path):
                os.remove(dest_path)

            os.symlink(src_abs, dest_path)
            print(f"Linked {dest} -> {src_abs}")

    except subprocess.CalledProcessError as e:
        print(f"Failed to extract/process {zip_name}: {e}")
    finally:
        subprocess.run(f'rm -rf {zip_path} {temp_ext}', shell=True)

def get_manifest_root(source):
    if source.startswith('http://') or source.startswith('https://'):
        print(f"Fetching manifest from URL: {source}")
        req = urllib.request.Request(source, headers={'User-Agent': 'Mozilla/5.0 (Turbo Repo Sync)'})
        with urllib.request.urlopen(req) as response:
            tree = ET.parse(response)
    else:
        print(f"Reading manifest from local path: {source}")
        if not os.path.exists(source):
            raise FileNotFoundError(f"Manifest file not found at: {source}")
        tree = ET.parse(source)
    return tree.getroot()

def main():
    root = get_manifest_root(MANIFEST_INPUT)

    remotes = {r.get('name'): r.get('fetch').rstrip('/') for r in root.findall('remote')}
    default_node = root.find('default')
    default_remote = default_node.get('remote') if default_node is not None else None
    default_revision = default_node.get('revision', 'master')

    # Parse the comma-separated overrides into a dictionary
    overrides = {}
    if PROJECT_OVERRIDES_STR:
        for item in PROJECT_OVERRIDES_STR.replace('\n', ',').split(','):
            if '=' in item:
                k, v = item.split('=', 1)
                overrides[k.strip()] = v.strip()

    extraction_tasks = []

    with open(INPUT_FILE, 'w') as f:
        for project in root.findall('project'):
            name = project.get('name')
            path = project.get('path', name)
            remote_name = project.get('remote', default_remote)

            revision = project.get('revision', default_revision)

            # Apply dynamic override [Equivalent of git checkout] :)
            if path in overrides and overrides[path]:
                print(f"[OVERRIDE] Changing {path} revision to: {overrides[path]}")
                revision = overrides[path]

            revision = revision.replace("refs/heads/", "")

            base_url = remotes.get(remote_name)
            if not base_url:
                continue

            ref_type = "hash" if is_hash(revision) else "branch"

            # For now I've added only GitHub and Codelinaro coz I need only these two for OnePlus kernel builds
            # Codelinaro UI very similar to GitLab so same logic ??
            # TODO: Add GitLab
            if "github.com" in base_url:
                if ref_type == "branch":
                    download_url = f"{base_url}/{name}/archive/refs/heads/{revision}.zip"
                else:
                    download_url = f"{base_url}/{name}/archive/{revision}.zip"
            elif "git.codelinaro.org" in base_url:
                project_basename = os.path.basename(name)
                if ref_type == "branch":
                    download_url = f"{base_url}/{name}/-/archive/{revision}/{project_basename}-{revision}.zip?ref_type=heads"
                else:
                    download_url = f"{base_url}/{name}/-/archive/{revision}/{project_basename}-{revision}.zip"
            else:
                continue

            zip_name = f"{name.replace('/', '_')}.zip"
            target_path = os.path.join(DEST_DIR, path)

            f.write(f"{download_url}\n")
            f.write(f"  dir=/tmp\n")
            f.write(f"  out={zip_name}\n")

            if "git.codelinaro.org" in base_url:
                f.write("  split=1\n")
                f.write("  max-connection-per-server=1\n")

            # Extract linkfiles and copyfiles
            linkfiles = [(link.get('src'), link.get('dest')) for link in project.findall('linkfile')]
            copyfiles = [(copy.get('src'), copy.get('dest')) for copy in project.findall('copyfile')]

            extraction_tasks.append((zip_name, target_path, linkfiles, copyfiles))

    print(f"Prepared {len(extraction_tasks)} repositories for download.")

    if not extraction_tasks:
        print("No valid projects found to download.")
        return

    # aria2c command arguments for maximum sppeed
    aria2_cmd = [
        'aria2c',
        '-i', INPUT_FILE,
        '-j', '8',
        '-x', '16',
        '-s', '16',
        '-k', '1M',
        '--allow-overwrite=true',
        '--console-log-level=error',
        '--summary-interval=0',
        '--file-allocation=none',
        '--continue=true'
    ]
    print("Starting fast multi-threaded downloads...")
    subprocess.run(aria2_cmd, check=True)

    print("Extracting archives...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as executor:
        for task in extraction_tasks:
            executor.submit(extract_project, *task)

if __name__ == "__main__":
    start_time = time.time()

    main()

    end_time = time.time()
    elapsed_seconds = int(end_time - start_time)

    minutes = elapsed_seconds // 60
    seconds = elapsed_seconds % 60

    if minutes > 0:
        time_str = f"{minutes}m {seconds}s"
    else:
        time_str = f"{seconds}s"

    print(f"\n[DEBUG] Repo sync completed in {time_str}")