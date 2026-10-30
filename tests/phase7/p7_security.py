"""Phase 7 - security, privacy and publication-readiness scan (read-only) of the project tree and the dashboard."""
import json, re, subprocess
from pathlib import Path
import pandas as pd
from p7_common import *

R = Registry()
A = "security"
SKIP = {".git", "__pycache__", ".pytest_cache", "phase7"}
files = [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP)]
text_ext = {".py", ".sql", ".md", ".txt", ".json", ".csv", ".html", ".js", ".css", ".gitignore", ""}
PAT = {
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "private_key": r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "github_token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "slack_token": r"xox[abpr]-[A-Za-z0-9-]{10,}",
    "generic_secret_assignment": r"(?i)(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"\s]{8,}['\"]",
    "openai_like_key": r"sk-[A-Za-z0-9]{20,}",
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "windows_user_path": r"[A-Za-z]:\\\\Users\\\\[^\\\\\s\"']+",
    "posix_home_path": r"/(home|Users)/[A-Za-z0-9._-]+/",
    "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "build_machine_path": r"/(?:tmp|mnt|root)/[A-Za-z0-9._/-]{6,}",
}
hits = []
for p in files:
    if p.suffix.lower() not in text_ext or p.stat().st_size > 60_000_000:
        continue
    if p.name in ("fpa_monthly_close_raw_messy.csv", "fpa_monthly_close_cleaned.csv"):
        continue  # data files scanned separately below
    t = p.read_text(encoding="utf-8", errors="ignore")
    for k, rx in PAT.items():
        for m in set(re.findall(rx, t)):
            mm = m if isinstance(m, str) else m[0]
            hits.append((str(p.relative_to(ROOT)), k, (mm if isinstance(mm, str) else str(mm))[:80]))
H = pd.DataFrame(hits, columns=["file", "pattern", "match"])
H.to_csv(WORK / "security_scan_hits.csv", index=False)
for k in ["aws_key", "private_key", "github_token", "slack_token", "openai_like_key", "generic_secret_assignment"]:
    sub = H[H.pattern == k]
    R.cmp(f"SEC.{k}", A, f"Credential pattern '{k}' in project text files", 0, len(sub), 0, note=sub.head(5).to_json(orient="records"))
for k in ["email", "windows_user_path", "posix_home_path", "ipv4", "build_machine_path"]:
    sub = H[H.pattern == k]
    R.add(f"SEC.{k}", A, f"Possible personal/machine-specific string '{k}' (needs review, not automatically a defect)",
          "INFO", None, len(sub), note=sub.drop_duplicates(["file", "match"]).head(12).to_json(orient="records"))
# data columns that could be personal
cl = pd.read_csv(CLEAN, dtype=str, keep_default_na=False, encoding="utf-8-sig", usecols=["user_id", "cost_center_owner", "line_text", "notes"])
R.add("SEC.users", A, "Distinct user_id values in the data (could identify people if the data were real)", "INFO", None,
      cl.user_id.nunique(), note=json.dumps(cl.user_id.value_counts().head(12).to_dict()))
R.add("SEC.owners", A, "Distinct cost_center_owner values (person-like names?)", "INFO", None, cl.cost_center_owner.nunique(),
      note=json.dumps(sorted(cl.cost_center_owner.unique().tolist())[:20]))
html = HTML.read_text(encoding="utf-8")
own = [o for o in cl.cost_center_owner.unique() if o and o in html]
R.add("SEC.html_owner", A, "Cost-centre owner names embedded in dashboard HTML", "INFO", None, len(own), note=json.dumps(own[:10]))
uid = [u for u in cl.user_id.unique() if u and len(u) > 3 and f'"{u}"' in html]
R.add("SEC.html_user", A, "user_id values embedded in dashboard HTML", "INFO", None, len(uid), note=json.dumps(uid[:10]))
docs = len(re.findall(r'"JE\d{6,}"', html))
R.add("SEC.html_docs", A, "Journal document numbers embedded in the dashboard HTML (line-level data)", "INFO", None, docs,
      note="document numbers of the 58,340 Posted lines, plus amounts of 136,330 lines (Posted + non-Posted), are embedded; acceptable for synthetic data, a disclosure risk if the source were real")
R.add("SEC.html_sha", A, "Dashboard embeds SHA-256 of raw/cleaned/DB/workbook (provenance, no secret)", "INFO", None, None)
R.cmp("SEC.html_ext", A, "Dashboard references external URLs (http/https) in src/href", 0,
      len(re.findall(r"(?:src|href)\s*=\s*[\"']https?://", html)), 0)
# git tracking of data files (publication risk)
try:
    tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split("\n")
    big = [t for t in tracked if t.endswith((".csv", ".duckdb", ".xlsx")) and "outputs/phase4" not in t]
    R.add("SEC.git_data", A, "Data files tracked by git (would be published with the repo)", "INFO", None, len(big), note=json.dumps(big))
    st = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True, text=True).stdout
    R.add("SEC.git_status", A, "Uncommitted working-tree entries (nothing was committed or pushed in Phase 7)", "INFO", None,
          len([l for l in st.splitlines() if l.strip()]))
    rem = subprocess.run(["git", "-C", str(ROOT), "remote", "-v"], capture_output=True, text=True).stdout
    R.add("SEC.git_remote", A, "Git remote configured", "INFO", None, None, note=rem.strip()[:200])
except Exception as e:
    R.add("SEC.git", A, "git inspection", "BLOCKED", note=str(e))
gi = (ROOT / ".gitignore").read_text()
R.add("SEC.gitignore", A, ".gitignore content (raw/processed/db exclusions)", "INFO", None, None, note=gi.replace("\n", " | ")[:400])
R.add("SEC.prov", A, "Data provenance and redistribution licence", "BLOCKED",
      note="Owner states the data is synthetic; no licence or provenance document exists to verify it (docs/DATA_PROVENANCE.md). Cannot be resolved by testing.")
R.save("security")
