"""
One-time script to add sample birth, marriage, and death documents to the Archiving page.
Copies images from the assets folder into uploads/ and creates Record entries.
Run from the app folder: python scripts/seed_sample_documents.py
"""
import json
import shutil
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

BASE_DIR = APP_ROOT
UPLOAD_DIR = BASE_DIR / "uploads"
# Try project assets; fallback to Cursor project folder if images were saved there
ASSETS_DIR = BASE_DIR / "assets"
if not ASSETS_DIR.exists():
    _cursor_assets = Path(r"C:\Users\63951\.cursor\projects\c-daragacivilregistrymanagementsystem\assets")
    if _cursor_assets.exists():
        ASSETS_DIR = _cursor_assets
# Prefer images already in uploads/ when asset files are missing
UPLOADS_FALLBACK = BASE_DIR / "uploads"

# Asset filenames (from Cursor workspace storage); multiple possible names per key if re-saved
_ASSET_PREFIX = "c__Users_63951_AppData_Roaming_Cursor_User_workspaceStorage_f3d677e75fb7ae9dd5d255420fa389fa_images_"

def _asset(name):
    return _ASSET_PREFIX + name

ASSET_FILES = {
    "birth1": _asset("birth_ex1-d8761ea0-953a-4f2b-a335-68ea6cf3ec0c.png"),
    "birth2": _asset("birth_ex2-fe72031c-d639-494b-a913-2f66075f1103.png"),
    "birth3": _asset("birth_ex3-b4c10a7a-04ed-4156-90e9-15a3c1325248.png"),
    "marriage1": _asset("marriage_sample_1-3f03985e-27c2-4141-abf0-14400b12cc72.png"),
    "marriage2": _asset("marriage_sample_2-34e38f49-bbc2-4a7a-a70a-1113da66f00b.png"),
    "marriage3": _asset("Copilot_20260310_164118-a22b9017-39b5-4ffb-bfc8-e9553a711a16.png"),
    "marriage4": _asset("Copilot_20260310_164453-32206ffb-9131-4f69-b02d-1ac315ef91cf.png"),
    "death1": _asset("deathexample-a1ba5aed-f52a-49b7-966d-4b55db58b7e4.png"),
    "death2": _asset("DEATH_SAMPLE-95dc1a99-32a4-4090-92e1-8c08ffda14d8.png"),
    "death3": _asset("Copilot_20260310_155430-12045cf4-da0c-4825-a884-7c7e8f3ed5cb.png"),
    "death4": _asset("Copilot_20260310_155952-b81f5b7a-01a4-4c6c-843c-48316527ec09.png"),
    "death5": _asset("Copilot_20260310_160153-a9913669-d7bf-49d9-a5f4-ec4e13678825.png"),
    "death6": _asset("Copilot_20260310_160349-29a60f17-36f2-4795-a27e-a45c4f945da4.png"),
    "death7": _asset("Copilot_20260310_160915-6341b3f8-7ede-45cc-8d6f-2737699be0c3.png"),
}
# Fallbacks if user re-saved images (new UUIDs)
ASSET_FILES_ALT = {
    "birth1": _asset("birth_ex1-a3338a4b-5eb8-44cd-8612-6e5401280d64.png"),
    "marriage1": _asset("marriage_sample_1-d6396e5a-49c3-4959-bc95-be2e46575471.png"),
    "marriage2": _asset("marriage_sample_2-ee59eaf1-f259-4ebf-aafd-599c3518bcb5.png"),
}

