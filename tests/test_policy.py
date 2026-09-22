from brainbox_os.policy import Risk, speculative_allowed

def test_safe_speculation():
    assert speculative_allowed(Risk.READ, False)
    assert speculative_allowed(Risk.PREPARE, False)

def test_risky_speculation_requires_confirmation():
    assert not speculative_allowed(Risk.WRITE, False)
    assert not speculative_allowed(Risk.EXTERNAL, False)
    assert not speculative_allowed(Risk.DESTRUCTIVE, False)
    assert speculative_allowed(Risk.WRITE, True)
