# Customer Browser QA Checklist

本文件是 **顧客面向 UI／產品階段** 的發行前檢查清單。

## 品質閘道（Definition of Done）

自 Stage 3B.3a 起，顧客面向階段 **不可** 僅因下列結果宣告完成：

- Ruff pass
- 單元／整合 pytest pass

必須同時滿足：

1. **Ruff** pass
2. **單元／整合 pytest** pass
3. **瀏覽器 E2E smoke** pass（Playwright）
4. **失敗截圖**可於 `artifacts/e2e/` 檢視
5. **至少一次人工 customer journey** 完成

未完成瀏覽器驗證 = 階段未完成。

---

## 執行 E2E

```bash
# 安裝測試依賴（僅開發／CI）
python -m pip install -e ".[dev,e2e]"

# 若本機有 Google Chrome，E2E 會優先使用 channel=chrome（無需 bundled Chromium）
# 若需 Playwright 內建瀏覽器：
python -m playwright install chromium

# 僅跑瀏覽器 smoke
pytest -m e2e

# 單元／整合（排除 E2E）
pytest -m "not e2e"

# 全量（含 E2E；需本機 Chrome 或已安裝 Chromium）
pytest
```

環境變數（可選）：

| 變數 | 說明 |
|------|------|
| `CEL_E2E_PORT` | Streamlit 測試埠（預設自動選取） |
| `CEL_E2E_HEADED` | 設為 `1` 可看到瀏覽器 |

失敗截圖目錄：`artifacts/e2e/`

---

## 人工預發佈清單

### HOME
- [ ] 乾淨 CUSTOMER 啟動（無 `CEL_APP_MODE=admin`）
- [ ] 無示範公司／示範排放自動載入
- [ ] 無 admin 監控內部欄位（`automated_sources_*`、`MONITORING_PARTIAL` 等）
- [ ] 可見「開始公司設定」與「使用示範資料」

### APPLICABILITY
- [ ] 五個步驟皆可前進／後退
- [ ] Step 2：實收資本可填；淨值可勾「不知道／暫不填」
- [ ] 未知財務 **不會** 顯示成 `0.00` / `NT$0` 並據此判 NOT_APPLICABLE
- [ ] Step 3：**沒有**莫名空白白色卡片
- [ ] Step 5：結果卡可見「適用」與年度 `2026` / `2027`（水平數字）
- [ ] **沒有**原始 HTML（`</p>`、`<span`、`cel-status-chip` 字樣）
- [ ] 「查看官方依據」可用

### EVIDENCE
- [ ] 精靈一次只展開一個步驟
- [ ] 完成步驟收合為摘要
- [ ] 上一步／下一步可用
- [ ] 上傳元件可用
- [ ] 預設不暴露 raw schema／內部 enum

### ANALYSIS
- [ ] 點「開始分析」後先見 loading／skeleton
- [ ] 舊 KPI 不會被當成新結果
- [ ] 真實階段進度可見
- [ ] 完成後結果出現；count-up 綁定 `calculated_tco2e`
- [ ] **未修改** `hero_emissions_countup.js`

### REPORTING
- [ ] 顧客模式無內部 debug／raw manifest 主下載
- [ ] Demo 匯出 `synthetic_demo=true`；公司上傳為 `false`

### LANGUAGE
- [ ] zh-TW 主要文案正確
- [ ] EN 切換後關鍵頁面可讀、無 HTML 外洩

---

## 已知禁止事項

- 不要用 `st.markdown` 分開輸出開標籤／關標籤來包住 Streamlit widget
- 複雜卡片／chip 使用 `emit_html()` / `st.html()` 一次輸出完整片段
- UNKNOWN 財務值不得變成 `0` / `0.0` / `0.00`