# Sample records: data_json fields + full_name, event_date, registry_number, image_path (after copy)
SAMPLES = [
    {
        "document_type": "birth",
        "registry_number": "34125-07-RE330",
        "full_name": "GABRIEELA REYES MAGBANUA",
        "event_date": "10 FEBRUARY 2021",
        "asset_key": "birth1",
        "archive_basename": "Magbanua_Gabrieela_Reyes_34125-07-RE330_birth.png",
        "data": {
            "Registry Number": "34125-07-RE330",
            "Date of Registration": "",
            "Name of Child": "GABRIEELA REYES MAGBANUA",
            "Sex": "FEMALE",
            "Date of Birth": "10 FEBRUARY 2021",
            "Place of Birth": "UST HOSPITAL, MANILA",
            "Name of Mother": "MARIA CRUZ MAGBANUA",
            "Citizenship of Mother": "FILIPINO",
            "Name of Father": "DANILO MAGBANUA JR.",
            "Citizenship of Father": "FILIPINO",
            "Date of Marriage of Parents": "APRIL 15, 2018, QUEZON CITY",
            "Place of Marriage of Parents": "QUEZON CITY",
            "Remarks": "",
        },
    },
    {
        "document_type": "birth",
        "registry_number": "27981-15-QF952",
        "full_name": "ISABELLA GRACE FERNANDEZ",
        "event_date": "15 AUGUST 2020",
        "asset_key": "birth2",
        "archive_basename": "Fernandez_Isabella_Grace_27981-15-QF952_birth.png",
        "data": {
            "Registry Number": "27981-15-QF952",
            "Date of Registration": "",
            "Name of Child": "ISABELLA GRACE FERNANDEZ",
            "Sex": "FEMALE",
            "Date of Birth": "15 AUGUST 2020",
            "Place of Birth": "ST. LUKE'S MEDICAL CENTER, MUNTINLUPA CITY",
            "Name of Mother": "CARINA CRUZ FERNANDEZ",
            "Citizenship of Mother": "FILIPINO",
            "Name of Father": "MIGUEL FERNANDEZ",
            "Citizenship of Father": "FILIPINO",
            "Date of Marriage of Parents": "FEBRUARY 14, 2016, TAGAYTAY CITY",
            "Place of Marriage of Parents": "TAGAYTAY CITY",
            "Remarks": "",
        },
    },
    {
        "document_type": "marriage",
        "registry_number": "2019-MANILA-001",
        "full_name": "RYAN COOPER SAN ANDRES / ANNE CRUZ",
        "event_date": "22 FEBRUARY 2019",
        "asset_key": "marriage1",
        "archive_basename": "Andres_Ryan_Cooper_San_2019-MANILA-001_marriage.png",
        "data": {
            "Registry Number": "2019-MANILA-001",
            "Date of Registration": "",
            "Date of Marriage": "22 FEBRUARY 2019",
            "Place of Marriage": "MANILA CITY HALL",
            "Husband Name": "RYAN COOPER SAN ANDRES",
            "Husband Age": "40",
            "Husband Citizenship": "FILIPINO",
            "Husband Civil Status": "SINGLE",
            "Husband Father": "ROMAN SAN ANDRES",
            "Husband Mother": "MARIA SAN ANDRES",
            "Wife Name": "ANNE CRUZ",
            "Wife Age": "35",
            "Wife Citizenship": "FILIPINO",
            "Wife Civil Status": "SINGLE",
            "Wife Father": "RECARDO CRUZ",
            "Wife Mother": "—",
        },
    },
    {
        "document_type": "marriage",
        "registry_number": "872817632",
        "full_name": "MARL LOUIS CASTILLO / MARIA DE LA ROSA",
        "event_date": "22 FEBRUARY 2019",
        "asset_key": "marriage2",
        "archive_basename": "Castillo_Marl_Louis_872817632_marriage.png",
        "data": {
            "Registry Number": "872817632",
            "Date of Registration": "",
            "Date of Marriage": "22 FEBRUARY 2019",
            "Place of Marriage": "MANILA CITY HALL",
            "Husband Name": "MARL LOUIS CASTILLO",
            "Husband Age": "28",
            "Husband Citizenship": "FILIPINO",
            "Husband Civil Status": "SINGLE",
            "Husband Father": "REYMON CASTILLO",
            "Husband Mother": "MARIA CASTILLO",
            "Wife Name": "MARIA DE LA ROSA",
            "Wife Age": "26",
            "Wife Citizenship": "FILIPINO",
            "Wife Civil Status": "SINGLE",
            "Wife Father": "JOSE DE LA ROSA",
            "Wife Mother": "MARCELA RAIRES",
        },
    },
    # Marriage sample 3 – MIGUEL ANGELO SANTOS DELA CRUZ / MARIA ISABELLA REYES MENDOZA (Form type 1)
    {
        "document_type": "marriage",
        "registry_number": "2023-0012",
        "full_name": "MIGUEL ANGELO SANTOS DELA CRUZ / MARIA ISABELLA REYES MENDOZA",
        "event_date": "20 MAY 2023",
        "asset_key": "marriage3",
        "archive_basename": "Dela_Cruz_Miguel_Angelo_Santos_2023-0012_marriage.png",
        "data": {
            "Registry Number": "2023-0012",
            "Date of Registration": "",
            "Date of Marriage": "20 MAY 2023",
            "Place of Marriage": "SAN AGUSTIN CHURCH, INTRAMUROS, MANILA",
            "Husband Name": "MIGUEL ANGELO SANTOS DELA CRUZ",
            "Husband Age": "38",
            "Husband Citizenship": "FILIPINO",
            "Husband Civil Status": "SINGLE",
            "Husband Father": "ROBERTO DELA CRUZ",
            "Husband Mother": "TERESITA SANTOS",
            "Wife Name": "MARIA ISABELLA REYES MENDOZA",
            "Wife Age": "34",
            "Wife Citizenship": "FILIPINO",
            "Wife Civil Status": "SINGLE",
            "Wife Father": "MATEO JAVIER",
            "Wife Mother": "ROSARIO REYES",
        },
    },
    # Marriage sample 4 – MIGUEL ANGELO SANTOS DELA CRUZ / MARIA ISABELLA REYES MENDOZA (Form type 2)
    {
        "document_type": "marriage",
        "registry_number": "2023-0881",
        "full_name": "MIGUEL ANGELO SANTOS DELA CRUZ / MARIA ISABELLA REYES MENDOZA",
        "event_date": "20 MAY 2026",
        "asset_key": "marriage4",
        "archive_basename": "Dela_Cruz_Miguel_Angelo_Santos_2023-0881_marriage.png",
        "data": {
            "Registry Number": "2023-0881",
            "Date of Registration": "",
            "Date of Marriage": "20 MAY 2023",
            "Place of Marriage": "SAN AGUSTIN CHURCH, INTRAMUROS, MANILA",
            "Husband Name": "MIGUEL ANGELO SANTOS DELA CRUZ",
            "Husband Age": "38",
            "Husband Citizenship": "FILIPINO",
            "Husband Civil Status": "SINGLE",
            "Husband Father": "ROBERTO DELA CRUZ",
            "Husband Mother": "TERESITA SANTOS",
            "Wife Name": "MARIA ISABELLA REYES MENDOZA",
            "Wife Age": "34",
            "Wife Citizenship": "FILIPINO",
            "Wife Civil Status": "SINGLE",
            "Wife Father": "MATEO JAVIER",
            "Wife Mother": "ROSARIO REYES",
        },
    },
    # Birth sample 3 – RAFAELLA PAZ VILLANUEVA
    {
        "document_type": "birth",
        "registry_number": "31682-09-PF765",
        "full_name": "RAFAELLA PAZ VILLANUEVA",
        "event_date": "12 APRIL 2021",
        "asset_key": "birth3",
        "archive_basename": "Villanueva_Rafaella_Paz_31682-09-PF765_birth.png",
        "data": {
            "Registry Number": "31682-09-PF765",
            "Date of Registration": "",
            "Name of Child": "RAFAELLA PAZ VILLANUEVA",
            "Sex": "FEMALE",
            "Date of Birth": "12 APRIL 2021",
            "Place of Birth": "UST HOSPITAL, MANILA",
            "Name of Mother": "ANDREA LOPEZ VILLANUEVA",
            "Citizenship of Mother": "FILIPINO",
            "Name of Father": "CARLOS MIGUEL VILLANUEVA",
            "Citizenship of Father": "FILIPINO",
            "Date of Marriage of Parents": "MAY 20, 2018, TAGAYTAY CITY",
            "Place of Marriage of Parents": "TAGAYTAY CITY",
            "Remarks": "",
        },
    },
    # Death sample 1 – REVIC BGAGAMAO OTADOY
    {
        "document_type": "death",
        "registry_number": "25-17742",
        "full_name": "REVIC BGAGAMAO OTADOY",
        "event_date": "28 MARCH 2025",
        "asset_key": "death1",
        "archive_basename": "Otadoy_Revic_Bgagamao_25-17742_death.png",
        "data": {
            "Registry Number": "25-17742",
            "Date of Registration": "",
            "Name of Deceased": "REVIC BGAGAMAO OTADOY",
            "Sex": "FEMALE",
            "Age": "63",
            "Civil Status": "MARRIED",
            "Nationality": "FILIPINO",
            "Date of Death": "28 MARCH 2025",
            "Place of Death": "MATI CITY, DAVAO ORIENTAL",
            "Cause of Death": "HEART ATTACK",
        },
    },
    # Death sample 2 – GEORGE DE GUZMAN ABAD
    {
        "document_type": "death",
        "registry_number": "1999-76251",
        "full_name": "GEORGE DE GUZMAN ABAD",
        "event_date": "29 AUGUST 1999",
        "asset_key": "death2",
        "archive_basename": "Abad_George_De_Guzman_1999-76251_death.png",
        "data": {
            "Registry Number": "1999-76251",
            "Date of Registration": "",
            "Name of Deceased": "GEORGE DE GUZMAN ABAD",
            "Sex": "MALE",
            "Age": "46",
            "Civil Status": "MARRIED",
            "Nationality": "FILIPINO",
            "Date of Death": "29 AUGUST 1999",
            "Place of Death": "ANGELES, PAMPANGA",
            "Cause of Death": "CARDIOPULMONARY ARREST",
        },
    },
    # Death sample 3 – JUAN CARLOS SANTOS REYES
    {
        "document_type": "death",
        "registry_number": "2023-0153",
        "full_name": "JUAN CARLOS SANTOS REYES",
        "event_date": "15 MARCH 2023",
        "asset_key": "death3",
        "archive_basename": "Reyes_Juan_Carlos_Santos_2023-0153_death.png",
        "data": {
            "Registry Number": "2023-0153",
            "Date of Registration": "",
            "Name of Deceased": "JUAN CARLOS SANTOS REYES",
            "Sex": "MALE",
            "Age": "67",
            "Civil Status": "MARRIED",
            "Nationality": "FILIPINO",
            "Date of Death": "15 MARCH 2023",
            "Place of Death": "SAN PEDRO HOSPITAL, SAN PEDRO, LAGUNA",
            "Cause of Death": "RESPIRATORY FAILURE; PNEUMONIA; CHRONIC OBSTRUCTIVE PULMONARY DISEASE",
        },
    },
    # Death sample 4 – MARIA FE VILLANUEVA CRUZ
    {
        "document_type": "death",
        "registry_number": "2022-2567",
        "full_name": "MARIA FE VILLANUEVA CRUZ",
        "event_date": "22 JULY 2022",
        "asset_key": "death4",
        "archive_basename": "Cruz_Maria_Fe_Villanueva_2022-2567_death.png",
        "data": {
            "Registry Number": "2022-2567",
            "Date of Registration": "",
            "Name of Deceased": "MARIA FE VILLANUEVA CRUZ",
            "Sex": "FEMALE",
            "Age": "73",
            "Civil Status": "WIDOW",
            "Nationality": "FILIPINO",
            "Date of Death": "22 JULY 2022",
            "Place of Death": "MANDAUE CITY MEDICAL CENTER, MANDAUE CITY, CEBU",
            "Cause of Death": "CARDIOGENIC SHOCK; ACUTE MYOCARDIAL INFARCTION; HYPERTENSIVE HEART DISEASE",
        },
    },
    # Death sample 5 – ANTONIO G. LIM
    {
        "document_type": "death",
        "registry_number": "2023-3891",
        "full_name": "ANTONIO G. LIM",
        "event_date": "03 NOVEMBER 2023",
        "asset_key": "death5",
        "archive_basename": "Lim_Antonio_G_2023-3891_death.png",
        "data": {
            "Registry Number": "2023-3891",
            "Date of Registration": "",
            "Name of Deceased": "ANTONIO G. LIM",
            "Sex": "MALE",
            "Age": "88",
            "Civil Status": "MARRIED",
            "Nationality": "FILIPINO",
            "Date of Death": "03 NOVEMBER 2023",
            "Place of Death": "SOUTHERN PHILIPPINES MEDICAL CENTER, DAVAO CITY",
            "Cause of Death": "SEPTIC SHOCK; URINARY TRACT INFECTION; BENIGN PROSTATIC HYPERPLASIA",
        },
    },
    # Death sample 6 – LUCIA R. MERCEDES
    {
        "document_type": "death",
        "registry_number": "2021-1456",
        "full_name": "LUCIA R. MERCEDES",
        "event_date": "12 JUNE 2021",
        "asset_key": "death6",
        "archive_basename": "Mercedes_Lucia_R_2021-1456_death.png",
        "data": {
            "Registry Number": "2021-1456",
            "Date of Registration": "",
            "Name of Deceased": "LUCIA R. MERCEDES",
            "Sex": "FEMALE",
            "Age": "40",
            "Civil Status": "MARRIED",
            "Nationality": "FILIPINO",
            "Date of Death": "12 JUNE 2021",
            "Place of Death": "BULACAN MEDICAL CENTER, MALOLOS CITY, BULACAN",
            "Cause of Death": "SEPTIC SHOCK; URINARY TRACT INFECTION; ESSENTIAL HYPERTENSION",
        },
    },
    # Death sample 7 – PEDRO M. JAVIER
    {
        "document_type": "death",
        "registry_number": "2022-1789",
        "full_name": "PEDRO M. JAVIER",
        "event_date": "08 FEBRUARY 2022",
        "asset_key": "death7",
        "archive_basename": "Javier_Pedro_M_2022-1789_death.png",
        "data": {
            "Registry Number": "2022-1789",
            "Date of Registration": "",
            "Name of Deceased": "PEDRO M. JAVIER",
            "Sex": "MALE",
            "Age": "53",
            "Civil Status": "MARRIED",
            "Nationality": "FILIPINO",
            "Date of Death": "08 FEBRUARY 2022",
            "Place of Death": "ILOILO DOCTORS' HOSPITAL, ILOILO CITY",
            "Cause of Death": "HYPOVOLEMIC SHOCK; MULTIPLE ORGAN FAILURE; LIVER CIRRHOSIS",
        },
    },
]


