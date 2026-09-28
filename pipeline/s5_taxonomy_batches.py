"""S5 part A, step 2: taxonomy.json (domains + subjects in BD's own vocabulary) and 6 tagging batches.

The subject list is hand-curated from these source vocabularies (the "evidence" field names which):
  ADV33  = PNAP ADV-33 Appendix A1 check items (Parts A-C, items 1.1-3.4.2) and Appendices B1-B12, C1-C3
  INDEX  = BD's legacy "Index under:" footnotes in 88 PNAPs (extracted by script, S5)
  FSCODE = Code of Practice for Fire Safety in Buildings 2011, Parts A-G
  PNAP   = PNAP series (ADM / APP / ADV) and title words
  LAO / TPB / FSD = the LandsD, PlanD and FSD series titles
keywords are only hints for part B tagging agents (title_hits = how many document titles they match).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _paths import PIPE, WORK, SITE
import json, re, collections, sys, pathlib, datetime
sys.stdout.reconfigure(encoding='utf-8')
SB = PIPE
G = SB / 'graph'; (G / 'batches').mkdir(exist_ok=True)

DOMAINS = [
    ('D1', 'Development control and town planning', '發展管制及城市規劃', 'ADV33 Part C 3.1 "Density"; ADV33 1.1-1.3 Location; TPB series'),
    ('D2', 'Fire safety', '消防安全', 'ADV33 3.2 "Safety"; FSCODE Parts B-G; FSD series'),
    ('D3', 'Structure and geotechnics', '結構及岩土', 'ADV33 Appendices B1-B12 (structural plans); INDEX geotechnical terms'),
    ('D4', 'Site safety and supervision', '地盤安全及工程監督', 'INDEX site terms; PNAP APP qualified-supervision notes; PNRC series'),
    ('D5', 'Building design, services and health', '建築設計、屋宇設備及衞生', 'ADV33 3.3 "Health and Environment", 3.4 allied legislation, 2.2-2.5; Appendix C (drainage)'),
    ('D6', 'Existing buildings, minor works and enforcement', '現有建築物、小型工程及執法', 'PNAP APP-147/148, PNBI series, BD guidelines on existing buildings'),
    ('D7', 'Lands and lease administration', '地政及契約管理', 'LAO Practice Note titles; JPN series'),
    ('D8', 'Administration, registration and approval process', '行政、註冊及審批程序', 'PNAP ADM series; ADV33 Parts A-B'),
]

# (id, domain, name_en, name_zh, evidence, en-keyword regex, zh-keyword regex)
S = [
 ('site-area', 'D1', 'Site area and site classification', '地盤面積及地盤類別', ['ADV33 3.1.1 Site Parameter: (i) site area, (ii) site classification', 'INDEX "B(P)R 23(2)(a) - Streets in relation to Site Area"', 'PNAP APP-44, APP-124, ADM-21'], r'site area|site classification|site parameter', r'地盤面積|地盤類別|地盤參數'),
 ('gfa', 'D1', 'Gross floor area and GFA concessions', '總樓面面積及寬免', ['ADV33 3.1.2 (i) Gross floor area', 'INDEX "B(P)R 23(3)"', 'PNAP APP-2, APP-151, APP-104', 'LAO 4/2014 "Accountable and Non-accountable GFA"'], r'gross floor area|\bGFA\b|non-accountable', r'總樓面面積|樓面面積'),
 ('pr-sc', 'D1', 'Plot ratio and site coverage', '地積比率及上蓋面積', ['ADV33 3.1.2 Plot Ratio (PR) and Site Coverage (SC)', 'PNAP APP-19, APP-132', 'JPN 7'], r'plot ratio|site coverage', r'地積比率|上蓋面積'),
 ('height', 'D1', 'Building height, storey height and podium', '建築物高度、樓層高度及平台', ['INDEX "Podium height" (APP-101)', 'PNAP APP-5 "Height of Storeys"', 'JPN 5 "Building Height Restriction"'], r'height|podium|storey', r'高度|平台|樓層'),
 ('streets', 'D1', 'Streets, private streets and service lanes', '街道、私家街道及後巷', ['ADV33 1.3 Building in, over, under or upon street/lane', 'INDEX "Street", "Street Improvement Schemes", "B(P)R 22(2) - Street Widening"', 'PNAP APP-11, APP-20, APP-73, Cap 123G'], r'\bstreets?\b|service lane|access road|street widening', r'街道|後巷|通路'),
 ('sbd-green', 'D1', 'Sustainable building design and green features', '可持續建築設計及環保設施', ['PNAP APP-151 "Quality and Sustainable Built Environment", APP-152 "SBD Guidelines"', 'JPN 1-3, 6', 'PNAP ADV-35 "Greening in Buildings"'], r'sustainable|green|greenery|landscape|building separation|setback', r'可持續|環保|綠化|園景|樓宇間距'),
 ('mic-innovation', 'D1', 'Modular integrated construction and innovative building', '組裝合成建築法及創新建築', ['PNAP ADV-36 "Modular Integrated Construction", ADV-38 "Innovative Building Materials"', 'JPN 8', 'PNAP APP-161'], r'modular|\bMiC\b|innovative', r'組裝合成|創新'),
 ('tpb-s16', 'D1', 'Planning permission under section 16', '根據第16條提出的規劃申請', ['TPB titles "... under Section 16 of the Town Planning Ordinance"', 'ADV33 3.4.2 (i) OZP; 1.2 Permitted use under Outline Zoning Plan', 'PNAP ADV-20'], r'section 16|planning application|planning permission|outline zoning', r'第16條|規劃申請|規劃許可|分區計劃大綱圖'),
 ('zoning', 'D1', 'Zoning and land-use designation', '地帶劃分及土地用途', ['TPB titles: CDA, OU(B), Industrial, Green Belt, Village Type Development zones', 'LAO "Other Specified Uses (Business) Zones"'], r'\bzones?\b|comprehensive development|green belt|specified uses|existing use', r'地帶|綜合發展區|綠化地帶|其他指定用途'),
 ('tpb-procedure', 'D1', 'Town planning procedures', '城市規劃程序', ['TPB PG 20A, 26A, 29C-36C (representations, publication, further information, deferment, renewal, extension, amendments)'], r'representation|publication of applications|further information|deferment|renewal of planning|extension of time|lapsing|approval conditions|class a and class b|consultation with district', r'申述|公布|進一步資料|延期|續期|規劃許可的有效期'),
 ('special-areas', 'D1', 'Special control areas', '特別管制區', ['ADV33 1.1 Special Control Area (Scheduled Area, Airport height control, Country Park)', 'PNAP APP-9, APP-24, APP-30, APP-32, APP-61, APP-134', 'INDEX "Designated Area"'], r'scheduled area|mid-levels|airport|railway protection|country park|designated area|northshore', r'附表區|半山區|機場|鐵路保護|郊野公園'),
 ('moe', 'D2', 'Means of escape', '逃生途徑', ['FSCODE Part B Means of Escape', 'ADV33 3.2.2 Means of Escape (MoE): travel distance, refuge floors, temporary refuge space', 'MOE Code 1996; B(P)R 41(1)'], r'means of escape|\bMOE\b|refuge floor|exit|staircase', r'逃生途徑|避火層|出口|樓梯'),
 ('frc', 'D2', 'Fire resisting construction and fire properties of elements', '耐火結構及建築元件的耐火性能', ['FSCODE Part C Fire Resisting Construction; Part E Fire Properties of Building Elements', 'ADV33 3.2.3 Fire Resisting Constructions (FRC)', 'INDEX "Fire Resisting Construction", "FRC Code"; PNAP APP-106'], r'fire resist|\bFRC\b|compartment|fire rated|fire door', r'耐火|防火'),
 ('moa', 'D2', 'Means of access for firefighting and rescue', '消防和救援進出途徑', ['FSCODE Part D Means of Access', 'ADV33 3.2.1 Means of Access for Firefighting: fireman\'s lifts, emergency vehicular access', 'INDEX "MOA", "Emergency vehicular access"; PNAP APP-75, APP-136; B(P)R 41A-41D'], r"means of access|\bMOA\b|fireman.s lift|emergency vehicular access|\bEVA\b|firefighting", r'消防和救援進出途徑|消防員升降機|緊急車輛通道'),
 ('fsm', 'D2', 'Fire safety management', '消防安全管理', ['FSCODE Part F Fire Safety Management'], r'fire safety management', r'消防安全管理'),
 ('fire-engineering', 'D2', 'Fire engineering approach', '消防工程方法', ['FSCODE Part G Fire Engineering', 'INDEX "Fire Engineering Approach"; PNAP APP-87'], r'fire engineering|performance-based', r'消防工程'),
 ('fsi', 'D2', 'Fire service installations and equipment', '消防裝置及設備', ['FSD Codes of Practice for Minimum FSI&E and Inspection, Testing and Maintenance', 'FSD Circular Letters; FSD Technical Guidance; Fire Protection Notices', 'INDEX "Fire Service Installations - Permanent Water Supply" (APP-31)'], r'fire service installation|\bFSI\b|sprinkler|fire alarm|fire detection|hydrant|hose reel|emergency lighting|exit sign|fire protection notice|smoke', r'消防裝置|花灑|火警|消防栓|喉轆|緊急照明|出口指示'),
 ('ventilation-fire', 'D2', 'Ventilating systems and fire dampers', '通風系統及防火閘', ['FSD old-series ventilation circulars (V/72, AC/71, 1(Vent)/90-98)', 'Building (Ventilating Systems) Regulations (Cap 123J)'], r'ventilat|fire damper|air condition|duct', r'通風|防火閘|空氣調節|風管'),
 ('fire-existing', 'D2', 'Fire safety improvement to existing buildings', '現有建築物的消防安全改善', ['PNAP APP-94 (Cap 502), APP-145 (Cap 572)', 'Fire Safety (Buildings / Commercial Premises / Industrial Buildings) Ordinances'], r'fire safety \((?:buildings|commercial premises|industrial buildings)\)|fire safety improvement|fire safety directions?', r'消防安全\((?:建築物|商業處所|工業建築物)\)|消防安全指示'),
 ('concrete', 'D3', 'Concrete structures and reinforcement', '混凝土結構及鋼筋', ['Code of Practice for Structural Use of Concrete 2013', 'INDEX "Concrete", "Fixing of Reinforcement for Concrete Works", "PFA Pulverised Fuel Ash"', 'PNAP APP-33, APP-45, APP-74, APP-167; ADV-15'], r'concrete|reinforcement|rebar|\bPFA\b', r'混凝土|鋼筋'),
 ('steel-glass-precast', 'D3', 'Steel, glass and precast construction', '鋼、玻璃及預製結構', ['Codes of Practice for Structural Use of Steel 2011, Glass 2018, Precast Concrete Construction 2016', 'PNAP APP-143, APP-168, APP-171, APP-174'], r'steel|glass|precast', r'鋼結構|玻璃|預製'),
 ('loads-wind', 'D3', 'Loads and wind effects', '荷載及風力效應', ['Code of Practice for Dead and Imposed Loads 2011', 'Code of Practice on Wind Effects 2019; PNAP APP-139'], r'imposed load|dead load|wind', r'荷載|風力'),
 ('foundations', 'D3', 'Foundations and piling', '基礎及樁柱', ['Code of Practice for Foundations 2017; PNAP APP-18', 'ADV33 Appendix B1 Foundation Plan', 'INDEX "Caissons" (APP-59 "Ban on Hand-dug Caissons")'], r'foundation|pile|piling|caisson', r'基礎|樁'),
 ('elsp', 'D3', 'Excavation, lateral support and dewatering', '挖掘、側向承托及抽水', ['ADV33 Appendix B2 Excavation and Lateral Support Plan', 'INDEX "Basement - Dewatering in Excavation Works", "Adjoining Buildings - pouring of Concrete against Walls of"', 'PNAP APP-22, APP-26, APP-57'], r'excavation|lateral support|dewatering|basement', r'挖掘|側向承托|抽水|地庫'),
 ('slopes', 'D3', 'Site formation, slopes and retaining walls', '地盤平整、斜坡及擋土牆', ['INDEX "Registration of Slopes and Retaining Walls", "Soil Nails", "Filling work", "Horizontal Drains", "Buried Services - keeping out of slopes"', 'PNAP APP-15, APP-51, APP-54, APP-63, APP-76, APP-79, APP-109, APP-135; ADV-8, ADV-23'], r'slope|retaining wall|site formation|soil nail|filling|horizontal drain|geoguide', r'斜坡|擋土牆|地盤平整|泥釘|填土'),
 ('ground-investigation', 'D3', 'Ground investigation and geotechnical information', '土地勘測及岩土資料', ['INDEX "Ground Investigation in Scheduled Areas", "Geotechnical Information Unit", "Geotechnical Design Information", "Soil testing"', 'PNAP APP-25, APP-49, APP-64, APP-128; ADM-6, ADM-7, ADM-16'], r'ground investigation|site investigation|geotechnical|soil', r'土地勘測|地盤勘測|岩土|土壤'),
 ('cladding', 'D3', 'Curtain walls, cladding, windows and glass balustrades', '幕牆、覆蓋層、窗及玻璃欄河', ['ADV33 Appendices B4-B7, B12 (curtain wall, glass balustrade, metal cladding, ceiling/grille/louvre)', 'INDEX "Spandrel"', 'PNAP APP-16, APP-37, APP-100, APP-116, APP-166; ADV-31'], r'curtain wall|cladding|window|balustrade|grille|louvre|tiles|finishes', r'幕牆|覆蓋層|窗|欄河|格柵|百葉|飾面'),
 ('materials', 'D3', 'Building materials, testing and product certification', '建築材料、測試及產品認證', ['PNAP APP-118 "Testing of Building Materials", APP-129, APP-165 "Product Certification System", APP-169', 'INDEX "Rainforest Timber" (ADV-5)'], r'materials?|testing|certification|timber|aggregate', r'材料|測試|認證|木材'),
 ('underground', 'D3', 'Underground caverns, tunnels and bridges', '地下岩洞、隧道及橋樑', ['INDEX "Underground caverns", "Bridges"', 'PNAP APP-34, APP-38, APP-62, APP-71; Guide to Fire Safety Design for Caverns'], r'cavern|tunnel|bridge|underground', r'岩洞|隧道|橋|地下'),
 ('site-supervision', 'D4', 'Site supervision and supervision plans', '地盤監督及監工計劃書', ['Code of Practice for Site Supervision 2009; Technical Memorandum for Supervision Plans 2009 (BO s39A)', 'INDEX "BO s17 - Requirement for Qualified Supervision of Structural Works"'], r'site supervision|supervision plan|technical memorandum', r'地盤監督|監工計劃書|技術備忘錄'),
 ('quality-supervision', 'D4', 'Qualified and quality supervision', '合資格監督及質量監督', ['PNAP APP-28, APP-48, APP-135, APP-158; PNRC 77 "Quality Supervision of Building Works"', 'INDEX "Supervision - Structural Works"'], r'qualified supervision|quality supervision|quality control|site audit|monitoring', r'合資格監督|質量監督|質量控制|巡查'),
 ('public-safety', 'D4', 'Site safety and protection of the public', '地盤安全及公眾保護', ['INDEX "Hoardings", "Covered walkways and Gantries", "Precautionary measures for construction works", "Contractor\'s Shed", "Concrete Batching Plant", "Sale offices"', 'PNAP APP-23, APP-95, APP-102, APP-107, APP-120, APP-127; ADV-12, ADV-29'], r'hoarding|gantr|covered walkway|site safety|public safety|precautionary|contractor.s shed|batching|sale offices?|pay for safety|site information', r'圍板|棚架|有蓋行人道|地盤安全|公眾安全|預防措施|工地'),
 ('scaffolding', 'D4', 'Scaffolding, working platforms and temporary works', '棚架、工作平台及臨時工程', ['INDEX "Plastic Sheet Scaffolding"', 'PNAP APP-70; ADV-10, ADV-11; Guidelines on Bamboo Scaffolds; PNRC 85'], r'scaffold|working platform|temporary works|protective net', r'棚架|工作平台|臨時工程|保護網'),
 ('demolition', 'D4', 'Demolition works', '拆卸工程', ['Code of Practice for Demolition of Buildings 2004', 'PNAP APP-21; Building (Demolition Works) Regulations (Cap 123C)'], r'demolition', r'拆卸'),
 ('blasting', 'D4', 'Blasting, ground vibration and settlement', '爆破、地面振動及沉降', ['INDEX "Blasting", "Blasting Control of Blasting"', 'PNAP APP-72, APP-137'], r'blasting|vibration|settlement', r'爆破|振動|沉降'),
 ('construction-environment', 'D4', 'Construction nuisance, waste and environmental protection', '建築滋擾、廢物及環境保護', ['INDEX "Construction waste", "Noise annoyance prevention", "Disposal of Dredged/Excavated Sediment", "Natural streams/rivers", "Metal refuse chutes at construction sites"', 'PNAP ADV-1 Asbestos, ADV-4, ADV-17, ADV-19, ADV-21, ADV-22, ADV-27; APP-66'], r'waste|noise|nuisance|sediment|asbestos|stream|river|trees?\b|pollution', r'廢物|噪音|滋擾|沉積物|石棉|河溪|樹木|污染'),
 ('light-vent', 'D5', 'Natural lighting and ventilation', '天然照明及通風', ['ADV33 3.3.1 Lighting and Ventilation', 'INDEX "Inner Room", "Common Corridors", "Bathrooms"', 'PNAP APP-65, APP-98, APP-113, APP-130; ADV-25, ADV-26, ADV-30'], r'lighting|ventilation|inner room|extractor', r'照明|通風|內部房間|抽氣扇'),
 ('open-space', 'D5', 'Open space and amenity features', '休憩用地及適意設施', ['ADV33 3.3.2 Open space', 'PNAP APP-42 "Amenity Features", APP-104, APP-122 "Sky Garden", APP-132'], r'open space|amenity|recreational|sky garden|babycare|lactation', r'休憩用地|適意設施|康樂|空中花園|育嬰'),
 ('sanitary', 'D5', 'Sanitary fitments and plumbing', '衞生設備及水管裝置', ['INDEX "Sanitary fitment", "Sanitary Fitments Fittings and Fixtures"; ADV33 2.4 Sanitary fitments', 'PNAP APP-99, APP-114; ADV-24, ADV-28'], r'sanitary|plumbing|flushing|lavator|toilet|fitments', r'衞生設備|衛生設備|水管|沖廁|廁所'),
 ('drainage', 'D5', 'Drainage works and water seepage', '排水工程及滲水', ['ADV33 Appendices C1-C3 (Drainage Plans)', 'INDEX "Cast iron drainage pipes", "B(SSFPDW&L)R 73 - Testing of Drainage Works", "Horizontal Drains"', 'PNAP APP-4, APP-58, APP-93, APP-105, APP-112, APP-133, APP-164'], r'drain|seepage|sewage|water supply|condensation|\bwells?\b', r'排水|滲水|污水|供水|冷凝水'),
 ('refuse', 'D5', 'Refuse storage and material recovery', '垃圾及物料回收', ['PNAP APP-35; Building (Refuse Storage and Material Recovery Chambers and Refuse Chutes) Regulations (Cap 123H)'], r'refuse|material recovery|chute', r'垃圾|物料回收'),
 ('lifts', 'D5', 'Lifts and escalators', '升降機及自動梯', ['Code of Practice for Building Works for Lifts and Escalators', 'PNAP APP-29, APP-89, APP-91; ADV-10'], r'\blifts?\b|escalator|liftwell', r'升降機|自動梯|升降機槽'),
 ('energy', 'D5', 'Energy efficiency and OTTV', '能源效益及總熱傳送值', ['Code of Practice for OTTV 1995; Building (Energy Efficiency) Regulation (Cap 123M)', 'PNAP APP-67, APP-156; Guidelines on Energy Efficiency of Residential Buildings'], r'energy|thermal transfer|\bOTTV\b|solar|photovoltaic', r'能源|熱傳送|太陽能'),
 ('utilities', 'D5', 'Gas, oil storage, telecommunications and utility installations', '氣體、貯油、電訊及公用設施', ['ADV33 2.2 Standard details: gas flue aperture', 'INDEX "Building (Oil Storage Installations) Regulations"', 'PNAP APP-8, APP-10, APP-27, APP-84; ADV-6, ADV-7'], r'\bgas\b|oil storage|chimney|flue|telecommunication|broadcast|lightning|radio base|transformer|smart locker', r'氣體|貯油|煙囪|煙道|電訊|避雷|發電機|變壓器'),
 ('bfa', 'D5', 'Barrier-free access and elderly-friendly design', '暢通無阻的通道及長者友善設計', ['ADV33 3.4.1 Access and Facilities for Persons with a Disability', 'Design Manual: Barrier Free Access 2008; B(P)R 72 and Third Schedule', 'PNAP APP-41, APP-175'], r'barrier free|disabilit|elderly-friendly|accessible', r'暢通無阻|殘疾|長者友善'),
 ('barriers-projections', 'D5', 'Protective barriers, projections and balconies', '防護欄障、伸出物及露台', ['INDEX "protective barrier stairwell open well"', 'ADV33 2.2 Utility platform, balcony, A/C platform', 'PNAP APP-19, APP-110, APP-119, APP-146; B(P)R 3A'], r'protective barrier|projection|balcon|utility platform|stair-?well|metal gate|a/c platform', r'防護欄障|伸出物|露台|工作平台|閘'),
 ('external-maintenance', 'D5', 'Access for external maintenance', '外部維修通道', ['Code of Practice on Access for External Maintenance 2021', 'PNAP ADV-14, APP-163; B(C)R s27, s31'], r'external maintenance|external inspection', r'外部維修'),
 ('parking', 'D5', 'Car parks, loading and vehicular access', '停車場、上落客貨及車輛通道', ['ADV33 3.4.2 (ii) Vehicular Run-in/out', 'INDEX "Vehicular Run-in and Run-out"', 'PNAP APP-111, APP-144; LAO parking notes'], r'car park|parking|loading|run-in|vehicular', r'停車|泊車|上落客貨|車輛出入'),
 ('special-use', 'D5', 'Special-use premises (hotels, schools, child care, RCHE, columbaria, entertainment)', '特殊用途處所（酒店、學校、幼兒中心、安老院舍、骨灰安置所、娛樂場所）', ['INDEX "Child Care Centres - licensing of", "Cinemas", "Kitchen attached to restaurant"', 'PNAP APP-14, APP-40, APP-43, APP-81, APP-154, APP-172, APP-173'], r'hotel|guesthouse|school|kindergarten|child care|elderly|RCHE|columbari|cinema|entertainment|hostel|restaurant|tutorial|bathhouse|massage|eating place', r'酒店|賓館|學校|幼稚園|幼兒|安老|骨灰|娛樂|宿舍|食肆|補習'),
 ('minor-works', 'D6', 'Minor works control system', '小型工程監管制度', ['PNAP APP-147, APP-148', 'General and Technical Guidelines on Minor Works Control System; Cap 123N'], r'minor works', r'小型工程'),
 ('mbis-mwis', 'D6', 'Mandatory building and window inspection', '強制驗樓及驗窗', ['PNBI series; Code of Practice for MBIS and MWIS', 'Building (Inspection and Repair) Regulation (Cap 123P)'], r'mandatory (?:building|window) inspection|\bMBIS\b|\bMWIS\b|inspection report|prescribed inspection', r'強制驗樓|強制驗窗|檢驗報告|訂明檢驗'),
 ('ubw', 'D6', 'Unauthorised building works and enforcement', '僭建物及執法', ['PNAP APP-47 "Unauthorized Alterations and Additions"', 'BD internal guidelines on actionable UBW and default works surcharge'], r'unauthori[sz]ed|\bUBW\b|enforcement|removal order|default works|surcharge', r'僭建|執法|清拆令|失責工程'),
 ('a-and-a', 'D6', 'Alteration and addition works', '改動及加建工程', ['INDEX "Structural A&A Works"', 'PNAP APP-117; ADM-12'], r'alteration|addition|\bA&A\b', r'改動|加建'),
 ('signboards', 'D6', 'Signboards', '招牌', ['PNAP APP-126, APP-155; PNRC 75', 'Guide on Advertising Signs; Guidelines on Abandoned or Dangerous Signboards'], r'signboard|advertising sign', r'招牌'),
 ('industrial', 'D6', 'Industrial buildings: conversion and use', '工業大廈的改裝及使用', ['PNAP APP-36, APP-150, APP-159', 'LAO waivers for industrial premises and special waivers for conversion'], r'industrial|godown|revitali', r'工業|貨倉|活化'),
 ('heritage', 'D6', 'Historic buildings and adaptive re-use', '歷史建築及活化再用', ['PNAP APP-69 "Conservation of Historic Buildings"', 'Practice Guidebook for Adaptive Re-use of Heritage Buildings'], r'historic|heritage|adaptive re-?use|conservation', r'歷史建築|文物|活化再用|保育'),
 ('maintenance', 'D6', 'Building maintenance and repair', '樓宇維修及保養', ['Building Maintenance Guidebook; Guidelines on Maintenance and Repair of Drainage System', 'Guidelines on Prevention of Water Seepage in New Buildings'], r'maintenance|repair|dilapidat|dangerous', r'維修|保養|失修|危險'),
 ('lease-modification', 'D7', 'Lease modification, land exchange and premium', '契約修訂、換地及補地價', ['LAO titles "Lease Modification", "Land Exchange", "Standard Rates", "Premium", "Pay for What You Build"'], r'lease modification|land exchange|premium|standard rates', r'契約修訂|換地|補地價|標準金額'),
 ('waivers', 'D7', 'Waivers and temporary use under lease', '豁免書及契約下的臨時用途', ['LAO titles "Application for Waiver(s)", "Special Waiver", "Temporary Occupation of Government Land"'], r'waiver|temporary occupation', r'豁免書|短期豁免|臨時佔用'),
 ('lease-compliance', 'D7', 'Lease compliance (DDH, landscape and site coverage clauses, certificate of compliance)', '契約條款的遵從（設計、布局及高度條款、園景條款、合規證明書）', ['LAO 3/2020 "Design, Disposition and Height Clause", 1/2020 "Landscape Clause", 1/2004 "Site Coverage Control", 1/2026 "Certificate of Compliance", 2/2022 "Building Covenant"'], r'design, disposition|landscape clause|compliance|building covenant|encroachment|house restrictions', r'設計、布局及高度|園景條款|合規|建築規約'),
 ('lease-plans', 'D7', 'Building plans and consent under lease', '契約下的建築圖則及同意', ['LAO titles "Processing of General Building Plans", "Approval or Consent Under Lease", "Master Layout Plans", "Streamlined Building Plans Checking"'], r'building plans?|master layout|approval or consent|consent to|general building plan', r'建築圖則|總綱發展藍圖|批准或同意'),
 ('lease-gfa-facilities', 'D7', 'GFA, parking and facilities under lease', '契約下的總樓面面積、泊車及設施', ['LAO 4/2014 "Accountable and Non-accountable GFA", 4/2006 and 2/2000 car parking, 4/2000(B) recreational facilities, 2/2011 balconies, 9/2025 aboveground'], r'gross floor area|car parking|parking|recreational|balcon|bonus plot ratio|residential care', r'總樓面面積|泊車|康樂設施|露台|額外地積比率'),
 ('nteh', 'D7', 'New Territories exempted houses', '新界豁免管制屋宇', ['LAO 1/2025 "Self-Certification of Compliance New Territories Exempted Houses"', 'Cap 121 Buildings Ordinance (Application to the New Territories) Ordinance'], r'new territories|exempted house|small house|\bNTEH\b', r'新界|豁免管制屋宇|小型屋宇'),
 ('plan-submission', 'D8', 'Plan submission and approval process', '圖則呈交及審批程序', ['ADV33 Part A Administration (specified forms, plans, fee)', 'PNAP ADM-2, ADM-5, ADM-9, ADM-10, ADM-14, ADM-19, ADM-22, ADM-23; APP-55, APP-60', 'INDEX "Priority", "BO s16(3A) - Approved Plans"'], r'submission|approval process|centralised processing|priority|colouring|specified forms|fees|withdrawal and resubmission|self-certification|consent', r'呈交|審批|集中處理|優先|指明表格|費用|自行核證'),
 ('bim-digital', 'D8', 'BIM and electronic submission', '建築信息模擬及電子呈交', ['PNAP ADM-17 "Submission in Electronic Format", ADV-34 "Building Information Modelling"', 'BD BIM guidelines 2019 and 2023; LAO 6/2024'], r'building information model|\bBIM\b|electronic', r'建築信息模擬|電子'),
 ('occupation', 'D8', 'Occupation permits and completion', '佔用許可證及完工', ['INDEX "BO s21 Occupation Permits", "B(A)R 25A - Water Supply Certificate"', 'PNAP APP-13, APP-78'], r'occupation|completion|certificate of completion', r'佔用|完工'),
 ('modification-exemption', 'D8', 'Modification and exemption (BO section 42)', '規例的修改及豁免（《建築物條例》第42條）', ['ADV33 Part B 2 Exemptions/Modifications; Appendices A2, A3, C2', 'PNAP APP-123 "Alternative Designs"'], r'modification|exemption|alternative design', r'修改|豁免|替代設計'),
 ('registration', 'D8', 'Registration and conduct of building professionals and contractors', '建築專業人士及承建商的註冊及操守', ['PNAP APP-3, APP-7, APP-96, APP-138, APP-140, APP-148, APP-149; ADV-37', 'INDEX "AP registering as RGE", "Authorised Signatory of Registered Contractor", "Corruption Prevention" (ADV-18)', 'PNRC series'], r'registration|authori[sz]ed person|registered contractor|signatory|nomination|conduct|corruption|bribery|gifts|continuing professional|workers registration', r'註冊|認可人士|承建商|獲授權簽署人|操守|貪污|持續專業'),
]
assert len({s[0] for s in S}) == len(S)

nodes = json.load(open(G / 'nodes.json', encoding='utf-8'))['nodes']
docs = [n for n in nodes if n['kind'] == 'document']
hits = collections.Counter(); untagged = []
for n in docs:
    got = False
    for sid, dom, en, zh, ev, ke, kz in S:
        if re.search(ke, n['title_en'] or '', re.I) or (kz and re.search(kz, n['title_zh'] or '')):
            hits[sid] += 1; got = True
    if not got: untagged.append(n['id'])
now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
tax = {'built': now, 'script': 'pipeline/s5_taxonomy_batches.py',
       'status': 'DRAFT for review (three-layer link model). Subjects are regions/colours, never lines.',
       'evidence_keys': {'ADV33': 'PNAP ADV-33 Essential Information in Plan Submissions, Appendix A1 check items and Appendices B/C',
                         'INDEX': 'BD legacy "Index under:" footnotes (88 PNAPs)', 'FSCODE': 'Code of Practice for Fire Safety in Buildings 2011, Parts A-G',
                         'PNAP': 'PNAP ADM/APP/ADV series and titles', 'LAO': 'LAO Practice Note titles', 'TPB': 'TPB Planning Guideline titles',
                         'FSD': 'FSD circular letters, CoP, technical guidance, fire protection notices'},
       'note_keywords': 'keywords are hints for part B only; title_hits counts document titles they match (a title can match several subjects).',
       'titles_matching_no_subject': len(untagged),
       'domains': [{'id': d, 'name_en': en, 'name_zh': zh, 'evidence': ev} for d, en, zh, ev in DOMAINS],
       'subjects': [{'id': sid, 'name_en': en, 'name_zh': zh, 'domain': dom, 'evidence': ev,
                     'keywords_en': ke, 'keywords_zh': kz, 'title_hits': hits[sid]} for sid, dom, en, zh, ev, ke, kz in S]}
json.dump(tax, open(G / 'taxonomy.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('subjects', len(S), 'domains', len(DOMAINS), 'titles matching no subject', len(untagged))
print('zero-hit subjects', [s for s, *_ in S if not hits[s]])
print('by domain', collections.Counter(s[1] for s in S))

# ------------------------------------------------------------------ batches
E = json.load(open(G / 'edges_citations.json', encoding='utf-8'))['edges']
N = {n['id']: n for n in nodes}
nb = collections.defaultdict(list)
for e in E:
    t, s = N[e['target']], N[e['source']]
    nb[e['source']].append({'dir': 'out', 'id': e['target'], 'label': t.get('code') or t.get('title_en') or e['target'],
                            'title': (t.get('title_en') or '')[:90], 'type': e['type'], 'level': e['level']})
    if s['kind'] == 'document':
        nb[e['target']].append({'dir': 'in', 'id': e['source'], 'label': s.get('code') or s['id'],
                                'title': (s.get('title_en') or '')[:90], 'type': e['type'], 'level': 'document'})
TX = {}
for l in open(str(WORK / 'text/corpus.jsonl'), encoding='utf-8'):
    r = json.loads(l); TX.setdefault(r['doc_id'], {})[r['lang']] = r['text_path']

def excerpt(n):
    for lang in ('en', 'zh'):
        if lang in (n.get('lang_versions') or []):
            for slot in ('en', 'zh'):
                p = TX.get(n['id'], {}).get(slot)
                if not p: continue
                t = open(p, encoding='utf-8', errors='ignore').read()
                zhr = len(re.findall(r'[\u4e00-\u9fff]', t)) / max(1, len(re.sub(r'\s', '', t)))
                if (zhr > 0.15) == (lang == 'zh'):
                    t = re.sub(r'[\uf000-\uf8ff]', '', t); t = re.sub(r'\s+', ' ', t).strip()
                    if lang == 'zh': t = re.sub(r'(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]) | (?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])', '', t)
                    return lang, t[:1500]
    return None, None

order = sorted(docs, key=lambda n: (n['dept'], n['series'], n['code'] or n['id']))
K = 6; size = -(-len(order) // K)
paths = []
for k in range(K):
    part = order[k * size:(k + 1) * size]
    recs = []
    for n in part:
        lang, ex = excerpt(n)
        nbs = nb.get(n['id'], [])
        # documents first, then sections, then instruments/ordinances; cap at 40
        rank = {'document': 0, 'section': 1, 'instrument': 2, 'external_ordinance': 3}
        seen = set(); ordered = []
        for x in sorted(nbs, key=lambda x: (rank.get(x['level'], 4), x['dir'], x['label'])):
            if (x['dir'], x['id']) in seen: continue
            seen.add((x['dir'], x['id'])); ordered.append(x)
        recs.append({'id': n['id'], 'code': n['code'], 'title_en': n['title_en'], 'title_zh': n['title_zh'],
                     'dept': n['dept'], 'series': n['series'], 'date': n['date'], 'missing_lang': n['missing_lang'],
                     'has_text': n['has_text'], 'excerpt_lang': lang, 'text_excerpt': ex,
                     'neighbours': ordered[:40], 'neighbours_total': len(ordered)})
    p = G / 'batches' / f'batch_{k + 1}.json'
    json.dump({'batch': k + 1, 'of': K, 'built': now, 'count': len(recs),
               'for': 'part B AI tagging agents: assign domain/subjects from taxonomy.json; suggest bridges for isolated or cross-department docs',
               'records': recs}, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    paths.append((str(p), len(recs), collections.Counter(r['dept'] for r in recs)))
for p in paths: print(p)
