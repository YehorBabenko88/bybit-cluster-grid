"""Pure builder policy tests: no native code, process/token or infrastructure effects."""
import pytest
from tools.python_containment_bundle import relative, hosted

@pytest.mark.parametrize("name", ["../a", "a/../b", "/a", "C:/a", "a\\b", "A:ads", "a//b", "a/", "CON", "x/NUL.py", "x. ", "x\x00.py"])
def test_alias_or_traversal_refused(name):
    with pytest.raises(ValueError): relative(name)

@pytest.mark.parametrize("name", ["python.exe", "DLLs/_socket.pyd", "Site/pkg/__init__.py", "Source/grid/coordinator.py"])
def test_canonical_relative_path(name): assert relative(name)==name

@pytest.mark.parametrize("changed", ["GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "GITHUB_REPOSITORY", "GITHUB_JOB", "EXACT_HEAD_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"])
def test_hosted_context_missing_refused(monkeypatch,changed):
    context=dict(GITHUB_ACTIONS="true",RUNNER_ENVIRONMENT="github-hosted",GITHUB_REPOSITORY="YehorBabenko88/bybit-cluster-grid",GITHUB_JOB="python-containment",EXACT_HEAD_SHA="a"*40,GITHUB_RUN_ID="12",GITHUB_RUN_ATTEMPT="1")
    for k,v in context.items():monkeypatch.setenv(k,v)
    monkeypatch.delenv(changed,raising=False)
    with pytest.raises(ValueError):hosted()
