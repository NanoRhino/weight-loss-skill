# Archived skills

Skills moved here are NOT discovered by openclaw at runtime (`collectSkillTargets` walks the parent skills directory at maxDepth=1 only, and `.archived/` itself has no SKILL.md).

Files are kept for reference. To restore, `git mv .archived/<name> ../<name>`.

## Archive log

- **2026-06-03**: `jdcloud-oss-upload` archived. Operator FuZhuoRan decided to remove all JD Cloud OSS code paths in favor of AWS S3 only. Reason: weekly-report 5/24 incident traced to upload-to-s3.sh fallback logic picking wrong cloud backend (jdoss bucket `nanorhino-im-plans` does not exist; only AWS does). Future plan-export uploads go to AWS S3 exclusively.
