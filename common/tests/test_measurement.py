from common.measurement import PassCallMeasurement, RunMeasurementHeader


def test_passcallmeasurement_fields():
    m = PassCallMeasurement(
        run_id="r1", source_id="KDB/raw/a.md", pass_="pass2",
        provider="deepseek", model="deepseek-v4-flash", prompt_version="2.0",
        final_status="clean", attempts=1, syntax_repaired=False, slug_coerced=False,
        token_overrun=False, total_input_tokens=100, total_output_tokens=50,
        total_latency_ms=1200, call_count=1, final_attempt_index=1, source_words=400,
        parse_ok=True, schema_ok=True, semantic_ok=True,
    )
    assert m.pass_ == "pass2" and m.final_status == "clean"


def test_runheader_fields():
    h = RunMeasurementHeader(
        run_id="r1", corpus_fingerprint="sha", pass1_prompt_version="1.1",
        pass2_prompt_version="2.0", scanned=36, to_compile=36, signal=29,
        noise=7, p1_attempted=36, p2_attempted=29)
    assert h.signal == 29
