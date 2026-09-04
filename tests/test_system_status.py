from railblock.system_status import check_system_status


def test_check_system_status_returns_one_record_per_engine():
    results = check_system_status()
    components = {r["component"] for r in results}
    assert components == {
        "CP-SAT Optimizer",
        "Validation Engine",
        "Risk Engine",
        "Coordination Engine",
        "Re-planning",
        "Simulation Engine",
        "Digital Twin",
    }


def test_check_system_status_reports_ready_for_every_bundled_engine():
    results = check_system_status()
    for record in results:
        assert record["status"] == "READY", f"{record['component']} was not READY: {record['status']}"


def test_check_system_status_never_claims_external_connectivity():
    results = check_system_status()
    forbidden_terms = ["connected", "live railway", "kavach", "tms", "smms", "tdms"]
    for record in results:
        lowered = record["status"].lower()
        for term in forbidden_terms:
            assert term not in lowered
