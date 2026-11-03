# Sample Test Case: MedVantage Pharmacy Burglary & Drug Theft

This folder contains a complete, self-contained, realistic case package designed to be tested end-to-end in the CaseWeave AI Investigation Studio.

---

## 1. Scenario Summary

- **Case Title:** `MedVantage Pharmacy Burglary & Narcotics Theft`
- **Location:** Northgate, Northgate City, the state
- **Incident:** Nighttime forced entry at a commercial 24/7 pharmacy stockroom. The narcotics vault was pried open, high-value schedule H1 drugs (Fentanyl, Ketamine, Alprazolam) and INR 42,500 cash were stolen.
- **Embedded Contradiction / Discrepancy for Stage 4 Debate:**
  - **The Intrusion Alarm Log** records the rear shutter breach at **`02:23:10`** (and tamper alarm at `02:22:45`).
  - **The CCTV Camera Overlay** shows the intruder entering the alley and prying the shutter at **`02:28:15 – 02:29:40`** (a ~6 minute discrepancy).
  - **Witness K. Sundaram (Night Guard)** places the screeching sound at **`02:21 AM`**.
  - **Technical Grounding:** The NVR unit's clock was running ~5m 32s fast compared to standard time, perfectly explaining why the CCTV camera time diverges from the hardware alarm sensor and witness wristwatch!

---

## 2. Exhibits & Evidence Files to Upload

Upload all of the following files directly in the **Evidence Explorer** tab:

| Order | File Name | Type | Description |
|---|---|---|---|
| **1** | `01_forensic_inspection_report.pdf` | **Document (PDF)** | Formatted official forensic inspection report from the state Police FSD. |
| **2** | `02_intrusion_alarm_log.json` | **Structured Log (JSON)** | Hardware IoT alarm log from rear shutter tamper sensors & PIR motion detectors. |
| **3** | `03_cctv_alleyway_log.txt` | **Text Document** | High-definition dome camera observation log & technical NVR clock offset note. |
| **4** | `04_witness_statement_sundaram.txt` | **Witness Statement** | BNSS Section 180 statement from the commercial complex night watchman. |
| **5** | `05_witness_statement_pharmacist.txt` | **Witness Statement** | BNSS Section 180 statement from the chief pharmacist detailing stolen narcotics and cash. |
| **6** | `photos/01_tampered_rear_shutter.jpg` | **Photo Evidence** | AI-generated photorealistic crime scene photo of the rear shutter pried open with heavy scrape marks. |
| **7** | `photos/02_toppled_narcotics_cabinet.jpg` | **Photo Evidence** | AI-generated photo of the forced open green metal narcotics cabinet with scattered medicine cartons and ampoules. |
| **8** | `photos/03_discarded_crowbar_and_glove.jpg` | **Photo Evidence** | AI-generated photo of the 18-inch hex crowbar and blue nitrile glove recovered on the stockroom floor. |
| **9** | `photos/04_cash_drawer_and_counter.jpg` | **Photo Evidence** | AI-generated photo of the ransacked cash drawer pulled completely out on the glass counter. |

---

## 3. Recommended Parameters to Enter in the UI

When submitting in the Case Studio UI:

- **Case Title (at Command Center):**
  ```text
  MedVantage Pharmacy Burglary & Narcotics Theft
  ```

- **Legal Query (under Run Analysis):**
  ```text
  Admissibility of electronic intrusion logs and CCTV timestamp discrepancies under Section 63 Bharatiya Sakshya Adhiniyam 2023
  ```

- **Guided Witness Statement Form (in Evidence Explorer):**
  - **Witness Name:** `R. Selvam`
  - **Role:** `Patrol Constable`
  - **Location:** `Poonamallee High Road Junction`
  - **Statement:**
    ```text
    During routine night patrol around 02:40 AM, I spotted an unknown male walking briskly away from the pharmacy alleyway carrying a dark backpack towards the metro station.
    ```

- **SAM 3.1 Prompts to Test on Photos:**
  - On `01_tampered_rear_shutter.jpg` $\rightarrow$ type: `shutter` or `padlock`
  - On `02_toppled_narcotics_cabinet.jpg` $\rightarrow$ type: `cabinet` or `medicine carton`
  - On `03_discarded_crowbar_and_glove.jpg` $\rightarrow$ type: `crowbar` or `glove`
  - On `04_cash_drawer_and_counter.jpg` $\rightarrow$ type: `drawer` or `counter`

