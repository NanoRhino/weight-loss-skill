#!/usr/bin/env python3.11
"""
generate-report-html.py — Weekly report data generator + uploader.

Reads collect-weekly-data.py JSON output, merges commentary/highlights/suggestions,
produces a JSON data file, uploads to cloud storage, and writes a report log.

Usage:
    python3.11 collect-weekly-data.py ... | python3.11 generate-report-html.py \
        --output weekly-data-2026-04-13.html --workspace-dir /path/to/workspace

Outputs the public report URL to stdout (for agent to use in message).

Flags:
    --no-upload   Skip cloud upload (local testing)
    --no-log      Skip writing report log (e.g., backfilling history)
"""

import argparse, json, sys, os, shutil, subprocess
from datetime import datetime, timezone


def log(msg):
    print(f"[generate-report-html] {msg}", file=sys.stderr)


def _find_upload_script():
    """Find upload-to-s3.sh relative to this script's location."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # skills/weekly-report/scripts/ → skills/plan-export/scripts/upload-to-s3.sh
    upload_path = os.path.join(script_dir, '..', '..', 'plan-export', 'scripts', 'upload-to-s3.sh')
    upload_path = os.path.abspath(upload_path)
    if os.path.exists(upload_path):
        return upload_path
    return None


def _upload_file(upload_script, file_path, key, workspace_dir, bucket="nanorhino-im-plans"):
    """Upload a file using upload-to-s3.sh. Returns public URL or None."""
    cmd = [
        "bash", upload_script,
        "--file", file_path,
        "--bucket", bucket,
        "--key", key,
        "--workspace", workspace_dir,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            url = result.stdout.strip().split('\n')[-1]  # last line is URL
            log(f"Uploaded {key} → {url}")
            return url
        else:
            log(f"Upload failed for {key}: {result.stderr.strip()}")
            return None
    except subprocess.TimeoutExpired:
        log(f"Upload timed out for {key}")
        return None
    except Exception as e:
        log(f"Upload error for {key}: {e}")
        return None


def _write_report_log(workspace_dir, data, url):
    """Write report log JSON for cross-session reference."""
    start_date = data.get('meta', {}).get('start_date', 'unknown')
    log_dir = os.path.join(workspace_dir, 'data', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f'weekly-report-{start_date}.json')

    summary = data.get('summary', {})
    commentary = data.get('commentary', {})
    report_log = {
        'start_date': start_date,
        'end_date': data.get('meta', {}).get('end_date', ''),
        'week_number': data.get('meta', {}).get('week_number', 0),
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'url': url or '',
        'summary': {
            'logged_days': summary.get('logged_days', 0),
            'cal_avg': summary.get('cal_avg', 0),
            'cal_avg_estimated': summary.get('cal_avg_estimated', 0),
            'weight_change': summary.get('weight_change'),
            'protein_avg': summary.get('protein_avg', 0),
            'fat_avg': summary.get('fat_avg', 0),
            'carb_avg': summary.get('carb_avg', 0),
        },
        'commentary': commentary,
        'highlights': data.get('highlights', []),
        'suggestions': data.get('suggestions', []),
        'nickname': data.get('nickname', ''),
        'tagline': data.get('tagline', ''),
    }

    with open(log_path, 'w') as f:
        json.dump(report_log, f, ensure_ascii=False, indent=2)
    log(f"Report log written to {log_path}")
    return log_path


def main():
    parser = argparse.ArgumentParser(description='Generate weekly report data JSON, upload, and log.')
    parser.add_argument('--output', '-o', required=True, help='Output JSON file path')
    parser.add_argument('--data-file', help='JSON data file (default: read from stdin)')
    parser.add_argument('--workspace-dir', help='Workspace directory (for upload + log)')
    parser.add_argument('--template-output', help='Copy HTML template to this path')
    parser.add_argument('--commentary', help='JSON object with section commentaries')
    parser.add_argument('--highlights', help='JSON array of highlight strings')
    parser.add_argument('--suggestions', help='JSON array of suggestion strings')
    parser.add_argument('--plan-rate', type=float, default=0.5, help='Planned weight loss rate kg/week')
    parser.add_argument('--username', help='Username for navigation URLs')
    parser.add_argument('--nickname', help='User nickname to display in header')
    parser.add_argument('--tagline', help='Short fun summary line for header')
    parser.add_argument('--no-upload', action='store_true', help='Skip cloud upload')
    parser.add_argument('--no-log', action='store_true', help='Skip writing report log')
    args = parser.parse_args()

    # Read input data
    if args.data_file:
        with open(args.data_file) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    # Parse optional args
    commentary = {}
    if args.commentary:
        try:
            commentary = json.loads(args.commentary)
        except:
            pass

    highlights = []
    if args.highlights:
        try:
            highlights = json.loads(args.highlights)
        except:
            pass

    suggestions = []
    if args.suggestions:
        try:
            suggestions = json.loads(args.suggestions)
        except:
            pass

    # Validate: warn if commentary/highlights/suggestions are empty
    if not commentary or not any(commentary.values()):
        log("WARNING: commentary is empty — report will show without section analysis")
    if not highlights:
        log("WARNING: highlights is empty — report will use fallback text")
    if not suggestions:
        log("WARNING: suggestions is empty — report will use fallback text")

    data['commentary'] = commentary
    data['highlights'] = highlights
    data['suggestions'] = suggestions
    data['nickname'] = args.nickname or ''
    data['tagline'] = args.tagline or ''
    data['plan_rate'] = args.plan_rate
    data['username'] = args.username or 'unknown'

    # Write output JSON
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    out_size = os.path.getsize(args.output)
    log(f"Written {out_size} bytes to {args.output}")

    # Write latest copy only if this is the most recent week
    out_dir = os.path.dirname(os.path.abspath(args.output))
    latest_path = os.path.join(out_dir, 'weekly-data-latest.html')
    should_update_latest = True
    if os.path.exists(latest_path):
        try:
            with open(latest_path) as f:
                existing = json.load(f)
            existing_start = existing.get('meta', {}).get('start_date', '')
            current_start = data.get('meta', {}).get('start_date', '')
            if existing_start and current_start and current_start < existing_start:
                should_update_latest = False
                log(f"Skipped latest update (existing {existing_start} > current {current_start})")
        except (json.JSONDecodeError, IOError):
            pass

    if should_update_latest:
        shutil.copy2(args.output, latest_path)
        log(f"Copied to {latest_path}")

    # Backfill: set prev week's next_exists = true
    prev_start = data.get('meta', {}).get('prev_start', '')
    if prev_start:
        prev_path = os.path.join(out_dir, f'weekly-data-{prev_start}.html')
        if os.path.exists(prev_path):
            try:
                with open(prev_path) as f:
                    prev_data = json.load(f)
                if not prev_data.get('meta', {}).get('next_exists', False):
                    prev_data['meta']['next_exists'] = True
                    with open(prev_path, 'w') as f:
                        json.dump(prev_data, f, ensure_ascii=False, indent=2)
                    log(f"Backfilled next_exists=true in {prev_path}")
            except (json.JSONDecodeError, IOError) as e:
                log(f"WARNING: could not backfill prev week {prev_path}: {e}")

    # Always copy template to workspace reports dir
    template_src = os.path.join(os.path.dirname(__file__), '..', 'templates', 'weekly-report.html')
    template_src = os.path.abspath(template_src)
    default_template_dest = os.path.join(out_dir, 'weekly-report.html')

    if os.path.exists(template_src):
        shutil.copy2(template_src, default_template_dest)

    if args.template_output:
        if os.path.exists(template_src):
            os.makedirs(os.path.dirname(os.path.abspath(args.template_output)), exist_ok=True)
            shutil.copy2(template_src, args.template_output)
            log(f"Template copied to {args.template_output}")
        else:
            log(f"WARNING: template not found at {template_src}")

    # === Upload to cloud storage ===
    report_url = None
    start_date = data.get('meta', {}).get('start_date', '')
    workspace_dir = args.workspace_dir

    # Auto-detect workspace from output path if not provided
    # output is typically {workspace}/data/reports/weekly-data-{date}.html
    if not workspace_dir:
        # Try to walk up from output dir: data/reports/ → data/ → workspace/
        candidate = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(args.output))))
        if os.path.isdir(os.path.join(candidate, 'data')):
            workspace_dir = candidate
            log(f"Auto-detected workspace: {workspace_dir}")

    if not args.no_upload and workspace_dir:
        upload_script = _find_upload_script()
        if not upload_script:
            log("WARNING: upload-to-s3.sh not found, skipping upload")
        else:
            log("Starting cloud upload...")

            # 1. Upload dated data file
            data_url = _upload_file(upload_script, args.output,
                                    f"weekly-data-{start_date}", workspace_dir)

            # 2. Upload latest (if updated)
            if should_update_latest:
                _upload_file(upload_script, latest_path,
                             "weekly-data-latest", workspace_dir)

            # 3. Upload HTML template
            if os.path.exists(default_template_dest):
                _upload_file(upload_script, default_template_dest,
                             "weekly-report", workspace_dir)

            # 4. Upload prev week data if backfilled
            if prev_start:
                prev_path_upload = os.path.join(out_dir, f'weekly-data-{prev_start}.html')
                if os.path.exists(prev_path_upload):
                    _upload_file(upload_script, prev_path_upload,
                                 f"weekly-data-{prev_start}", workspace_dir)

            # Build report URL
            if data_url:
                # data_url is like https://nanorhino.ai/user/x5l8ro/weekly-data-2026-04-20.html
                # report URL is https://nanorhino.ai/user/x5l8ro/weekly-report.html?week=2026-04-20
                base = data_url.rsplit('/weekly-data-', 1)[0]
                report_url = f"{base}/weekly-report.html?week={start_date}"
    elif args.no_upload:
        log("Upload skipped (--no-upload)")
    else:
        log("WARNING: no workspace-dir, skipping upload")

    # === Write report log ===
    if not args.no_log and workspace_dir:
        _write_report_log(workspace_dir, data, report_url)
    elif args.no_log:
        log("Report log skipped (--no-log)")

    # === Output URL to stdout ===
    if report_url:
        print(report_url)
    else:
        # Fallback: print local file path
        print(os.path.abspath(args.output))


if __name__ == '__main__':
    main()
