FROM apache/airflow:2.10.5-python3.12

# Deux venv séparés : évite les conflits de dépendances avec Airflow lui-même.
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /home/airflow/velib_venv \
 && /home/airflow/velib_venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
 && python -m venv /home/airflow/dbt_venv \
 && /home/airflow/dbt_venv/bin/pip install --no-cache-dir \
      "dbt-bigquery==1.12.4" "dbt-core==1.13.0b1"   # versions testées (dbt-core est une préversion)
