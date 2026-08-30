# 計算覆蓋現況 v1（Calculation Coverage）

日期：2026-08-13<br>
範圍：Stage 4 官方 114 年度熱值啟用後的**實際**能力<br>
依據：`calculate.py`、`match_factors.py`、`heating.py`、factor registry、`tests/test_stage4_ghg_coverage.py`

> 本文件只描述**目前程式與測試已證實**的行為。

## 摘要

| 結論 | 說明 |
|------|------|
| **電力** | `grid_electricity` 可計算。2024 demo：50000 kWh × 0.474 = **23.7 tCO2e**。2025 企業盤查係數 0.466 僅在用途脈絡符合時使用。 |
| **燃料公式** | 已實作 `fuel_activity_to_energy_to_multigas_co2e` v1.0（CO2/CH4/N2O × GWP 28/265） |
| **2025 柴油（公司車）** | **supported**：官方低位熱值 8636 kcal/L |
| **2025 天然氣 NG1** | **supported**：低位 8067 kcal/m3（高位 8963 保留） |
| **2025 天然氣 NG2** | **supported**：低位 8728 kcal/m3（高位 9698 保留） |
| **2025 天然氣（未指定類型）** | **blocked**：必須確認 NG1 或 NG2，不得推測 |
| **2024 demo 天然氣／柴油** | **blocked_missing_conversion**：不可回溯套用 2025 熱值 |
| **外購鋼材** | `purchased_steel`：**無可用排放係數** |
| **假零值** | blocked / no-factor 列的 `calculated_*` 為 missing（NaN），不會寫成 0 |

## 狀態圖例

| Status | 意義 |
|--------|------|
| **supported** | 端到端可算出 `calculated_tco2e`（含生產登錄檔中的 verified 參考） |
| **blocked** | 有候選係數或部分準備，但計算被明確阻擋 |
| **unsupported** | 無可套用係數或非排放活動 |

## 覆蓋表

| Activity type | Scope（產品語意） | Factor coverage | Conversion | GWP path | Status | Blocking reason | Next requirement |
|---------------|-------------------|-----------------|------------|----------|--------|-----------------|------------------|
| `grid_electricity` | Scope 2 | 2024：0.474 ready；2025 enterprise：0.466（需工業／企業盤查脈絡） | kWh；`not_required` | 直接 CO2e（`activity_value_times_direct_co2e_factor` v1.0） | **supported** | 用途不明時不選 2025 分類係數 | 維持年份／類別治理 |
| `natural_gas` NG1 2025 | Scope 1 stationary | ODS：CO2 56100 / CH4 1 / N2O 0.1 kg/TJ | 8067 kcal/m3 → kcal → TJ（4.1868e-9） | 燃燒 GWP：CH4=28、N2O=265 | **supported** | — | 必須明示 NG1 |
| `natural_gas` NG2 2025 | Scope 1 stationary | 同上 | 8728 kcal/m3 → kcal → TJ | 同上 | **supported** | — | 必須明示 NG2 |
| `natural_gas` 無類型／未知 | Scope 1 | 熱值已登錄但不可猜測 | — | — | **blocked** | `blocked_natural_gas_type_required` | 確認 NG1 或 NG2 |
| `natural_gas` 2024 | Scope 1 | 係數存在 | 無 2024 官方熱值 | — | **blocked** | `blocked_missing_conversion` | 另案提供 2024 正本 |
| `diesel`（company_vehicle）2025 | Scope 1 mobile | ODS：CO2 74100 / CH4 3.9 / N2O 3.9 kg/TJ | 8636 kcal/L → kcal → TJ | 同上 | **supported** | — | 維持公司車脈絡 |
| `diesel` 2024 | Scope 1 | 係數存在 | 無 2024 官方熱值 | — | **blocked** | `blocked_missing_conversion` | 另案提供 2024 正本 |
| `diesel`（非公司車） | — | 不套用公司車移動係數 | — | — | **unsupported** | `no_factor_configured` | 另案方法論 |
| `purchased_steel` | Scope 3 Category 1 候選 | **無** registry 係數 | N/A | N/A | **unsupported** | `no_factor_configured` | 專案 Scope 3 階段才能引入官方係數 |

汽油／液化石油氣熱值已登錄為參考列，**尚未**實作計算路徑。

### 附註：非排放活動

| Activity type | Status | 說明 |
|---------------|--------|------|
| 成品產出（demo `rec_output_001`） | **unsupported**（`not_emissions_activity`） | 有意排除 |

## 2024 demo 行為（刻意不變）

| 活動 | 狀態 |
|------|------|
| 外購電力 | calculated **23.7 tCO2e** |
| 天然氣 | `blocked_missing_conversion`（不是 0） |
| 柴油 | `blocked_missing_conversion`（不是 0） |
| 鋼材 | `no_factor_configured` |

不可用 2025／114 年度熱值去解鎖 2024 活動。

## 產品語意

1. Dashboard「目前已計算排放量」只加總 `calculation_status=calculated`。
2. blocked 活動必須顯示缺口，**不可**顯示為 0。
3. 天然氣未確認 NG1/NG2 時，客戶文案為「請確認天然氣類型（NG1 或 NG2），才能套用正確熱值。」不暴露後端 enum。
4. `hero_emissions_countup.js` 鎖定：目標為後端實際已計算合計，無寫死數字。

## 官方熱值來源（114／活動年 2025）

來源是環境部氣候變遷署官方 **HTML 公告**，以人工方式保存為本地 PDF 快照；**不是**原先對外發布的可下載 PDF。

- 公告標題：114年度車用汽油、柴油、液化石油氣及天然氣之熱值
- 發布日期：2026-02-10
- 驗證方法：`MANUALLY_VERIFIED_FIRST_PARTY_HTML_SNAPSHOT`
- 本地快照：`data/reference/manual_sources/moenv_114_fuel_heating_values_2026-02-10.pdf`
- SHA-256：`80585dc0f2bd92f6abe0405a9855ccace2bc745e92b7f1be9b5c67e8cdb5c8c7`
- 詳情頁 Record_ID 未完整印出，**未猜測**

先前誤標 snapshot `snap_src_tw_moenv_fuel_heating_values_f809a27150c0` 實際是 113年2月5日排放係數 PDF，維持 `rejected` / `WRONG_DOCUMENT_FOR_SOURCE`，檔案保留備查。

`HEATING_VALUE_SOURCE_VERIFICATION_REQUIRED` 已對 **2025 柴油／NG1／NG2** 解除。未來年度熱值仍須各自的 verified 證據。
