# 香港建築規例關係地圖 · HK Building Regulations Map

An interactive, bilingual map of Hong Kong's building control documents and the links between them.

> **Disclaimer.** This is a personal hobby project by Anzon Wong (AW Design). It is **not** an official website. It does not represent, and is not endorsed by, the Government of the Hong Kong Special Administrative Region, the Buildings Department, the Lands Department, the Planning Department, the Town Planning Board, the Fire Services Department or any other government department. It is a navigation aid, **not legal advice**. Summaries and links may be incomplete, out of date or wrong. Always rely on the official documents published by the relevant department and on Hong Kong e-Legislation. See the full [Disclaimer](#disclaimer) below.

[中文說明](#中文說明)

---

## What it is

The map draws Hong Kong's building control documents as one connected network that you can rotate in 3D (or see in 2D on a phone):

- the Buildings Ordinance (Cap. 123) and its subsidiary regulations, down to Part and section level;
- Buildings Department practice notes (PNAP, PNRC, PNBI, JPN), circular letters, codes of practice and guidelines;
- Lands Department LAO Practice Notes;
- Town Planning Board Planning Guidelines;
- Fire Services Department circular letters, codes of practice and guidance.

The September 2026 build has 2,276 nodes (907 documents and 1,174 legislative provisions), 4,806 citation links and 99 suggested cross-department links. Click a node to light up its links and read a short English and Chinese summary with a link to the official source. Search by code, title or topic (with recent searches and popular starters), and switch the layout between department, subject domain and individual subject.

## How it was made

The map has three layers, and each is marked differently on screen:

1. **Solid lines are explicit citations.** A solid line is drawn only where one document names another, for example "PNAP APP-151" or "Regulation 23(3)(b)". The citations were found by pattern matching over the full text of every document, and each line keeps the quoted sentence and page so you can check it.
2. **Dashed lines are AI suggestions.** A small number of dashed lines join related documents across departments, or give an isolated document a neighbour. They were suggested by AI, then read against the text of both documents; each one carries a written reason. Treat them as hints, not as relationships stated by the documents.
3. **Topics are regions and colours, never lines.** Every document is tagged with a domain and subjects in the Buildings Department's own vocabulary.

The English and Chinese summaries were written by AI from the full text of each document and then checked against that text. Where no usable text was available, the summary says it is based on the title only. Superseded or repealed documents are shown faded.

**Data checked: September 2026.** Documents change. The map is a snapshot and will fall behind the official sites.

The Python pipeline that built the data is in [`pipeline/`](pipeline/README.md).

## Data sources

All documents were read from the publishers' own public websites. Nothing is re-hosted here; every node links back to its official source.

| Publisher | Documents | Official site |
|---|---|---|
| Department of Justice | Buildings Ordinance (Cap. 123) and subsidiary legislation | [Hong Kong e-Legislation](https://www.elegislation.gov.hk/) |
| Buildings Department (BD) | PNAP, PNRC, PNBI, JPN, circular letters, codes of practice, guidelines | [www.bd.gov.hk](https://www.bd.gov.hk/) |
| Lands Department (LandsD) | LAO Practice Notes | [www.landsd.gov.hk](https://www.landsd.gov.hk/) |
| Planning Department / Town Planning Board (PlanD / TPB) | TPB Planning Guidelines | [www.pland.gov.hk](https://www.pland.gov.hk/) · [www.tpb.gov.hk](https://www.tpb.gov.hk/) |
| Fire Services Department (FSD) | Circular letters, codes of practice, technical guidance, fire protection notices | [www.hkfsd.gov.hk](https://www.hkfsd.gov.hk/) |

## Run it locally

The site is static: `index.html`, `app.js`, `layout.js` and `data.js`. No build step is needed.

- Open `index.html` in a browser, or
- serve the folder with any static server, for example `python -m http.server 8000` and then open <http://localhost:8000/>.

The 3D view loads three.js and the graph libraries from the jsDelivr CDN, so the first load needs an internet connection.

It is also ready for GitHub Pages: publish the repository root.

## Disclaimer

- This is a **personal hobby project** by Anzon Wong (AW Design).
- It is **not an official website** and **does not represent, and is not endorsed by**, the Government of the Hong Kong Special Administrative Region or any of its departments or boards, including the Buildings Department, the Lands Department, the Planning Department, the Town Planning Board and the Fire Services Department.
- It is **not legal or professional advice**. Nothing here replaces reading the official documents or taking professional advice for a particular case.
- Summaries, tags and links were produced with the help of AI and may be incomplete, out of date or wrong. The data was checked in September 2026 and will not reflect later changes.
- **Always rely on the official documents** published by the relevant department and on Hong Kong e-Legislation.
- The author accepts no liability for any loss arising from use of this map.

## License and notice

- **Code** (`index.html`, `app.js`, the `pipeline/` scripts): MIT License, see [LICENSE](LICENSE).
- **Data** (the summaries, topic tags and link data in `data.js` and `layout.js`): provided under the [Creative Commons Attribution 4.0 International licence (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). Please credit "AW Design · Anzon Wong".
- **Source documents and legislation** remain the property of their publishers (the Government of the Hong Kong Special Administrative Region and its departments). They are **not redistributed** in this repository and are **only linked**. Short quotations shown next to citation links are included only to let readers verify each link, and the official documents remain the authoritative text.

## Credit

AW Design · Anzon Wong

---

## 中文說明

> **免責聲明：** 本網站是 Anzon Wong（AW Design）的個人興趣項目，並非官方網站，不代表香港特別行政區政府、屋宇署、地政總署、規劃署、城市規劃委員會、消防處或任何政府部門，亦未獲其認可。本網站只作導覽用途，**並非法律意見**。摘要及連結或有遺漏、過時或錯誤之處，一切以有關部門發出的官方文件及電子版香港法例為準。詳見下文[免責聲明](#免責聲明)。

### 這是甚麼

本地圖把香港建築管制文件繪成一個互相連結的網絡，可在立體空間中旋轉瀏覽（手機上則以平面顯示），內容包括：

- 《建築物條例》（第123章）及其附屬規例，細分至部及條；
- 屋宇署的作業備考（PNAP、PNRC、PNBI、JPN）、通函、作業守則及指引；
- 地政總署的地政處作業備考；
- 城市規劃委員會的規劃指引；
- 消防處的通函、守則及技術指引。

2026年9月版本共有2,276個節點（907份文件及1,174項法例條文）、4,806條引用連結及99條跨部門建議連結。點選節點即可顯示其連結，並閱讀中英文簡短摘要及官方來源連結。可按編號、標題或主題搜尋，並可按部門或專題範疇切換顏色。

### 製作方法

地圖分為三層，在畫面上以不同方式顯示：

1. **實線代表明確引用。** 只有當一份文件明確提及另一份文件（例如「PNAP APP-151」或「第23(3)(b)條」）時才會繪出實線。引用是以規則比對每份文件全文而找出，每條連結均保留引文及頁碼，方便讀者核對。
2. **虛線代表人工智能建議。** 少量虛線連接不同部門的相關文件，或為孤立文件提供鄰近文件。這些連結由人工智能建議，再對照兩份文件的文本核實，每條均附有書面理由。請視之為提示，而非文件本身所述的關係。
3. **主題以區域及顏色表示，從不以線表示。** 每份文件均按屋宇署本身的用語標示範疇及專題。

中英文摘要由人工智能根據每份文件的全文撰寫，再對照原文核實。如沒有可用文本，摘要會註明只根據標題撰寫。已被取代或廢除的文件以淡色顯示。

**資料核對日期：2026年9月。** 文件會不時更新，本地圖只是某一時間的記錄，日後會與官方網站有所出入。

建立資料的 Python 程序載於 [`pipeline/`](pipeline/README.md)。

### 資料來源

所有文件均取自發布機構本身的公開網站。本存放庫並不轉載任何文件，每個節點均連結至官方來源。

| 發布機構 | 文件 | 官方網站 |
|---|---|---|
| 律政司 | 《建築物條例》（第123章）及附屬法例 | [電子版香港法例](https://www.elegislation.gov.hk/) |
| 屋宇署 | 作業備考、通函、作業守則、指引 | [www.bd.gov.hk](https://www.bd.gov.hk/) |
| 地政總署 | 地政處作業備考 | [www.landsd.gov.hk](https://www.landsd.gov.hk/) |
| 規劃署／城市規劃委員會 | 城市規劃委員會規劃指引 | [www.pland.gov.hk](https://www.pland.gov.hk/) · [www.tpb.gov.hk](https://www.tpb.gov.hk/) |
| 消防處 | 通函、守則、技術指引、防火通告 | [www.hkfsd.gov.hk](https://www.hkfsd.gov.hk/) |

### 在本機運行

本網站為靜態網站，由 `index.html`、`app.js`、`layout.js` 及 `data.js` 組成，毋須編譯。

- 直接以瀏覽器開啟 `index.html`；或
- 以任何靜態伺服器提供此資料夾，例如執行 `python -m http.server 8000`，再開啟 <http://localhost:8000/>。

立體視圖會從 jsDelivr 載入 three.js 及圖表程式庫，因此首次載入須連接互聯網。本存放庫亦可直接以 GitHub Pages 發布。

### 免責聲明

- 本網站是 Anzon Wong（AW Design）的**個人興趣項目**。
- 本網站**並非官方網站**，**不代表**香港特別行政區政府或其任何部門及委員會（包括屋宇署、地政總署、規劃署、城市規劃委員會及消防處），**亦未獲其認可**。
- 本網站**並非法律或專業意見**，不能取代閱讀官方文件或就個別個案徵詢專業意見。
- 摘要、標籤及連結借助人工智能製作，或有遺漏、過時或錯誤之處。資料於2026年9月核對，不會反映其後的修訂。
- **一切以有關部門發出的官方文件及電子版香港法例為準。**
- 作者對因使用本地圖而引致的任何損失概不負責。

### 授權及聲明

- **程式碼**（`index.html`、`app.js` 及 `pipeline/` 內的程式）：以 MIT 授權發布，詳見 [LICENSE](LICENSE)。
- **資料**（`data.js` 及 `layout.js` 內的摘要、主題標籤及連結資料）：以[創用CC 姓名標示 4.0 國際授權條款（CC BY 4.0）](https://creativecommons.org/licenses/by/4.0/deed.zh-hant)提供，請註明「AW Design · Anzon Wong」。
- **原始文件及法例**的權利仍屬其發布機構（香港特別行政區政府及其部門）所有。本存放庫**並不轉載**這些文件，**只提供連結**。引用連結旁的簡短引文只為方便讀者核實連結，一切以官方文件為準。

### 鳴謝

AW Design · Anzon Wong
