#!/usr/bin/env python3
"""
dataguard — block customer data, PII, and secrets from being committed to Git.

Keeps the rule "data lives in the database, not in the repo" enforceable instead
of just aspirational. Pure Python standard library — no pip installs, runs the
same on a dev laptop (pre-commit) and in CI (GitHub Actions).

Usage:
  python dataguard.py --staged          # scan files staged for commit (pre-commit hook)
  python dataguard.py --all             # scan every tracked file (full audit)
  python dataguard.py PATH [PATH ...]   # scan explicit files or directories
  python dataguard.py --changed BASE    # scan files changed vs BASE ref (CI on a PR/push)

Flags:
  --strict   treat PII found in source code (not just data files) as an error too
  --quiet    only print on failure

Exit code 0 = clean, 1 = violations found (blocks the commit / fails CI).

Tune behavior with a .dataguardignore file at the repo root (gitignore-style
globs, one per line) to allow-list known-safe paths (e.g. upstream CI helpers).
"""
import sys, os, re, json, zipfile, subprocess, fnmatch

# ───────────────────────── configuration ──────────────────────────────────

# Fixtures may ONLY export configuration/schema doctypes. Anything else is data.
# Default-deny: a doctype not in this set (and not ending in "Settings") is flagged.
ALLOWED_FIXTURE_DOCTYPES = {
    "custom field", "property setter", "client script", "server script",
    "workspace", "print format", "print style", "letter head", "notification",
    "role", "custom docperm", "crm fields layout", "translation", "workflow",
    "workflow state", "workflow action master", "report", "dashboard",
    "dashboard chart", "number card", "module onboarding", "onboarding step",
    "custom html block", "web form", "email template", "workflow action",
}

# Files that are secrets/config/dumps and must never be committed.
SECRET_FILE_GLOBS = [
    "*.env", ".env", ".env.*", "site_config.json", "*.pem", "*.key", "*.p12",
    "*.pfx", "id_rsa", "id_dsa", "*.sql", "*.sqlite", "*.sqlite3", "*.db",
    "*.bak", "*.dump", "credentials.json", "service-account*.json",
]
# …but these are templates / upstream CI helpers and are allowed.
SECRET_FILE_ALLOW = [
    "*.env.example", "*.env.sample", "*.env.template", "*.env.dist",
    "*/.github/helper/site_config.json", ".github/helper/site_config.json",
]

# High-confidence secret content patterns (low false-positive).
SECRET_CONTENT = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\btoken\s+[0-9a-f]{12,}:[0-9a-f]{12,}"), "Frappe api_key:api_secret"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"), "Slack token"),
    (re.compile(r"gh[pousr]_[0-9A-Za-z]{30,}"), "GitHub token"),
    (re.compile(r"(?i)\b(api_secret|api_key|secret_key|access_token|auth_token|passwd|password)\b\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"),
     "hardcoded secret/password"),
]
SECRET_PLACEHOLDERS = {
    "test", "admin", "root", "changeme", "password", "123", "1234", "12345",
    "123456", "example", "your_password", "your-secret", "yoursecret", "xxxx",
    "xxxxxxxx", "placeholder", "none", "null", "true", "false", "dummy",
    "secret", "redacted", "<your-secret>", "***",
}

# PII signals.
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?1[-.\s])?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)")
EXAMPLE_EMAIL_DOMAINS = (
    "example.com", "example.org", "example.net", "test.com", "frappe.io",
    "localhost", "domain.com", "email.com", "yoursite.com", "mail.com",
    "sentry.io", "company.com", "acme.com",
)
EXAMPLE_EMAIL_LOCAL = (
    "test", "noreply", "no-reply", "admin", "user", "you", "name", "email",
    "support", "info", "hello", "demo", "example", "someone", "first.last",
)

# Never scan these (binary, vendored, generated).
SKIP_DIR = {".git", "node_modules", "dist", "build", ".yarn", "__pycache__",
            ".venv", "env", "venv", ".next", "coverage", "vendor"}
SKIP_GLOBS = [
    "*.min.js", "*.min.css", "*.map", "*.lock", "package-lock.json",
    "yarn.lock", "*.po", "*.mo", "*.pot", "*.woff*", "*.ttf", "*.eot",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico", "*.svg", "*.pdf", "*.zip",
    "*.gz", "*.mp4", "*.webp", "*.otf", "dataguard.py",
]
MAX_BYTES = 3_000_000  # don't read content of files larger than this

