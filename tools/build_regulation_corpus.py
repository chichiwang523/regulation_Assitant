from __future__ import annotations

import json
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "regulations"
SOURCES = ROOT / "data" / "sources"
GOVINFO_CFR_2024_TITLE49_VOL6 = "https://www.govinfo.gov/bulkdata/CFR/2024/title-49/CFR-2024-title49-vol6.xml"


DOMAINS = {
    "braking_base": "01_braking_base",
    "esc_evsc": "02_esc_evsc",
    "aeb_aebs": "03_aeb_aebs",
    "ldws_lka": "04_ldws_lka",
    "bsis_mois": "05_bsis_mois",
    "steering_ad": "06_steering_ad",
    "axle_suspension": "07_axle_suspension",
    "ev_safety_charging": "08_ev_safety_charging",
    "visibility_lighting": "09_visibility_lighting",
    "underrun_protection": "10_underrun_protection",
    "emc_connectivity": "11_emc_connectivity",
    "emissions_noise": "12_emissions_noise",
    "tires_wheels": "13_tires_wheels",
    "coupling_marking": "14_coupling_marking",
}


def undoc(symbol: str) -> str:
    return f"https://documents.un.org/api/symbol/access?l=en&s={quote(symbol, safe='')}&t=pdf"


ENTRIES = [
    # Braking base
    {
        "domain": "braking_base",
        "region": "china",
        "code": "GB 12676-2014",
        "title": "Technical requirements and testing methods for commercial vehicle and trailer braking systems",
        "filename": "GB_12676_2014_EN_sample_preview.pdf",
        "local_source": "GB_12676_2014_EN_sample_preview.pdf",
        "source_url": "https://www.chinaautoregs.com/wp-content/uploads/2020/08/GB-12676-2014%E8%8B%B1%E6%96%87%E7%89%88%E7%BF%BB%E8%AF%91%EF%BC%88%E6%A0%B7%E9%A1%B5%E9%A2%84%E8%A7%88%EF%BC%89.pdf",
        "status": "preview_only",
        "note": "English sample preview only; complete official Chinese text was not directly downloadable.",
    },
    {
        "domain": "braking_base",
        "region": "china",
        "code": "GB 7258",
        "title": "Technical specifications for safety of power-driven vehicles operating on roads",
        "filename": "GB_7258_metadata.json",
        "status": "metadata_only",
        "note": "GB full text availability is restricted; add official/full PDF manually when available.",
    },
    {
        "domain": "braking_base",
        "region": "un_eu",
        "code": "UN R13",
        "title": "Heavy vehicle braking",
        "filename": "UN_R13_Rev9_consolidated.pdf",
        "local_source": "UN_R13_Rev9_consolidated.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.12/Rev.9"),
        "status": "downloadable",
    },
    {
        "domain": "braking_base",
        "region": "un_eu",
        "code": "EU 2015/68",
        "title": "Agricultural and forestry vehicle braking requirements",
        "filename": "EU_2015_68.pdf",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32015R0068",
        "status": "downloadable",
    },
    {
        "domain": "braking_base",
        "region": "usa",
        "code": "FMVSS 121",
        "title": "Air brake systems",
        "filename": "FMVSS_121_49CFR571.121.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.121",
        "status": "downloadable",
    },
    {
        "domain": "braking_base",
        "region": "usa",
        "code": "FMVSS 105",
        "title": "Hydraulic and electric brake systems",
        "filename": "FMVSS_105_49CFR571.105.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.105",
        "status": "downloadable",
    },
    # ESC / EVSC
    {
        "domain": "esc_evsc",
        "region": "china",
        "code": "GB/T 30677",
        "title": "ESC performance requirements and test methods",
        "filename": "GBT_30677_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "esc_evsc",
        "region": "china",
        "code": "GB 7258",
        "title": "Mandatory installation requirements referenced for tractors and trailers",
        "filename": "GB_7258_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "esc_evsc",
        "region": "un_eu",
        "code": "UN R13 Annex 21",
        "title": "Vehicle stability function for heavy vehicles",
        "filename": "UN_R13_Rev9_consolidated.pdf",
        "local_source": "UN_R13_Rev9_consolidated.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.12/Rev.9"),
        "status": "downloadable",
    },
    {
        "domain": "esc_evsc",
        "region": "un_eu",
        "code": "UN R140",
        "title": "Electronic Stability Control systems",
        "filename": "UN_R140.pdf",
        "source_url": undoc("E/ECE/324/Rev.2/Add.139"),
        "status": "downloadable",
    },
    {
        "domain": "esc_evsc",
        "region": "usa",
        "code": "FMVSS 136",
        "title": "Electronic stability control systems for heavy vehicles",
        "filename": "FMVSS_136_49CFR571.136.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.136",
        "status": "downloadable",
    },
    # AEB / AEBS
    {
        "domain": "aeb_aebs",
        "region": "china",
        "code": "GB 38187",
        "title": "AEBS requirements for commercial vehicles",
        "filename": "GB_38187_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "aeb_aebs",
        "region": "china",
        "code": "GB/T 39901",
        "title": "AEB performance for operating freight vehicles",
        "filename": "GBT_39901_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "aeb_aebs",
        "region": "un_eu",
        "code": "UN R131",
        "title": "Advanced Emergency Braking Systems",
        "filename": "UN_R131_Rev2.pdf",
        "source_url": undoc("E/ECE/324/Rev.2/Add.130/Rev.2"),
        "status": "downloadable",
    },
    {
        "domain": "aeb_aebs",
        "region": "un_eu",
        "code": "EU 2019/2144",
        "title": "General Safety Regulation",
        "filename": "EU_2019_2144_GSR.pdf",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32019R2144",
        "status": "downloadable",
    },
    {
        "domain": "aeb_aebs",
        "region": "usa",
        "code": "FMVSS 127",
        "title": "Automatic emergency braking for light vehicles",
        "filename": "FMVSS_127_49CFR571.127.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.127",
        "status": "downloadable",
    },
    {
        "domain": "aeb_aebs",
        "region": "usa",
        "code": "Heavy vehicle AEB final rule",
        "title": "NHTSA/FMCSA heavy vehicle AEB rulemaking",
        "filename": "US_heavy_vehicle_AEB_rulemaking_metadata.json",
        "source_url": "https://www.nhtsa.gov/laws-regulations/advanced-driver-assistance-systems",
        "status": "metadata_only",
        "note": "No stable FMVSS section equivalent was added to eCFR in this corpus run.",
    },
    # LDWS / LKA
    {
        "domain": "ldws_lka",
        "region": "china",
        "code": "GB/T 38186",
        "title": "LDWS for commercial vehicles",
        "filename": "GBT_38186_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "ldws_lka",
        "region": "china",
        "code": "GB/T 39323",
        "title": "Lane keeping assistance for trucks",
        "filename": "GBT_39323_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "ldws_lka",
        "region": "un_eu",
        "code": "UN R130",
        "title": "Lane Departure Warning System",
        "filename": "UN_R130.pdf",
        "source_url": undoc("E/ECE/324/Rev.2/Add.129"),
        "status": "downloadable",
    },
    {
        "domain": "ldws_lka",
        "region": "un_eu",
        "code": "EU 2019/2144",
        "title": "General Safety Regulation lane requirements",
        "filename": "EU_2019_2144_GSR.pdf",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32019R2144",
        "status": "downloadable",
    },
    {
        "domain": "ldws_lka",
        "region": "usa",
        "code": "FMCSA guidance",
        "title": "No standalone mandatory FMVSS identified for heavy truck LDWS/LKA",
        "filename": "US_LDWS_LKA_metadata.json",
        "status": "metadata_only",
    },
    # BSIS / MOIS
    {
        "domain": "bsis_mois",
        "region": "china",
        "code": "GB/T 39265",
        "title": "Blind spot detection",
        "filename": "GBT_39265_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "bsis_mois",
        "region": "china",
        "code": "GB/T 41797",
        "title": "Forward pedestrian/collision related requirements",
        "filename": "GBT_41797_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "bsis_mois",
        "region": "un_eu",
        "code": "UN R151",
        "title": "Blind Spot Information System",
        "filename": "UN_R151.pdf",
        "source_url": undoc("E/ECE/TRANS/505/Rev.3/Add.150"),
        "status": "downloadable",
    },
    {
        "domain": "bsis_mois",
        "region": "un_eu",
        "code": "UN R159",
        "title": "Moving Off Information System",
        "filename": "UN_R159.pdf",
        "source_url": undoc("E/ECE/TRANS/505/Rev.3/Add.158"),
        "status": "downloadable",
    },
    {
        "domain": "bsis_mois",
        "region": "usa",
        "code": "No direct FMVSS",
        "title": "No corresponding mandatory FMVSS identified",
        "filename": "US_BSIS_MOIS_metadata.json",
        "status": "metadata_only",
    },
    # Steering & AD
    {
        "domain": "steering_ad",
        "region": "china",
        "code": "GB 17675",
        "title": "Steering system structure and performance",
        "filename": "GB_17675_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "steering_ad",
        "region": "china",
        "code": "GB/T 40465",
        "title": "Combined driver assistance for commercial vehicles",
        "filename": "GBT_40465_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "steering_ad",
        "region": "un_eu",
        "code": "UN R79",
        "title": "Steering equipment",
        "filename": "UN_R79_Rev5.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.78/Rev.5"),
        "status": "downloadable",
    },
    {
        "domain": "steering_ad",
        "region": "un_eu",
        "code": "UN R157",
        "title": "Automated Lane Keeping Systems",
        "filename": "UN_R157_Rev1.pdf",
        "source_url": undoc("E/ECE/TRANS/505/Rev.3/Add.156/Rev.1"),
        "status": "downloadable",
    },
    {
        "domain": "steering_ad",
        "region": "usa",
        "code": "FMVSS 203",
        "title": "Impact protection for the driver from the steering control system",
        "filename": "FMVSS_203_49CFR571.203.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.203",
        "status": "downloadable",
    },
    {
        "domain": "steering_ad",
        "region": "usa",
        "code": "FMVSS 204",
        "title": "Steering control rearward displacement",
        "filename": "FMVSS_204_49CFR571.204.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.204",
        "status": "downloadable",
    },
    # Axle & suspension
    {
        "domain": "axle_suspension",
        "region": "china",
        "code": "GB 1589",
        "title": "Dimensions, axle load and masses",
        "filename": "GB_1589_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "axle_suspension",
        "region": "china",
        "code": "GB 7258",
        "title": "Safety configuration requirements",
        "filename": "GB_7258_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "axle_suspension",
        "region": "un_eu",
        "code": "EU 1230/2012",
        "title": "Masses and dimensions for motor vehicles and trailers",
        "filename": "EU_1230_2012.pdf",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32012R1230",
        "status": "downloadable",
    },
    {
        "domain": "axle_suspension",
        "region": "un_eu",
        "code": "UN R13",
        "title": "Air suspension and braking related annexes",
        "filename": "UN_R13_Rev9_consolidated.pdf",
        "local_source": "UN_R13_Rev9_consolidated.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.12/Rev.9"),
        "status": "downloadable",
    },
    {
        "domain": "axle_suspension",
        "region": "usa",
        "code": "FMVSS 121",
        "title": "Brake distribution and air brake requirements",
        "filename": "FMVSS_121_49CFR571.121.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.121",
        "status": "downloadable",
    },
    {
        "domain": "axle_suspension",
        "region": "usa",
        "code": "Federal Bridge Formula",
        "title": "Federal Bridge Formula / state bridge laws",
        "filename": "US_Federal_Bridge_Formula_metadata.json",
        "source_url": "https://ops.fhwa.dot.gov/freight/publications/brdg_frm_wghts/",
        "status": "metadata_only",
    },
    # EV safety & charging
    {
        "domain": "ev_safety_charging",
        "region": "china",
        "code": "GB 18384",
        "title": "Electric vehicle safety requirements",
        "filename": "GB_18384_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "ev_safety_charging",
        "region": "china",
        "code": "GB 38031",
        "title": "Electric vehicle traction battery safety requirements",
        "filename": "GB_38031_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "ev_safety_charging",
        "region": "china",
        "code": "GB/T 18487",
        "title": "Conductive charging system",
        "filename": "GBT_18487_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "ev_safety_charging",
        "region": "china",
        "code": "GB/T 20234",
        "title": "Charging coupler/interface",
        "filename": "GBT_20234_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "ev_safety_charging",
        "region": "un_eu",
        "code": "UN R100",
        "title": "Electric power train safety",
        "filename": "UN_R100_Rev3.pdf",
        "source_url": undoc("E/ECE/324/Rev.2/Add.99/Rev.3"),
        "status": "downloadable",
    },
    {
        "domain": "ev_safety_charging",
        "region": "un_eu",
        "code": "UN R136",
        "title": "Electric motorcycles and other category L vehicles",
        "filename": "UN_R136.pdf",
        "source_url": undoc("E/ECE/324/Rev.2/Add.135"),
        "status": "downloadable",
    },
    {
        "domain": "ev_safety_charging",
        "region": "un_eu",
        "code": "ISO 15118",
        "title": "Vehicle-to-grid communication interface",
        "filename": "ISO_15118_metadata.json",
        "source_url": "https://www.iso.org/standard/77845.html",
        "status": "metadata_only",
        "note": "ISO standards are paywalled; metadata only.",
    },
    {
        "domain": "ev_safety_charging",
        "region": "usa",
        "code": "FMVSS 305",
        "title": "Electric-powered vehicles: electrolyte spillage and electrical shock protection",
        "filename": "FMVSS_305_49CFR571.305.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.305",
        "status": "downloadable",
    },
    {
        "domain": "ev_safety_charging",
        "region": "usa",
        "code": "SAE J1772",
        "title": "SAE conductive charge coupler",
        "filename": "SAE_J1772_metadata.json",
        "source_url": "https://www.sae.org/standards/content/j1772_202401/",
        "status": "metadata_only",
        "note": "SAE standards are paywalled; metadata only.",
    },
    {
        "domain": "ev_safety_charging",
        "region": "usa",
        "code": "SAE J3105",
        "title": "Electric vehicle power transfer system using conductive automated connection devices",
        "filename": "SAE_J3105_metadata.json",
        "source_url": "https://www.sae.org/standards/content/j3105_202002/",
        "status": "metadata_only",
        "note": "SAE standards are paywalled; metadata only.",
    },
    # Visibility & lighting
    {
        "domain": "visibility_lighting",
        "region": "china",
        "code": "GB 15084",
        "title": "Devices for indirect vision and installation requirements",
        "filename": "GB_15084_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "visibility_lighting",
        "region": "china",
        "code": "GB 4785",
        "title": "Installation of lighting and light-signalling devices",
        "filename": "GB_4785_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "visibility_lighting",
        "region": "un_eu",
        "code": "UN R46",
        "title": "Devices for indirect vision",
        "filename": "UN_R46_Rev6.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.45/Rev.6"),
        "status": "downloadable",
    },
    {
        "domain": "visibility_lighting",
        "region": "un_eu",
        "code": "UN R48",
        "title": "Installation of lighting and light-signalling devices",
        "filename": "UN_R48_Rev12.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.47/Rev.12"),
        "status": "downloadable",
    },
    {
        "domain": "visibility_lighting",
        "region": "usa",
        "code": "FMVSS 108",
        "title": "Lamps, reflective devices, and associated equipment",
        "filename": "FMVSS_108_49CFR571.108.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.108",
        "status": "downloadable",
    },
    {
        "domain": "visibility_lighting",
        "region": "usa",
        "code": "FMVSS 111",
        "title": "Rear visibility",
        "filename": "FMVSS_111_49CFR571.111.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.111",
        "status": "downloadable",
    },
    # Underrun and external protection
    {
        "domain": "underrun_protection",
        "region": "china",
        "code": "GB 11567",
        "title": "Side and rear lower protection requirements for motor vehicles and trailers",
        "filename": "GB_11567_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "underrun_protection",
        "region": "china",
        "code": "GB 26511",
        "title": "Front underrun protective requirements for commercial vehicles",
        "filename": "GB_26511_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "underrun_protection",
        "region": "un_eu",
        "code": "UN R58",
        "title": "Rear underrun protection",
        "filename": "UN_R58_Rev3.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.57/Rev.3"),
        "status": "downloadable",
    },
    {
        "domain": "underrun_protection",
        "region": "un_eu",
        "code": "UN R73",
        "title": "Lateral protection devices",
        "filename": "UN_R73_Rev1.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.72/Rev.1"),
        "status": "downloadable",
    },
    {
        "domain": "underrun_protection",
        "region": "un_eu",
        "code": "UN R93",
        "title": "Front underrun protective devices",
        "filename": "UN_R93.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.92"),
        "status": "downloadable",
    },
    {
        "domain": "underrun_protection",
        "region": "usa",
        "code": "FMVSS 223",
        "title": "Rear impact guards",
        "filename": "FMVSS_223_49CFR571.223.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.223",
        "status": "downloadable",
    },
    {
        "domain": "underrun_protection",
        "region": "usa",
        "code": "FMVSS 224",
        "title": "Rear impact protection",
        "filename": "FMVSS_224_49CFR571.224.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.224",
        "status": "downloadable",
    },
    # EMC and connectivity
    {
        "domain": "emc_connectivity",
        "region": "china",
        "code": "GB 34660",
        "title": "Road vehicles electromagnetic compatibility requirements and test methods",
        "filename": "GB_34660_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "emc_connectivity",
        "region": "un_eu",
        "code": "UN R10",
        "title": "Electromagnetic compatibility",
        "filename": "UN_R10_Rev6.pdf",
        "source_url": undoc("E/ECE/324/Add.9/Rev.6"),
        "status": "downloadable",
    },
    {
        "domain": "emc_connectivity",
        "region": "un_eu",
        "code": "UN R155",
        "title": "Cyber security and cyber security management system",
        "filename": "UN_R155.pdf",
        "source_url": undoc("E/ECE/TRANS/505/Rev.3/Add.154"),
        "status": "downloadable",
    },
    {
        "domain": "emc_connectivity",
        "region": "un_eu",
        "code": "UN R156",
        "title": "Software update and software update management system",
        "filename": "UN_R156.pdf",
        "source_url": undoc("E/ECE/TRANS/505/Rev.3/Add.155"),
        "status": "downloadable",
    },
    # Emissions and noise
    {
        "domain": "emissions_noise",
        "region": "china",
        "code": "GB 17691",
        "title": "Heavy-duty diesel and gas fuelled vehicle emission limits and measurement methods",
        "filename": "GB_17691_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "emissions_noise",
        "region": "china",
        "code": "GB 1495",
        "title": "Limits and measurement methods for noise emitted by accelerating motor vehicles",
        "filename": "GB_1495_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "emissions_noise",
        "region": "un_eu",
        "code": "UN R49",
        "title": "Emissions of compression ignition and positive ignition engines",
        "filename": "UN_R49_Rev7.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.48/Rev.7"),
        "status": "downloadable",
    },
    {
        "domain": "emissions_noise",
        "region": "un_eu",
        "code": "UN R51",
        "title": "Noise emissions",
        "filename": "UN_R51_Rev3.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.50/Rev.3"),
        "status": "downloadable",
    },
    {
        "domain": "emissions_noise",
        "region": "usa",
        "code": "EPA heavy-duty emissions",
        "title": "Heavy-duty highway compression-ignition emission standards",
        "filename": "US_EPA_heavy_duty_emissions_metadata.json",
        "source_url": "https://www.ecfr.gov/current/title-40/chapter-I/subchapter-U/part-1037",
        "status": "metadata_only",
    },
    # Tires, wheels and rims
    {
        "domain": "tires_wheels",
        "region": "china",
        "code": "GB 9744",
        "title": "Truck tyres",
        "filename": "GB_9744_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "tires_wheels",
        "region": "un_eu",
        "code": "UN R54",
        "title": "Pneumatic tyres for commercial vehicles and trailers",
        "filename": "UN_R54_Rev3.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.53/Rev.3"),
        "status": "downloadable",
    },
    {
        "domain": "tires_wheels",
        "region": "un_eu",
        "code": "UN R117",
        "title": "Tyre rolling sound emissions, adhesion and rolling resistance",
        "filename": "UN_R117_Rev4.pdf",
        "source_url": undoc("E/ECE/324/Rev.2/Add.116/Rev.4"),
        "status": "downloadable",
    },
    {
        "domain": "tires_wheels",
        "region": "usa",
        "code": "FMVSS 119",
        "title": "New pneumatic tires for vehicles over 4,536 kg GVWR",
        "filename": "FMVSS_119_49CFR571.119.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.119",
        "status": "downloadable",
    },
    {
        "domain": "tires_wheels",
        "region": "usa",
        "code": "FMVSS 120",
        "title": "Tire selection and rims for vehicles over 4,536 kg GVWR",
        "filename": "FMVSS_120_49CFR571.120.xml",
        "source_url": "https://www.ecfr.gov/api/versioner/v1/full/current/title-49.xml?part=571&section=571.120",
        "status": "downloadable",
    },
    # Coupling devices and rear marking
    {
        "domain": "coupling_marking",
        "region": "china",
        "code": "GB/T 32860",
        "title": "Road vehicles drawbar couplings and fifth wheel couplings metadata",
        "filename": "GBT_32860_metadata.json",
        "status": "metadata_only",
    },
    {
        "domain": "coupling_marking",
        "region": "un_eu",
        "code": "UN R55",
        "title": "Mechanical coupling components",
        "filename": "UN_R55_Rev3.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.54/Rev.3"),
        "status": "downloadable",
    },
    {
        "domain": "coupling_marking",
        "region": "un_eu",
        "code": "UN R70",
        "title": "Rear marking plates for heavy and long vehicles",
        "filename": "UN_R70_Rev1.pdf",
        "source_url": undoc("E/ECE/324/Rev.1/Add.69/Rev.1"),
        "status": "downloadable",
    },
]


