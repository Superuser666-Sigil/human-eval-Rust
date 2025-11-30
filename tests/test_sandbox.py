from human_eval import sandbox


def test_firejail_security_opts_present():
    assert "--seccomp" in sandbox.FIREJAIL_SECURITY_OPTS
    assert "--caps.drop=all" in sandbox.FIREJAIL_SECURITY_OPTS
