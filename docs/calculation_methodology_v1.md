# 計算方法論 v1（Calculation Methodology）

日期：2026-08-13<br>
範圍：Stage 4 GHG 計算覆蓋（電力回歸、燃料多氣體、官方 114 年度熱值、NG 子類型）

本文件描述**實際程式行為**。

## 精度與進位

- 中間運算一律使用 `Decimal`，不對 kcal、TJ、氣體質量或 GWP 加權結果做提前進位。
- 引擎輸出的 `calculated_kgco2e` / `calculated_tco2e` 為該 Decimal 結果轉成 IEEE float（與既有電力路徑相同）。
- 儀表板／報表的顯示格式屬於呈現層，不回寫計算結果。
- 測試以獨立 Decimal 公式重算期望值，再以受控容差比對。

## 公式家族

| formula_id | version | 用途 |
|---|---|---|
| `activity_value_times_direct_co2e_factor` | `1.0` | 外購電力：活動量 × 直接 CO2e 係數 |
| `fuel_activity_to_energy_to_multigas_co2e` | `1.0` | 燃料：活動量 × 熱值 → TJ → CO2/CH4/N2O × GWP |

不得把燃料計算重用電力公式 ID。

## 外購電力

```
kgCO2e = activity_kWh × factor_kgCO2e_per_kWh
tCO2e  = kgCO2e / 1000
```

- 2024 demo：`0.474 kgCO2e/kWh` → 50000 kWh → **23700 kgCO2e / 23.7 tCO2e**
- 2025 企業盤查／揭露：僅在活動用途可對應 `industrial_enterprise_inventory`（例如廠場 `process_use`）時使用 `0.466`
- `0.467` 售電平均與 `0.471` 住宅係數不得因「最新年度」被默默代入
- 用途／費率脈絡不明時 fail-safe：不匹配、不計算

## 天然氣（固定燃燒）

```
kcal = activity_m3 × low_heating_value_kcal_per_m3
TJ   = kcal × (registry kcal→TJ multiplier, 4.1868e-9)
CO2_kg = TJ × 56100
CH4_kg = TJ × 1
N2O_kg = TJ × 0.1
kgCO2e = CO2_kg×1 + CH4_kg×28 + N2O_kg×265
tCO2e  = kgCO2e / 1000
```

計算使用**低位熱值**。官方高位熱值一併保存，不自行用 90% 重算一個略有不同的低位值。

| 子類型 | 高位熱值 | 低位熱值（計算用） |
|--------|----------|-------------------|
| NG1 | 8963 kcal/m3 | 8067 kcal/m3 |
| NG2 | 9698 kcal/m3 | 8728 kcal/m3 |

公告說明 NG1／NG2 低位熱值係依 2006 IPCC 氣體燃料建議比例 90%，由高位熱值計算而得。本系統直接採用公告給出的低位值。

### 天然氣類型為強制條件

- `natural_gas` + NG1 → 可匹配 8067 kcal/m3
- `natural_gas` + NG2 → 可匹配 8728 kcal/m3
- `natural_gas` + 未知／空白 → **不得猜測**，回傳 `blocked_natural_gas_type_required`
- 無效子類型 → 驗證／審查失敗（`factor_match_inconsistent`）

不得從公司名稱、地區、用量、供應商（除非已有 verified 對照）、歷史平均或「較合理的結果」推論 NG1／NG2。

客戶文案：「請確認天然氣類型（NG1 或 NG2），才能套用正確熱值。」

## 柴油（移動燃燒／公司車）

```
kcal = activity_L × 8636
TJ   = kcal × 4.1868e-9
CO2_kg = TJ × 74100
CH4_kg = TJ × 3.9
N2O_kg = TJ × 3.9
kgCO2e = CO2_kg×1 + CH4_kg×28 + N2O_kg×265
tCO2e  = kgCO2e / 1000
```

非 `process_use=company_vehicle` 的柴油不走公司車移動燃燒路徑。

## 熱值選取

條件：燃料種類 + **活動日曆年** + 地理 + `status=ready` + 完整官方 provenance；天然氣另加 **fuel_subtype**。

- 114年度熱值只適用活動年 **2025**
- 沒有剛好一年的 verified 熱值 → `blocked_missing_conversion`
- 同一年多筆衝突 ready 熱值 → `blocked_ambiguous_conversion`（不取最新）
- 跨年活動期間 → 不匹配
- 不得以「最新可用」跨年回退

kcal→TJ 必須來自 `engineering_conversions.csv` 的 ready 列，不得在計算邏輯中寫死乘數。

## GWP 脈絡

| emission_context | 氣體 | GWP | 用途 |
|---|---|---|---|
| `fuel_combustion` | CO2 | 1 | 固定／移動燃料燃燒 |
| `fuel_combustion` | CH4 | 28 | 固定／移動燃料燃燒 |
| `fuel_combustion` | N2O | 265 | 固定／移動燃料燃燒 |
| `fossil_methane_process` | CH4 | 30 | 石化甲烷／製程或逸散；**燃燒不得選用** |

燃燒路徑只查 `fuel_combustion`。缺少或歧義 GWP → `blocked_missing_gwp`。

## 係數版本一致性

同一筆燃料結果的 CO2／CH4／N2O 必須同一 `source_reference_id`、`factor_year`、`combustion_context`。缺一氣體不得部分加總。

現行官方一般燃料係數來源：環境部 **113年2月5日公告溫室氣體排放係數** ODS<br>
`snap_src_tw_moenv_general_emission_factors_085fe962e158`。

## 阻擋行為（禁止假零）

`blocked_*` / `no_factor_configured` / `unsupported_*` 的 `calculated_kgco2e` 與 `calculated_tco2e` 必須是 missing，不得寫 0。

## 追溯鏈

成功燃料結果必須能追溯：

活動 → 正規化 → 燃料子類型 → 熱值列 → 熱值來源 snapshot（路徑／雜湊）→ kcal→TJ 工程換算 → CO2/CH4/N2O 係數 → GWP（含 emission_context）→ formula_id/version → kgCO2e / tCO2e

機器可讀追蹤在 `calculation_trace`（JSON，非 LLM 產生），含 `heating_value_id`、`heating_value_source_reference_id`、snapshot path/hash、factor IDs、GWP、formula。

## 官方 114 年度熱值來源

來源為環境部氣候變遷署官方 HTML 公告，人工保存為本地 PDF 快照；**不是**原先對外發布的可下載 PDF。

- 標題：114年度車用汽油、柴油、液化石油氣及天然氣之熱值
- 發布日期：2026-02-10
- `source_medium`：official HTML announcement
- `local_snapshot`：manually saved PDF
- 驗證方法：`MANUALLY_VERIFIED_FIRST_PARTY_HTML_SNAPSHOT`
- 本地路徑：`data/reference/manual_sources/moenv_114_fuel_heating_values_2026-02-10.pdf`
- SHA-256：`80585dc0f2bd92f6abe0405a9855ccace2bc745e92b7f1be9b5c67e8cdb5c8c7`
- 詳情頁 Record_ID 印出不完整，**未猜測**

誤標 snapshot `snap_src_tw_moenv_fuel_heating_values_f809a27150c0` 實際是排放係數 PDF，維持 `rejected` / `WRONG_DOCUMENT_FOR_SOURCE`。

`HEATING_VALUE_SOURCE_VERIFICATION_REQUIRED` 僅對 2025 柴油／NG1／NG2 解除。未來年度仍須各自 verified 證據。

汽油 7586 kcal/L 與 LPG 5993 kcal/L／10972 kcal/kg 已登錄為參考，Stage 4 不擴充其計算路徑。
