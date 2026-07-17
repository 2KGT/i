#!/usr/bin/env python3
"""
clean.py — Dọn dẹp repo (Reset lịch sử commit, xóa run cũ và cache).
"""

import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

# Thêm SCRIPTS_DIR vào path để import notify
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

try:
    import notify as _notify
except ImportError:
    _notify = None

def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Chạy lệnh hệ thống"""
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False, text=True)
    if check and result.returncode != 0:
        print(f"❌ Thất bại (exit {result.returncode}): {' '.join(cmd)}")
        sys.exit(result.returncode)
    return result

def gh_api(path: str, method: str = "GET", token: str = "") -> dict | list | None:
    """Gọi GitHub REST API"""
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"⚠️ GitHub API {method} {path} → HTTP {e.code}")
        return None
    except Exception as e:
        print(f"⚠️ GitHub API lỗi: {e}")
        return None

def clean_logs():
    print("\n" + "=" * 55)
    print("🗑️  BẮT ĐẦU DỌN DẸP: Reset commit history + xóa workflow runs + cache")
    print("=" * 55)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    repo  = os.environ.get("GITHUB_REPOSITORY", "")
    current_run_id = os.environ.get("GITHUB_RUN_ID", "")

    if not token or not repo:
        print("❌ Thiếu GH_TOKEN hoặc GITHUB_REPOSITORY")
        sys.exit(1)

    # ── BƯỚC 1: Reset lịch sử commit ──────────────────────
    print("\n🧽 Bước 1: Reset lịch sử commit...")
    run(["git", "config", "--global", "user.name",  "github-actions[bot]"])
    run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"])

    run(["git", "checkout", "--orphan", "temp_clean_branch"])
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", "🚀 Initial Clean Repository Base [skip ci]"])
    run(["git", "branch", "-D", "main"])
    run(["git", "branch", "-m", "main"])
    run(["git", "push", "origin", "main", "--force"])
    print("✅ Đã reset lịch sử commit về trạng thái sạch!")

    # ── BƯỚC 2: Xóa workflow runs cũ ──────────────────────
    print("\n🗑️  Bước 2: Xóa các workflow runs đã hoàn thành cũ...")
    all_runs = []
    page = 1
    while page <= 10:
        data = gh_api(
            f"/repos/{repo}/actions/runs?status=completed&per_page=100&page={page}",
            token=token,
        )
        if not data or not data.get("workflow_runs"):
            break
        all_runs.extend(data.get("workflow_runs", []))
        if len(data.get("workflow_runs", [])) < 100:
            break
        page += 1

    deleted = 0
    skipped = 0
    for r in all_runs:
        run_id = str(r.get("id", ""))
        if run_id == current_run_id:
            skipped += 1
            continue
        gh_api(f"/repos/{repo}/actions/runs/{run_id}", method="DELETE", token=token)
        deleted += 1

    print(f"✅ Đã xóa {deleted} workflow runs (bỏ qua {skipped} run hiện tại).")

    # ── BƯỚC 3: Xóa cache Actions ──────────────────────────
    print("\n🗄️  Bước 3: Xóa cache cũ...")
    cache_data = gh_api(f"/repos/{repo}/actions/caches?per_page=100", token=token)
    caches = cache_data.get("actions_caches", []) if cache_data else []

    if not caches:
        print("ℹ️  Không có cache nào cần xóa.")
    else:
        for c in caches:
            cache_id = c.get("id")
            if cache_id:
                gh_api(f"/repos/{repo}/actions/caches/{cache_id}", method="DELETE", token=token)
        print(f"✅ Đã xóa {len(caches)} cache Actions.")

    return True

def main():
    run_logs = os.environ.get("RUN_CLEAN_LOGS", "false").lower() == "true"

    if not run_logs:
        print("ℹ️  Tính năng dọn dẹp không được kích hoạt.")
        sys.exit(0)

    success = True
    try:
        clean_logs()
    except SystemExit:
        success = False
        raise
    finally:
        if _notify:
            _notify.notify_clean(False, run_logs, success)
        else:
            print(f"📢 [Clean Status] Hoàn thành dọn dẹp repo. Kết quả: {success}")

if __name__ == "__main__":
    main()
