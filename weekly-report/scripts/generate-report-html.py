#!/usr/bin/env python3.11
"""
generate-report-html.py — Weekly report data generator.

Reads collect-weekly-data.py JSON output, merges commentary/highlights/suggestions,
and produces a JSON data file. The HTML template (templates/weekly-report.html) 
renders the data client-side.

Usage:
    python3.11 collect-weekly-data.py ... | python3.11 generate-report-html.py --output weekly-data-2026-04-13.html
    python3.11 generate-report-html.py --data-file data.json --output weekly-data-2026-04-13.html

Also writes weekly-data-latest.html alongside --output for default URL access.
Optionally copies the HTML template to --template-output.
"""

import argparse, json, sys, os, shutil


def main():
    parser = argparse.ArgumentParser(description='Generate weekly report data JSON from collected data.')
    parser.add_argument('--output', '-o', required=True, help='Output JSON file path')
    parser.add_argument('--data-file', help='JSON data file (default: read from stdin)')
    parser.add_argument('--template-output', help='Copy HTML template to this path')
    parser.add_argument('--commentary', help='JSON object with section commentaries')
    parser.add_argument('--highlights', help='JSON array of highlight strings')
    parser.add_argument('--suggestions', help='JSON array of suggestion strings')
    parser.add_argument('--plan-rate', type=float, default=0.5, help='Planned weight loss rate kg/week')
    parser.add_argument('--username', help='Username for navigation URLs')
    parser.add_argument('--nickname', help='User nickname to display in header')
    parser.add_argument('--tagline', help='Short fun summary line for header')
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

    # Merge everything into one output object
    # Validate: warn if commentary/highlights/suggestions are empty
    if not commentary or not any(commentary.values()):
        print("[generate-report-html] WARNING: commentary is empty — report will show without section analysis", file=sys.stderr)
    if not highlights:
        print("[generate-report-html] WARNING: highlights is empty — report will use fallback text", file=sys.stderr)
    if not suggestions:
        print("[generate-report-html] WARNING: suggestions is empty — report will use fallback text", file=sys.stderr)

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
    print(f"[generate-report-html] Written {out_size} bytes to {args.output}")

    # Write latest copy only if this is the most recent week
    # Compare against existing latest to avoid overwriting newer data with older
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
                print(f"[generate-report-html] Skipped latest update (existing {existing_start} > current {current_start})")
        except (json.JSONDecodeError, IOError):
            pass  # overwrite if existing is corrupt

    if should_update_latest:
        shutil.copy2(args.output, latest_path)
        print(f"[generate-report-html] Copied to {latest_path}")

    # Always copy template to workspace reports dir (ensures it exists for upload)
    template_src = os.path.join(os.path.dirname(__file__), '..', 'templates', 'weekly-report.html')
    template_src = os.path.abspath(template_src)
    out_dir = os.path.dirname(os.path.abspath(args.output))
    default_template_dest = os.path.join(out_dir, 'weekly-report.html')

    if os.path.exists(template_src):
        shutil.copy2(template_src, default_template_dest)

    # Copy template if explicit path requested
    if args.template_output:
        if os.path.exists(template_src):
            os.makedirs(os.path.dirname(os.path.abspath(args.template_output)), exist_ok=True)
            shutil.copy2(template_src, args.template_output)
            print(f"[generate-report-html] Template copied to {args.template_output}")
        else:
            print(f"[generate-report-html] WARNING: template not found at {template_src}", file=sys.stderr)


if __name__ == '__main__':
    main()
