import json
import requests
import pandas as pd
from erp_client.erp_next_client import ERPNextClient


if __name__ == "__main__":
    """
    Main execution script demonstrating ERPNext data extraction for:
    - DocTypes (e.g. 'CC Daily Reports')
    - Query Reports (e.g. 'Stock Balance')
    """
    client = ERPNextClient(base_url="http://erp.csa-india.org")
    username = "[EMAIL_ADDRESS]"
    password = "[PASSWORD]"

    errors = []

    try:
        client.login(username, password)
        print("✓ Authentication successful")
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        errors.append(f"Login: {e}")
        exit(1)

    # Configure target dataset and source type:
    # Option 1: source_type = "query_report", dataset_id = "Stock Balance"
    # Option 2: source_type = "doctype", dataset_id = "CC Daily Reports" (on http://erp.csa-india.org)
    source_type = "doctype"
    dataset_id = "CC Daily Reports" 

    print(f"\n{'='*70}")
    print(f"Target Source Type : {source_type}")
    print(f"Target Dataset ID  : {dataset_id}")
    print(f"{'='*70}")

    if source_type == "query_report":
        # Query Report Execution Flow
        print(f"\n[1] Executing Query Report: '{dataset_id}'")

        # Sensible filter parameters for Stock Balance
        report_filters = {
            "company": "Jeevanadatha FPCL",
            "from_date": "2024-01-01",
            "to_date": "2026-12-31",
        }
        print(f"  Applied Filters: {report_filters}")

        report_data = None
        try:
            report_data = client.run_query_report(
                report_name=dataset_id,
                filters=report_filters,
                ignore_prepared_report=True,
            )
            print("  ✓ Query Report executed")
            print("  ✓ Data retrieved")
            print(f"  Total records returned : {report_data['total_records']}")
            print(f"  Total columns detected : {len(report_data['columns'])}")
            print(f"  Column names           : {report_data['column_fieldnames']}")
            if report_data.get("total_row"):
                print("  Summary / Total row    : Detected and separated cleanly")
        except Exception as e:
            print(f"  ✗ Query Report execution failed: {e}")
            errors.append(f"Query Report execution: {e}")

        # Convert to DataFrame
        if report_data and report_data.get("records"):
            try:
                df = client.to_dataframe(report_data)
                print(f"\n[2] DataFrame Representation (Shape: {df.shape}):")
                print("  ✓ DataFrame created")

                # Show key columns
                preview_cols = [
                    c
                    for c in [
                        "item_code",
                        "item_name",
                        "item_group",
                        "warehouse",
                        "bal_qty",
                        "bal_val",
                        "in_qty",
                        "out_qty",
                    ]
                    if c in df.columns
                ]
                if not preview_cols:
                    preview_cols = list(df.columns)[:8]
                print("\n" + df[preview_cols].head(5).to_string(index=False))
            except Exception as e:
                print(f"  ✗ DataFrame creation failed: {e}")
                errors.append(f"DataFrame creation: {e}")

    elif source_type == "doctype":
        # DocType Execution Flow
        print("\n[1] DocType Schema Retrieval:")
        try:
            schema = client.get_dataset_schema(dataset_id)
            print(f"  ✓ Schema retrieved ({len(schema)} fields defined)")
            sample_fields = {k: schema[k] for k in list(schema.keys())[:8]}
            print(f"  Sample fields: {sample_fields}")
        except Exception as e:
            print(f"  ✗ Failed to get schema: {e}")
            errors.append(f"Schema retrieval: {e}")

        print("\n[2] Child-Table Field Detection:")
        try:
            detailed_schema = client.get_detailed_schema(
                dataset_id, fetch_child_schemas=False
            )
            table_fields = detailed_schema.get("table_fields", {})
            print(
                f"  ✓ Detected {len(table_fields)} Table fields in DocType '{dataset_id}':"
            )
            for tf, child_dt in table_fields.items():
                print(f"    - Table Field: '{tf}' -> Child DocType: '{child_dt}'")
        except Exception as e:
            print(f"  ✗ Failed to get detailed schema: {e}")
            errors.append(f"Detailed schema: {e}")

        print("\n[3] Basic Record List Retrieval (DataFrame):")
        try:
            df_records = client.get_dataset(dataset_id)
            print(f"  ✓ Total records fetched: {len(df_records)}")
            print(df_records.head(3).to_string(index=False))
        except Exception as e:
            print(f"  ✗ Failed to get dataset: {e}")
            errors.append(f"Dataset retrieval: {e}")

        print("\n[4] Structured Full-Document Extraction:")
        dataset_obj = None
        try:
            dataset_obj = client.get_dataset_object(dataset_id)
            print(
                f"  ✓ Extracted {dataset_obj['total_records']} full documents with child tables"
            )
            if dataset_obj["records"]:
                sample_doc = dataset_obj["records"][0]
                print(
                    f"  Sample document: '{sample_doc.get('name')}' (creation: {sample_doc.get('creation')})"
                )
        except Exception as e:
            print(f"  ✗ Failed to extract dataset object: {e}")
            errors.append(f"Full document extraction: {e}")

        if dataset_obj:
            print("\n[5] Reshaping & Normalization:")
            try:
                reshaped = client.reshape_dataset(dataset_obj)
                summary = reshaped["summary"]
                print(f"  ✓ Reshaped {summary['total_documents']} parent documents")
                print("  Child Table counts:")
                for tbl, count in summary["child_table_counts"].items():
                    if count > 0:
                        print(f"    - {tbl:32s} : {count} rows")

                # Dynamic child table inspection
                populated_tables = [
                    tbl
                    for tbl, count in summary["child_table_counts"].items()
                    if count > 0
                ]
                for tbl in populated_tables[:2]:
                    tbl_df = client.to_dataframe(reshaped, tbl)
                    print(f"\n  Child Table '{tbl}' DataFrame ({len(tbl_df)} rows):")
                    preview_cols = [
                        c for c in tbl_df.columns if not c.startswith("_")
                    ][:6]
                    print(tbl_df[preview_cols].head(3).to_string(index=False))
            except Exception as e:
                print(f"  ✗ Failed during reshaping: {e}")
                errors.append(f"Reshaping: {e}")

        print("\n[6] Synchronization Extraction:")
        try:
            sync_df = client.sync_pull_dataset(dataset_id, last_index=0)
            print(
                f"  ✓ sync_pull_dataset(last_index=0) returned {len(sync_df)} records (pd.DataFrame)"
            )
            sync_obj = client.sync_pull_dataset_object(dataset_id, last_index=0)
            sync_reshaped = client.reshape_dataset(sync_obj)
            print(
                f"  ✓ sync_pull_dataset_object(last_index=0) returned {sync_obj['total_records']} structured docs"
            )
        except Exception as e:
            print(f"  ✗ Failed during sync extraction: {e}")
            errors.append(f"Sync extraction: {e}")

    # Truthful status summary
    print(f"\n{'='*70}")
    if not errors:
        print("✓ All ERPNext extraction steps completed successfully!")
    else:
        print(f"✗ Extraction completed with {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
    print(f"{'='*70}\n")

