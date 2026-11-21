"""Teste la connexion BigQuery : authentification, dataset, requête, droit d'écriture.

Usage : python scripts/test_bigquery.py
"""
from google.cloud import bigquery
from google.oauth2 import service_account

KEY = "secrets/gcp-key.json"
DATASET = "velib_data_base"

creds = service_account.Credentials.from_service_account_file(KEY)
client = bigquery.Client(credentials=creds, project=creds.project_id)
print("Projet :", client.project)

# 1. Authentification + droit de lancer un job
print("SELECT 1 ->", list(client.query("SELECT 1 AS ok").result())[0].ok)

# 2. Le dataset existe-t-il, et dans quelle région ?
ds = client.get_dataset(f"{client.project}.{DATASET}")
print(f"Dataset {ds.dataset_id} : région {ds.location}")

# 3. Droit d'écriture : charge 1 ligne par load job (le streaming est interdit sans facturation)
table_id = f"{client.project}.{DATASET}._connection_test"
job = client.load_table_from_json(
    [{"x": 1}], table_id,
    job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE", autodetect=True),
)
job.result()
print("Écriture OK :", client.get_table(table_id).num_rows, "ligne(s) dans", table_id)
client.delete_table(table_id)
print("Table de test supprimée. Tout fonctionne.")
