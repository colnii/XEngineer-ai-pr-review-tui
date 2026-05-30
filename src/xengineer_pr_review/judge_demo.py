from __future__ import annotations

from xengineer_pr_review.diff_parser import parse_unified_diff
from xengineer_pr_review.models import PullRequestData, PullRequestRef


JUDGE_DEMO_URL = "https://github.com/colnii/xengineer-demo/pull/7"

JUDGE_DEMO_DIFF = """diff --git a/src/xengineer/reviewer.py b/src/xengineer/reviewer.py
index 1111111..2222222 100644
--- a/src/xengineer/reviewer.py
+++ b/src/xengineer/reviewer.py
@@ -1,6 +1,16 @@
 def summarize_pr(files):
-    return "Review pending"
+    risky_files = [path for path in files if "config" in path or "auth" in path]
+    if risky_files:
+        return f"Review {len(files)} files; risky files: {', '.join(risky_files)}"
+    return f"Review {len(files)} files"
+
+
+def build_review_checklist(files):
+    return {
+        "changed_files": len(files),
+        "needs_tests": any(path.endswith(".py") for path in files),
+    }
diff --git a/src/xengineer/config.py b/src/xengineer/config.py
index 3333333..4444444 100644
--- a/src/xengineer/config.py
+++ b/src/xengineer/config.py
@@ -1,4 +1,6 @@
 REVIEW_TIMEOUT_SECONDS = 20
+MODEL_TIMEOUT_SECONDS = 45
+ALLOW_JUDGE_DEMO = True
diff --git a/tests/test_reviewer.py b/tests/test_reviewer.py
new file mode 100644
index 0000000..5555555
--- /dev/null
+++ b/tests/test_reviewer.py
@@ -0,0 +1,8 @@
+from xengineer.reviewer import build_review_checklist
+
+
+def test_build_review_checklist_marks_python_changes_as_test_needed():
+    checklist = build_review_checklist(["src/xengineer/reviewer.py"])
+
+    assert checklist["changed_files"] == 1
+    assert checklist["needs_tests"] is True
diff --git a/README.md b/README.md
index 6666666..7777777 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,7 @@
 # XEngineer Demo
+
+## Judge Demo
+
+Run `xpr-review --judge-demo` to open a deterministic review demo without API keys.
"""


class JudgeDemoGitHubClient:
    def fetch_pr(self, ref: PullRequestRef) -> PullRequestData:
        return PullRequestData(
            ref=ref,
            title="Add zero-config judge review demo",
            author="xengineer-demo-bot",
            base_branch="main",
            head_branch="feature/judge-demo",
            files=parse_unified_diff(JUDGE_DEMO_DIFF),
            diff_text=JUDGE_DEMO_DIFF,
        )
