def test_smoke_imports():
    # Ensure project imports work even without full dependencies
    try:
        import src
    except Exception as e:
        raise AssertionError(f"Import failed: {e}")