def main(reset: bool = False):
    from app import app, UPLOAD_DIR
    from models import db, Record

    UPLOAD_DIR.mkdir(exist_ok=True)
    (UPLOAD_DIR / "birth").mkdir(exist_ok=True)
    (UPLOAD_DIR / "marriage").mkdir(exist_ok=True)
    (UPLOAD_DIR / "death").mkdir(exist_ok=True)

    if not ASSETS_DIR.exists():
        print("Assets folder not found at:", ASSETS_DIR)
        print("Creating sample records without copying images (image_path will be empty).")
        asset_dir_ok = False
    else:
        asset_dir_ok = True

    def get_asset_path(key, sample):
        path = ASSET_FILES.get(key)
        if path and (ASSETS_DIR / path).exists():
            return ASSETS_DIR / path
        alt = ASSET_FILES_ALT.get(key)
        if alt and (ASSETS_DIR / alt).exists():
            return ASSETS_DIR / alt
        existing = UPLOADS_FALLBACK / sample["document_type"] / sample["archive_basename"]
        if existing.exists():
            return existing
        return ASSETS_DIR / ASSET_FILES.get(key, "")

    app.app_context().push()
    db.create_all()

    if reset:
        deleted = Record.query.delete()
        db.session.commit()
        print(f"Cleared {deleted} existing archive record(s).")

    for s in SAMPLES:
        doc_type = s["document_type"]
        image_path = None
        if asset_dir_ok:
            src = get_asset_path(s["asset_key"], s)
            dest_dir = UPLOAD_DIR / doc_type
            dest = dest_dir / s["archive_basename"]
            if src and src.exists():
                try:
                    shutil.copy2(src, dest)
                    image_path = f"{doc_type}/{s['archive_basename']}"
                    print("Copied:", src.name[:50], "->", image_path)
                except Exception as e:
                    print("Copy failed:", e)
            else:
                print("Source not found:", src)
        else:
            print("Skipping image copy for", s["full_name"][:40])

        data_json = json.dumps(s["data"], ensure_ascii=False)
        record = Record(
            document_type=doc_type,
            registry_number=s["registry_number"],
            full_name=s["full_name"],
            event_date=s["event_date"],
            data_json=data_json,
            extracted_json=data_json,
            corrected_json=data_json,
            image_path=image_path,
            image_front_path=image_path or "",
        )
        db.session.add(record)
        print("Added record:", s["full_name"][:50], "|", doc_type)

    db.session.commit()
    print("Done. Sample documents are now in Archiving. Refresh the Archiving page.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load all example birth, marriage, and death documents into Archiving.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove existing archive records first, then insert the full example set (no duplicates).",
    )
    args = parser.parse_args()
    main(reset=args.reset)
