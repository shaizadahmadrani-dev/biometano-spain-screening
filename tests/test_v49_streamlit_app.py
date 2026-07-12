from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "sergio_biometano_app" / "app.py"


def test_app_opens_both_v49_scales_without_exceptions():
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run(timeout=60)
    assert not app.exception
    assert app.radio[0].value == "Cobertura nacional · 5 km"
    assert "21.519" in app.warning[0].value
    national_metrics = {metric.label: metric.value for metric in app.metric}
    assert national_metrics["Evidencia de screening"] == "62%"
    assert national_metrics["Prefactibilidad"] == "no iniciada"

    app.radio[0].set_value("Refinamiento priorizado · 1 km").run(timeout=60)
    assert not app.exception
    assert "30.450" in app.warning[0].value
    refined_metrics = {metric.label: metric.value for metric in app.metric}
    assert refined_metrics["Evidencia de screening"] == "100%"
    assert refined_metrics["Prefactibilidad"] in {"no iniciada", "descartada"}