# ───────────────────────── helpers ────────────────────────────────────────

def sh(args):
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""

def repo_root():
    r = sh(["git", "rev-parse", "--show-toplevel"]).strip()
    return r or os.getcwd()

def load_ignore(root):
    pats = []
    p = os.path.join(root, ".dataguardignore")
    if os.path.isfile(p):
        for line in open(p, encoding="utf-8", errors="ignore"):
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line)
    return pats

def matches(path, globs):
    name = os.path.basename(path)
    norm = path.replace("\\", "/")
    for g in globs:
        if fnmatch.fnmatch(name, g) or fnmatch.fnmatch(norm, g) or fnmatch.fnmatch(norm, "*/" + g):
            return True
    return False

def should_skip(path, ignore):
    norm = path.replace("\\", "/")
    parts = set(norm.split("/"))
    if parts & SKIP_DIR:
        return True
    if matches(path, SKIP_GLOBS):
        return True
    if matches(path, ignore):
        return True
    return False

def read_text(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return ""
        with open(path, "rb") as f:
            return f.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

def real_emails(text):
    out = []
    for e in EMAIL.findall(text):
        local, _, dom = e.partition("@")
        dom = dom.lower()
        if any(dom == d or dom.endswith("." + d) for d in EXAMPLE_EMAIL_DOMAINS):
            continue
        if local.lower() in EXAMPLE_EMAIL_LOCAL:
            continue
        out.append(e)
    return sorted(set(out))

def real_phones(text):
    return sorted(set(PHONE.findall(text)))

def xlsx_text(path):
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return ""
    parts = []
    for n in z.namelist():
        if n.startswith("xl/sharedStrings") or (n.startswith("xl/worksheets/") and n.endswith(".xml")):
            try:
                raw = z.read(n).decode("utf-8", errors="ignore")
                parts.append(re.sub(r"<[^>]+>", " ", raw))  # strip XML tags
            except Exception:
                pass
    return " ".join(parts)

# ───────────────────────── checks ─────────────────────────────────────────

def check_fixture(path, findings):
    """Fixtures must export only config/schema doctypes, never business records."""
    norm = path.replace("\\", "/")
    if "/fixtures/" not in norm or not norm.endswith(".json"):
        return
    txt = read_text(path)
    if not txt.strip():
        return
    try:
        data = json.loads(txt)
    except Exception:
        findings.append(("WARN", path, "fixtures file is not valid JSON (could not verify)"))
        return
    records = data if isinstance(data, list) else [data]
    seen = {}
    for rec in records:
        if isinstance(rec, dict):
            dt = (rec.get("doctype") or "").strip()
            if not dt:
                # infer from filename: custom_field.json -> Custom Field
                dt = os.path.basename(path)[:-5].replace("_", " ").title()
            seen[dt.lower()] = dt
    for dt_l, dt in seen.items():
        if not (dt_l in ALLOWED_FIXTURE_DOCTYPES or dt_l.endswith("settings")):
            findings.append(("ERROR", path,
                f"fixture exports records of business doctype '{dt}' - data belongs in the DB, not Git"))
    # PII inside fixtures is always a hard fail regardless of doctype
    em, ph = real_emails(txt), real_phones(txt)
    if em:
        findings.append(("ERROR", path, f"fixture contains email PII: {', '.join(em[:5])}"))
    if ph:
        findings.append(("ERROR", path, f"fixture contains phone PII: {', '.join(ph[:5])}"))

def check_secret_file(path, findings):
    if matches(path, SECRET_FILE_ALLOW):
        return
    if matches(path, SECRET_FILE_GLOBS):
        findings.append(("ERROR", path,
            "secret/config/dump file must not be committed (use .env.example or keep it out of Git)"))

def check_secret_content(path, findings):
    if matches(path, SECRET_FILE_GLOBS) or path.replace("\\", "/").endswith(".env"):
        return  # already flagged as a file
    txt = read_text(path)
    if not txt:
        return
    for rx, label in SECRET_CONTENT:
        for m in rx.finditer(txt):
            val = m.groups()[-1] if m.groups() else m.group(0)
            if val and val.strip().lower() in SECRET_PLACEHOLDERS:
                continue
            if val and re.search(r"\{\{|\$\{|<[^>]+>|YOUR_|xxxx", val):  # template tokens
                continue
            findings.append(("ERROR", path, f"possible {label}: '{val[:24]}…'"))
            break

def check_spreadsheet(path, findings):
    norm = path.replace("\\", "/").lower()
    if norm.endswith((".xlsx", ".xls")):
        text = xlsx_text(path)
    elif norm.endswith(".csv"):
        text = read_text(path)
    else:
        return
    em, ph = real_emails(text), real_phones(text)
    if em or ph:
        bits = (["emails: " + ", ".join(em[:3])] if em else []) + (["phones: " + ", ".join(ph[:3])] if ph else [])
        findings.append(("ERROR", path,
            f"spreadsheet/CSV contains real data ({'; '.join(bits)}) - keep only blank templates in Git"))

def check_source_pii(path, findings, strict):
    """Real emails/phones hardcoded in source (e.g. a seeder). Warn by default."""
    norm = path.replace("\\", "/").lower()
    if "/fixtures/" in norm or norm.endswith((".xlsx", ".xls", ".csv")):
        return  # handled by stricter checks
    if not norm.endswith((".py", ".js", ".ts", ".vue", ".json", ".md", ".txt", ".yaml", ".yml", ".html")):
        return
    txt = read_text(path)
    if not txt:
        return
    # ignore commit co-author trailers and obvious doc placeholders
    txt = re.sub(r"(?im)^.*co-authored-by:.*$", "", txt)
    em, ph = real_emails(txt), real_phones(txt)
    if em or ph:
        sev = "ERROR" if strict else "WARN"
        bits = (["emails: " + ", ".join(em[:3])] if em else []) + (["phones: " + ", ".join(ph[:3])] if ph else [])
        findings.append((sev, path,
            f"real PII in source ({'; '.join(bits)}) - confirm it is not customer data (hardcoded seeder?)"))

# ───────────────────────── driver ─────────────────────────────────────────

def gather(args):
    if "--staged" in args:
        out = sh(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"])
        return [l for l in out.splitlines() if l.strip()]
    if "--all" in args:
        return [l for l in sh(["git", "ls-files"]).splitlines() if l.strip()]
    if "--changed" in args:
        base = args[args.index("--changed") + 1]
        out = sh(["git", "diff", "--name-only", "--diff-filter=ACM", base + "...HEAD"])
        return [l for l in out.splitlines() if l.strip()]
    paths = [a for a in args if not a.startswith("--")]
    files = []
    for p in paths:
        if os.path.isdir(p):
            for dp, dn, fn in os.walk(p):
                dn[:] = [d for d in dn if d not in SKIP_DIR]
                for f in fn:
                    files.append(os.path.join(dp, f))
        elif os.path.isfile(p):
            files.append(p)
    return files

def main():
    args = sys.argv[1:]
    if not args:
        print("usage: dataguard.py [--staged|--all|--changed BASE|PATH...] [--strict] [--quiet]")
        return 2
    strict = "--strict" in args
    quiet = "--quiet" in args
    root = repo_root()
    ignore = load_ignore(root)

    files = gather(args)
    findings = []
    for path in files:
        if not os.path.isfile(path):
            continue
        if should_skip(path, ignore):
            continue
        check_fixture(path, findings)
        check_secret_file(path, findings)
        check_secret_content(path, findings)
        check_spreadsheet(path, findings)
        check_source_pii(path, findings, strict)

    errors = [f for f in findings if f[0] == "ERROR"]
    warns = [f for f in findings if f[0] == "WARN"]

    if findings:
        print("\n[dataguard] potential data/secret leaks:\n")
        for sev, path, msg in errors + warns:
            tag = "[BLOCK]" if sev == "ERROR" else "[warn] "
            print(f"  {tag} {path}\n          {msg}")
        print()
    if errors:
        print(f"BLOCKED: {len(errors)} data-leak violation(s). Fix them, or allow-list a "
              f"verified-safe path in .dataguardignore.\n")
        return 1
    if warns and not quiet:
        print(f"[dataguard] {len(warns)} warning(s) - not blocking.\n")
    elif not quiet:
        print(f"[dataguard] OK - scanned {len(files)} file(s), no data leaks found.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