def target_path(entry: dict) -> Path:
    return CORPUS / DOMAINS[entry["domain"]] / entry["region"] / entry["filename"]


def write_metadata(entry: dict, target: Path, reason: str | None = None) -> None:
    payload = dict(entry)
    payload["download_result"] = reason or entry.get("status", "metadata_only")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def looks_like_pdf(path: Path) -> bool:
    return path.exists() and path.read_bytes()[:4] == b"%PDF"


def looks_like_xml(path: Path) -> bool:
    if not path.exists():
        return False
    head = path.read_bytes()[:120].lstrip()
    return head.startswith(b"<?xml") or head.startswith(b"<")


def download(entry: dict, target: Path) -> tuple[str, int]:
    request = Request(entry["source_url"], headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=180) as response:
        body = response.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return "downloaded", len(body)


def ensure_govinfo_volume() -> Path:
    cache = CORPUS / "_cache" / "CFR-2024-title49-vol6.xml"
    if cache.exists() and cache.stat().st_size > 1_000_000:
        return cache
    status, size = download({"source_url": GOVINFO_CFR_2024_TITLE49_VOL6}, cache)
    if status != "downloaded" or size < 1_000_000:
        raise OSError("Could not download govinfo CFR Title 49 volume 6")
    return cache


def extract_fmvss(entry: dict, target: Path) -> tuple[str, int]:
    section_no = entry["source_url"].rsplit("section=", 1)[-1]
    volume = ensure_govinfo_volume()
    root = ET.parse(volume).getroot()
    for section in root.iter("SECTION"):
        sectno = section.findtext("SECTNO")
        normalized = "".join(ch for ch in (sectno or "") if ch.isdigit() or ch == ".")
        if normalized == section_no:
            target.parent.mkdir(parents=True, exist_ok=True)
            body = ET.tostring(section, encoding="utf-8", xml_declaration=True)
            target.write_bytes(body)
            return "extracted_govinfo_2024", len(body)
    raise OSError(f"Section {section_no} not found in govinfo CFR 2024 title 49 volume 6")


