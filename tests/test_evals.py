from agent_code_review.evals import load_manifest, render_eval_table, run_evals


def test_manifest_shape(samples_dir):
    manifest = load_manifest(samples_dir)
    assert set(manifest) == {"clean_pr", "buggy_pr", "security_pr"}
    assert manifest["clean_pr"] == []
    assert len(manifest["buggy_pr"]) == 7
    assert len(manifest["security_pr"]) == 3


def test_eval_mock_numbers(samples_dir):
    evals = {e.sample: e for e in run_evals(samples_dir)}

    buggy = evals["buggy_pr"]
    # 6 of 7 seeded defects are mechanically detectable; the off-by-one
    # needs the LLM layer, so mock recall is honestly 6/7.
    assert buggy.found == 6
    assert buggy.recall == 6 / 7
    assert buggy.precision == 1.0
    assert buggy.severity_accuracy == 1.0
    assert len(buggy.missed) == 1
    assert "off-by-one" in buggy.missed[0]

    clean = evals["clean_pr"]
    assert clean.blockers == 0
    assert clean.false_positives == 0
    assert clean.precision == 1.0

    security = evals["security_pr"]
    assert security.recall == 1.0
    assert security.blockers == 3


def test_eval_table_renders(samples_dir):
    table = render_eval_table(run_evals(samples_dir))
    assert "| buggy_pr | 7 | 6 | 0.857 | 1.000 | 1.000 | 2 |" in table
    assert "**overall**" in table
    assert "0.900" in table  # overall recall 9/10
