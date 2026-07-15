# Turbo Repo Sync
[![Ask DeepWiki](https://devin.ai/assets/askdeepwiki.png)](https://deepwiki.com/nullptr-t-oss/turbo-repo-sync)

A GitHub Action that provides a significantly faster alternative to the standard `repo sync` command for Android-style manifest-based projects. It parses a local or remote `manifest.xml`, downloads project source code as ZIP/TAR archives concurrently using `aria2c`, and extracts them to the specified workspace.

## Features

- **Blazing Fast Syncs**: Leverages `aria2c` for concurrent, multi-connection downloads, dramatically reducing the time it takes to sync a large number of repositories compared to a traditional `git clone`.
- **Flexible Manifest Location**: Fetches the `manifest.xml` from a local path within your repository or directly from a URL.
- **Project Overrides**: Easily specify different branches or commit hashes for individual projects without modifying the manifest file.
- **Manifest Tag Support**: Correctly processes `<copyfile>` and `<linkfile>` tags to set up your workspace as intended.
- **Git LFS Handling**: Automatically falls back to a standard `git clone` for projects marked with `lfs="true"` to ensure large files are handled correctly.
- **Multi-Forge Support**: Constructs appropriate archive download URLs for GitHub, Codelinaro (CAF), and AOSP (android.googlesource.com).
- **Robust Downloads**: Includes a retry mechanism to handle intermittent network issues.

## Usage

Integrate this action into your GitHub Workflows to quickly set up your source tree for building or testing.

```yaml
name: Build Android
on:
  workflow_dispatch:

jobs:
  sync_and_build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Sync Sources with Turbo Repo Sync
        uses: nullptr-t-oss/turbo-repo-sync@main
        with:
          # URL to a remote manifest file
          manifest_path: 'https://github.com/my-org/manifests/raw/main/default.xml'
          
          # Root directory for a local manifest
          # manifest_path: '.repo/manifests/default.xml'
          
          # Directory to extract projects into
          workspace_dir: '.'
          
          # Override specific project revisions
          project_overrides: 'kernel/msm-4.14=my-feature-branch, prebuilts/clang/host/linux-x86=a1b2c3d'

      - name: Continue with build steps...
        run: |
          echo "Sources are synced!"
          ls -l kernel/msm-4.14
```

## Inputs

| Input               | Description                                                                                                    | Required | Default                           |
| ------------------- | -------------------------------------------------------------------------------------------------------------- | -------- | --------------------------------- |
| `manifest_path`     | Local path or HTTP/HTTPS URL to the `manifest.xml` file.                                                       | `true`   | `.repo/manifests/default.xml`     |
| `workspace_dir`     | The root directory where projects should be extracted.                                                         | `true`   | `.`                               |
| `project_overrides` | A comma-separated list of `path=revision` pairs to override the revision specified in the manifest for a project. | `false`  | `''` (empty string)               |

### `project_overrides` Examples

You can override revisions for one or more projects using a comma-separated string. The `path` a project is extracted to is used as the key.

- **Override a branch for a kernel project:**
  `kernel/oneplus/sm8250=twelve`

- **Override a commit hash for a toolchain project:**
  `prebuilts/clang/host/linux-x86=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2`

- **Combine multiple overrides:**
  `kernel/oneplus/sm8250=twelve,vendor/oneplus=a1b2c3d`

## How It Works

1.  **Parse Manifest**: The action reads the specified `manifest.xml`, identifying all remotes and projects.
2.  **Apply Overrides**: It checks for any `project_overrides` and updates the target revision for the specified projects.
3.  **Generate Download URLs**: For each project, it constructs a direct download URL for a source archive (`.zip` or `.tar.gz`) based on the remote (GitHub, AOSP, Codelinaro) and the target revision.
4.  **Concurrent Download**: It feeds all generated URLs into `aria2c`, which downloads the archives in parallel using multiple connections per download for maximum speed.
5.  **Concurrent Extraction**: After downloads are complete, it extracts all archives into their target paths in parallel using a thread pool.
6.  **Process Links**: Finally, it processes any `<copyfile>` and `<linkfile>` tags from the manifest to create the necessary file copies and symbolic links.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