def copy_local(entry: dict, target: Path) -> tuple[str, int]:
    source = SOURCES / entry["local_source"]
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return "copied", target.stat().st_size


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    manifest = []
    for entry in ENTRIES:
        target = target_path(entry)
        result = {"path": str(target.relative_to(ROOT))}
        try:
            if entry["status"] in {"metadata_only"}:
                write_metadata(entry, target, "metadata_only")
                result["status"] = "metadata_only"
            elif entry.get("local_source"):
                status, size = copy_local(entry, target)
                result.update({"status": status, "bytes": size})
                write_metadata(entry, target, status)
            elif entry["filename"].startswith("FMVSS_"):
                if target.exists() and target.stat().st_size > 0:
                    result.update({"status": "exists", "bytes": target.stat().st_size})
                else:
                    status, size = extract_fmvss(entry, target)
                    result.update({"status": status, "bytes": size})
                write_metadata(entry, target, result["status"])
            else:
                if target.exists() and target.stat().st_size > 0:
                    result.update({"status": "exists", "bytes": target.stat().st_size})
                else:
                    status, size = download(entry, target)
                    result.update({"status": status, "bytes": size})
                    time.sleep(0.25)
                write_metadata(entry, target, result["status"])
            if target.suffix.lower() == ".pdf" and target.exists() and not looks_like_pdf(target):
                result["warning"] = "not_pdf_header"
            if target.suffix.lower() == ".xml" and target.exists() and not looks_like_xml(target):
                result["warning"] = "not_xml_like"
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            result.update({"status": "failed", "error": str(exc)})
            write_metadata(entry, target, f"failed: {exc}")
        manifest.append({**entry, **result})
        print(f"{result['status']:>13} {entry['code']} -> {result['path']}")

    (CORPUS / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
