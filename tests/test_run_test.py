import sys
import pytest
from unittest.mock import patch, MagicMock

def test_run_test_import_has_no_side_effects():
    """
    Regression Test for DEF-012:
    Verifies that importing `run_test` does NOT access sys.argv[1] or start a workload,
    even when sys.argv contains no arguments.
    """
    with patch.object(sys, "argv", ["run_test.py"]):
        # Import should succeed without raising IndexError
        import run_test
        assert hasattr(run_test, "run")
        assert callable(run_test.run)

def test_run_test_missing_argument_exits_cleanly(capsys):
    """
    Verifies that invoking run() without arguments prints usage and exits cleanly with code 1.
    """
    import run_test
    with patch.object(sys, "argv", ["run_test.py"]):
        with pytest.raises(SystemExit) as exc_info:
            run_test.run()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Usage: python run_test.py <profile_name>" in captured.out

def test_run_test_nonexistent_profile_exits_cleanly(capsys):
    """
    Verifies that invoking run() with a non-existent profile prints a message and exits with code 1.
    """
    import run_test
    with patch.object(sys, "argv", ["run_test.py", "profile_that_does_not_exist"]):
        with pytest.raises(SystemExit) as exc_info:
            run_test.run()
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Profile not found" in captured.out

def test_run_test_launches_locust_with_correct_args():
    """
    Verifies that invoking run('normal_day') builds the expected Locust command line and env.
    """
    import run_test
    with patch("subprocess.run") as mock_subprocess_run:
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        
        res = run_test.run("normal_day")
        assert mock_subprocess_run.called
        call_args, call_kwargs = mock_subprocess_run.call_args
        
        cmd = call_args[0]
        assert cmd[0] == "locust"
        assert "--host" in cmd
        assert "http://127.0.0.1:8000" in cmd
        assert "--csv" in cmd
        assert "results_normal_day" in cmd
        assert call_kwargs["env"]["LOCUST_PROFILE"] == "profiles\\normal_day.yaml" or call_kwargs["env"]["LOCUST_PROFILE"] == "profiles/normal_day.yaml"
