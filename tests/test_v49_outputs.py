import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sergio_biometano_app" / "data"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_outputs():
    national = pd.read_parquet(DATA / "sergio_cells_v49_national_5km.parquet")
    refined = pd.read_parquet(DATA / "sergio_cells_v49_refined_1km.parquet")
    return national, refined


def test_v49_has_explicit_national_and_refined_scopes():
    national, refined = load_outputs()
    assert len(national) == national["cell_id"].nunique() == 21_519
    assert len(refined) == refined["cell_id"].nunique() == 30_450
    assert national["grid_level"].eq("cobertura nacional 5 km").all()
    assert refined["grid_level"].eq("refinamiento 1 km").all()
    assert national["national_universe"].all()
    assert not refined["national_universe"].any()


def test_nitrates_are_preserved_as_digestate_risk_not_sole_hard_veto():
    _, refined = load_outputs()
    nitrate = refined["nitrate_intersects"].fillna(False).astype(bool)
    assert int(nitrate.sum()) == 15_830
    assert refined.loc[nitrate, "digestate_risk"].eq("alto").all()

    hard = refined["hard_veto"].fillna(False).astype(bool)
    reasons = refined["veto_reasons"].fillna("[]").astype(str).str.lower()
    nitrate_only = hard & reasons.str.contains("nitr") & ~reasons.str.contains(
        "built|urban|natura|agua|slope|pendiente|físic|fisic", regex=True
    )
    assert int(nitrate_only.sum()) == 0


def test_prefeasibility_is_not_inferred_from_screening_proxies():
    national, refined = load_outputs()
    assert not national["prefeasibility_status"].eq("prefactible").any()
    assert not refined["prefeasibility_status"].eq("prefactible").any()
    assert refined["missing_critical_gates"].astype(str).str.len().gt(2).all()


def test_nearest_operating_plant_is_recomputed_for_every_refined_cell():
    _, refined = load_outputs()
    assert refined["nearest_operating_biomethane_plant_distance_km"].notna().all()
    assert refined["nearest_operating_biomethane_plant_name"].nunique() == 24


def test_manifest_hashes_match_distributed_v49_snapshots():
    manifest_path = DATA / "provenance_manifest_v49.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    distributed = {
        relative_path: expected
        for relative_path, expected in manifest["outputs"].items()
        if (ROOT / relative_path).exists()
    }
    assert set(distributed) == {
        "sergio_biometano_app/data/sergio_cells_v49_national_5km.parquet",
        "sergio_biometano_app/data/sergio_cells_v49_refined_1km.parquet",
    }
    for relative_path, expected in distributed.items():
        assert sha256(ROOT / relative_path) == expected
