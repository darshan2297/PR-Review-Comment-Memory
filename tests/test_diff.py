from team_coding_dna import retrieval

SAMPLE_DIFF = """diff --git a/billing/charge.py b/billing/charge.py
index 1234567..89abcde 100644
--- a/billing/charge.py
+++ b/billing/charge.py
@@ -1,3 +1,4 @@
-amount = 19.99
+amount = Decimal("19.99")
diff --git a/web/app.ts b/web/app.ts
--- a/web/app.ts
+++ b/web/app.ts
@@ -0,0 +1 @@
+console.log("hi")
"""


def test_extract_changed_paths():
    paths = retrieval.extract_changed_paths(SAMPLE_DIFF)
    assert "billing/charge.py" in paths
    assert "web/app.ts" in paths
    # de-duplicated even though +++/--- repeat the path
    assert paths.count("billing/charge.py") == 1


def test_detect_languages():
    langs = retrieval.detect_languages(["billing/charge.py", "web/app.ts", "x.unknown"])
    assert langs == {"python", "typescript"}


def test_path_matches_globs():
    assert retrieval.path_matches("billing/**", "billing/charge.py")
    assert retrieval.path_matches("billing/**", "billing/sub/dir/x.py")
    assert not retrieval.path_matches("billing/*", "billing/sub/x.py")
    # bare name matches anywhere
    assert retrieval.path_matches("*.py", "billing/charge.py")


def test_handles_paths_only_diff():
    diff = "--- a/api/routes.py\n+++ b/api/routes.py\n"
    assert retrieval.extract_changed_paths(diff) == ["api/routes.py"]
