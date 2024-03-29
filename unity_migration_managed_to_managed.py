# Databricks notebook source
# MAGIC %md
# MAGIC # Hive managed tables to UC managed tables
# MAGIC
# MAGIC This notebook will migrate all managed tables from a given source catalog and database to a target catalog
# MAGIC
# MAGIC **Important:**
# MAGIC - This notebook needs to run on a cluster with spark.databricks.sql.initial.catalog.name set to hive_metastore or the base catalog where the external tables will be pulled for cloning
# MAGIC - Optional: table descriptions can be written to a temporary Delta table for portability across workspaces.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

from pyspark.sql.functions import col

source_catalog = "hive_metastore"
source_database = "dbdemos_c360"
destination_catalog = "dbdemos"

# COMMAND ----------

# MAGIC %md
# MAGIC # PART I: Get all tables from Hive Metastore or original catalog
# MAGIC
# MAGIC For this, the initial catalog name must be set to the desired source catalog

# COMMAND ----------

# MAGIC %md
# MAGIC ### Select all EXTERNAL tables from External Metastore

# COMMAND ----------


def get_value(lst, idx, idy, default):
    try:
        return lst[idx][idy]
    except IndexError:
        return default


# COMMAND ----------

# Get all tables from Hive Metastore and source database
# For this you need to set the initial catalog to hive_metastore which is by default

databases=[source_database]
descriptions = []
# Loop through each database/schema
for db in databases:
    # Get all tables from the current database/schema
    print(db)
    tables = spark.sql("show tables in {}".format(db)).select("tableName").collect()

    # Loop through each table and run the describe command
    for table in tables:
        table_name = table.tableName
        try:
            desc = spark.sql(f"DESCRIBE FORMATTED {db}.{table_name}").filter(
                "col_name = 'Location' OR col_name='Database' OR col_name='Table' OR col_name='Type'"
            )
            for info in desc:
                desc_all = desc.collect()
                # catalog_name = get_value(desc_all, 0, 1, "NA")
                database_name = get_value(desc_all, 0, 1, "NA")
                table_name = get_value(desc_all, 1, 1, "NA")
                table_type = get_value(desc_all, 2, 1, "NA")
                table_location = get_value(desc_all, 3, 1, "NA")

                print(f"{database_name}.{table_name} is {table_type} and is located at {table_location}")

            descriptions.append((database_name, table_name, table_type, table_location))
        # To handle missing external tables
        except:
            print(f"Error on {db[0]}.{table_name}.")

# Create DataFrame from the results and only pick managed tables
source_catalog_tables = spark.createDataFrame(
    descriptions, ["database_name", "table_name", "table_type", "table_location"]
).filter("table_type='MANAGED'")

# Optional: Write the DataFrame to a Delta table
# df.write.format("delta").mode("overwrite").save(delta_table_location)

# COMMAND ----------

# MAGIC %md
# MAGIC # PART II - CLONE tables

# COMMAND ----------

# MAGIC %md
# MAGIC ### CLONE all tables

# COMMAND ----------

# Create all missing databases on destination catalog
for database in databases:
    spark.sql(f"CREATE DATABASE IF NOT EXISTS `{destination_catalog}`.{database}")

# COMMAND ----------

# Clone source hive tables into unity managed tables
tables = source_catalog_tables.collect()

for table in tables:
    print(f"Converting table {table[0]}.{table[1]}...")
    spark.sql(
        f"CREATE OR REPLACE TABLE `{destination_catalog}`.{table[0]}.{table[1]} DEEP CLONE {source_catalog}.{table[0]}.{table[1]}"
    )
