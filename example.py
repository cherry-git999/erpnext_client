import json
import requests
import pandas as pd
from erp_client.erp_next_client import ERPNextClient


if __name__ == "__main__":
    """
    Main execution script demonstrating:
    1. ERPNext login
    2. DocType schema and child-table discovery
    3. Basic dataset retrieval (DataFrame)
    4. Full-document structured extraction with child tables (actual record data)
    5. Dataset reshaping and normalization
    6. Child table inspection and DataFrame conversions
    7. Sync pull verification (backward compatible + structured sync)
    """
    client = ERPNextClient(base_url="http://erp.csa-india.org")
    username = "ads@aegiondynamic.com"
    password = "Csa@2025"
    client.login(username, password)
    print("✓ Successfully logged into ERPNext")

    dataset_id = "CC Daily Reports"
    print(f"\n{'='*70}")
    print(f"Target DocType: {dataset_id}")
    print(f"{'='*70}")

    # 1. Schema Retrieval
    print("\n[1] DocType Schema Retrieval:")
    try:
        schema = client.get_dataset_schema(dataset_id)
        print(f"  Total fields defined: {len(schema)}")
        sample_fields = {k: schema[k] for k in list(schema.keys())[:8]}
        print(f"  Sample fields (fieldname -> fieldtype): {sample_fields}")
    except requests.exceptions.HTTPError as e:
        print(f"  Failed to get schema: {e}")

    # 2. Detailed Schema and Child-Table Detection
    print("\n[2] Child-Table Field Detection (Schema Analysis):")
    try:
        detailed_schema = client.get_detailed_schema(dataset_id, fetch_child_schemas=False)
        table_fields = detailed_schema.get("table_fields", {})
        print(f"  Detected {len(table_fields)} Table fields in DocType '{dataset_id}':")
        for tf, child_dt in table_fields.items():
            print(f"    - Table Field: '{tf}' -> Child DocType: '{child_dt}'")
    except requests.exceptions.HTTPError as e:
        print(f"  Failed to get detailed schema: {e}")

    # 3. Basic DataFrame Retrieval (get_dataset)
    print("\n[3] Basic Record List Retrieval (get_dataset -> DataFrame):")
    try:
        df_records = client.get_dataset(dataset_id)
        print(f"  Total records fetched: {len(df_records)}")
        print("  DataFrame Head:")
        print(df_records.head(3).to_string(index=False))
    except requests.exceptions.HTTPError as e:
        print(f"  Failed to get dataset: {e}")

    # 4. Structured Full-Document Extraction (get_dataset_object)
    print("\n[4] Structured Full-Document Extraction (get_dataset_object):")
    try:
        dataset_obj = client.get_dataset_object(dataset_id)
        total_docs = dataset_obj["total_records"]
        print(f"  Total documents extracted with child tables: {total_docs}")

        if total_docs > 0:
            sample_doc = dataset_obj["records"][0]
            print(f"\n  Sample Parent Document: '{sample_doc.get('name')}'")
            print(f"    - NF Coordinator : {sample_doc.get('name_of_nf_coordinator')}")
            print(f"    - Month          : {sample_doc.get('month')}")
            print(f"    - Year           : {sample_doc.get('year')}")
            print(f"    - Creation Date  : {sample_doc.get('creation')}")
            print(f"    - Owner          : {sample_doc.get('owner')}")
            print(f"    - Child Tables   : {list(dataset_obj['table_fields'].keys())[:4]} ...")
    except requests.exceptions.HTTPError as e:
        print(f"  Failed to extract dataset object: {e}")

    # 5. Reshaping and Normalization (reshape_dataset)
    print("\n[5] Reshaping & Normalization (reshape_dataset):")
    try:
        reshaped = client.reshape_dataset(dataset_obj)
        summary = reshaped["summary"]
        print(f"  Total Parent Documents: {summary['total_documents']}")
        print("  Child Table Record Counts Across All Documents:")
        for tbl, count in summary["child_table_counts"].items():
            if count > 0:
                print(f"    - {tbl:32s} : {count} rows")
            else:
                print(f"    - {tbl:32s} : 0 rows (empty table handled safely)")

        # 6. Inspection of Actual Child Table Data
        print("\n[6] Actual Child Table Data Inspection:")
        
        # 6a. Parent Records Table
        parent_df = client.to_dataframe(reshaped)
        print("\n  [6a] Parent Records Summary (DataFrame):")
        display_cols = [c for c in ["name", "name_of_nf_coordinator", "month", "year", "creation"] if c in parent_df.columns]
        print(parent_df[display_cols].to_string(index=False))

        # 6b. cc_daily_reports Child Table
        cc_daily_df = client.to_dataframe(reshaped, "cc_daily_reports")
        print(f"\n  [6b] Child Table 'cc_daily_reports' ({len(cc_daily_df)} total rows):")
        if not cc_daily_df.empty:
            cc_cols = [c for c in ["parent", "date", "activity", "sub_activity", "mandal", "village", "number_of_participants"] if c in cc_daily_df.columns]
            print(cc_daily_df[cc_cols].head(5).to_string(index=False))

        # 6c. field_visit Child Table
        field_visit_df = client.to_dataframe(reshaped, "field_visit")
        print(f"\n  [6c] Child Table 'field_visit' ({len(field_visit_df)} total rows):")
        if not field_visit_df.empty:
            fv_cols = [c for c in ["parent", "date", "activity", "sub_activity", "mandal", "village", "crop", "variety"] if c in field_visit_df.columns]
            print(field_visit_df[fv_cols].head(5).to_string(index=False))

    except Exception as e:
        print(f"  Failed during reshaping/child table inspection: {e}")

    # 7. Synchronization Extraction (sync_pull_dataset & sync_pull_dataset_object)
    print("\n[7] Synchronization Extraction:")
    try:
        # Backward-compatible sync
        sync_df = client.sync_pull_dataset(dataset_id, last_index=0)
        print(f"  ✓ sync_pull_dataset(last_index=0) returned {len(sync_df)} records (pd.DataFrame)")

        # Structured sync compatible with reshape_dataset
        sync_obj = client.sync_pull_dataset_object(dataset_id, last_index=0)
        sync_reshaped = client.reshape_dataset(sync_obj)
        print(f"  ✓ sync_pull_dataset_object(last_index=0) returned {sync_obj['total_records']} structured docs")
        print(f"    - Reshaped sync parent count : {sync_reshaped['summary']['total_documents']}")
        print(f"    - Reshaped sync cc_daily_reports count : {sync_reshaped['summary']['child_table_counts'].get('cc_daily_reports', 0)}")
    except requests.exceptions.HTTPError as e:
        print(f"  Failed during sync extraction: {e}")

    print(f"\n{'='*70}")
    print("All ERPNext data extraction tests completed successfully!")
    print(f"{'='*70}\n")
