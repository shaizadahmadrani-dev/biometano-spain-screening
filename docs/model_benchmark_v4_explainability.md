# Explainability benchmark v4

Top features per model. En models lineals, el signe indica direcció després d'escalar; en arbres, és importància relativa.

Caveat: en arbres, `feature_importances_` és importància relativa basada en splits/impuresa; no és efecte causal ni estabilitat garantida, especialment amb variables correlacionades.

| model | feature | importance_type | value | abs_value | direction |
| --- | --- | --- | --- | --- | --- |
| gradient_boosting | TOT_P_2021 | tree_feature_importance | 0.24265 | 0.24265 | importance |
| gradient_boosting | cereals_production_ths_t_2024 | tree_feature_importance | 0.22003 | 0.22003 | importance |
| gradient_boosting | bio1_annual_mean_temp_c | tree_feature_importance | 0.08991 | 0.08991 | importance |
| gradient_boosting | bio15_precipitation_seasonality | tree_feature_importance | 0.06802 | 0.06802 | importance |
| gradient_boosting | worldcover2021_share_tree_cover_sample25 | tree_feature_importance | 0.04124 | 0.04124 | importance |
| gradient_boosting | nearest_wwtp_dist_km | tree_feature_importance | 0.03411 | 0.03411 | importance |
| gradient_boosting | nearest_ggit_operating_gas_pipeline_dist_km_mediterranean_v4 | tree_feature_importance | 0.03394 | 0.03394 | importance |
| gradient_boosting | DIST_COAST | tree_feature_importance | 0.02994 | 0.02994 | importance |
| gradient_boosting | bovine_lsu_2023 | tree_feature_importance | 0.02963 | 0.02963 | importance |
| gradient_boosting | bio6_min_temp_coldest_month_c | tree_feature_importance | 0.02722 | 0.02722 | importance |
| gradient_boosting | bio5_max_temp_warmest_month_c | tree_feature_importance | 0.02600 | 0.02600 | importance |
| gradient_boosting | DIST_BORD | tree_feature_importance | 0.02287 | 0.02287 | importance |
| linear_svm | nearest_wwtp_dist_km | scaled_coefficient | -1.90858 | 1.90858 | negative |
| linear_svm | nearest_ggit_operating_gas_pipeline_dist_km_mediterranean_v4 | scaled_coefficient | -0.88030 | 0.88030 | negative |
| linear_svm | cereals_production_ths_t_2024 | scaled_coefficient | 0.72654 | 0.72654 | positive |
| linear_svm | arable_main_area_ths_ha_2024 | scaled_coefficient | -0.69440 | 0.69440 | negative |
| linear_svm | bio1_annual_mean_temp_c | scaled_coefficient | 0.58758 | 0.58758 | positive |
| linear_svm | bio5_max_temp_warmest_month_c | scaled_coefficient | -0.40864 | 0.40864 | negative |
| linear_svm | bio12_annual_precip_mm | scaled_coefficient | -0.36878 | 0.36878 | negative |
| linear_svm | worldcover2021_share_tree_cover_sample25 | scaled_coefficient | -0.33510 | 0.33510 | negative |
| linear_svm | wwtp_wastewater_treated_sum_cell | scaled_coefficient | -0.24896 | 0.24896 | negative |
| linear_svm | DIST_BORD | scaled_coefficient | 0.19208 | 0.19208 | positive |
| linear_svm | bio15_precipitation_seasonality | scaled_coefficient | -0.19109 | 0.19109 | negative |
| linear_svm | LAND_PC | scaled_coefficient | 0.18954 | 0.18954 | positive |
| logistic_regression | nearest_wwtp_dist_km | scaled_coefficient | -3.20522 | 3.20522 | negative |
| logistic_regression | nearest_ggit_operating_gas_pipeline_dist_km_mediterranean_v4 | scaled_coefficient | -1.62843 | 1.62843 | negative |
| logistic_regression | worldcover2021_share_tree_cover_sample25 | scaled_coefficient | -1.09031 | 1.09031 | negative |
| logistic_regression | bio12_annual_precip_mm | scaled_coefficient | -0.82165 | 0.82165 | negative |
| logistic_regression | bio5_max_temp_warmest_month_c | scaled_coefficient | -0.72211 | 0.72211 | negative |
| logistic_regression | bio1_annual_mean_temp_c | scaled_coefficient | 0.63100 | 0.63100 | positive |
| logistic_regression | cereals_production_ths_t_2024 | scaled_coefficient | 0.61925 | 0.61925 | positive |
| logistic_regression | bio15_precipitation_seasonality | scaled_coefficient | -0.58308 | 0.58308 | negative |
| logistic_regression | worldcover2021_share_shrubland_sample25 | scaled_coefficient | -0.54984 | 0.54984 | negative |
| logistic_regression | arable_main_area_ths_ha_2024 | scaled_coefficient | -0.54593 | 0.54593 | negative |
| logistic_regression | LAND_PC | scaled_coefficient | 0.51722 | 0.51722 | positive |
| logistic_regression | worldcover2021_share_grassland_sample25 | scaled_coefficient | -0.51505 | 0.51505 | negative |
| random_forest | TOT_P_2021 | tree_feature_importance | 0.13906 | 0.13906 | importance |
| random_forest | bio1_annual_mean_temp_c | tree_feature_importance | 0.08587 | 0.08587 | importance |
| random_forest | bio15_precipitation_seasonality | tree_feature_importance | 0.07013 | 0.07013 | importance |
| random_forest | cereals_production_ths_t_2024 | tree_feature_importance | 0.06690 | 0.06690 | importance |
| random_forest | nearest_wwtp_dist_km | tree_feature_importance | 0.06273 | 0.06273 | importance |
| random_forest | bio6_min_temp_coldest_month_c | tree_feature_importance | 0.05841 | 0.05841 | importance |
| random_forest | bio5_max_temp_warmest_month_c | tree_feature_importance | 0.05732 | 0.05732 | importance |
| random_forest | nearest_ggit_operating_gas_pipeline_dist_km_mediterranean_v4 | tree_feature_importance | 0.04622 | 0.04622 | importance |
| random_forest | DIST_COAST | tree_feature_importance | 0.04619 | 0.04619 | importance |
| random_forest | DIST_BORD | tree_feature_importance | 0.04407 | 0.04407 | importance |
| random_forest | bio12_annual_precip_mm | tree_feature_importance | 0.04398 | 0.04398 | importance |
| random_forest | arable_main_area_ths_ha_2024 | tree_feature_importance | 0.04136 | 0.04136 | importance |
