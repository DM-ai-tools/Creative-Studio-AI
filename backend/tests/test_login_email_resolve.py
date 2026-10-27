from app.services.auth_service import login_email_candidates, resolve_login_email


def test_seedance_alias_resolves_to_full_email():
    assert resolve_login_email("seedance_2.5") == "seedance_2.5@creativestudio.tools"
    assert resolve_login_email("SEEDANCE_2.5") == "seedance_2.5@creativestudio.tools"


def test_login_candidates_include_legacy_local_part():
    candidates = login_email_candidates("seedance_2.5")
    assert candidates[0] == "seedance_2.5@creativestudio.tools"
    assert "seedance_2.5" in candidates
