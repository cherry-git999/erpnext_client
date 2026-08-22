"""
Data Shaping and Normalization Layer for ERPNext Datasets.

This module is responsible for:
1. Normalizing raw nested ERPNext documents (separating parent scalar fields from child tables).
2. Ensuring relational integrity by attaching parent foreign keys (parent, parenttype, parentfield) to child rows.
3. Converting structured dataset objects or query report results into Pandas DataFrames.
"""

from typing import Any, Dict, List, Optional
import pandas as pd


class DataShaper:
    """
    Transforms raw ERPNext datasets into normalized, predictable structures
    and Pandas DataFrames.
    """

    @staticmethod
    def reshape_dataset(dataset_object: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms a raw ERPNext dataset object into a clean, normalized structure.

        Separates parent document attributes and child-table records without destroying information,
        allowing seamless downstream mapping to dashboards, JSON, DataFrames, or databases.

        Args:
            dataset_object (Dict[str, Any]): Structured dataset from get_dataset_object() or sync_pull_dataset_object().

        Returns:
            Dict[str, Any]: Normalized dataset containing parent_records, child_tables, documents, and summary.
        """
        doctype = dataset_object.get("doctype", "")
        schema = dataset_object.get("schema", {})
        table_fields = dataset_object.get("table_fields", {})
        raw_records = dataset_object.get("records", [])

        parent_records: List[Dict[str, Any]] = []
        child_tables: Dict[str, List[Dict[str, Any]]] = {
            tf: [] for tf in table_fields
        }
        normalized_documents: List[Dict[str, Any]] = []

        for record in raw_records:
            doc_name = record.get("name", "")
            parent_dict: Dict[str, Any] = {}
            doc_tables: Dict[str, List[Dict[str, Any]]] = {}

            # Separate parent scalar fields from child tables
            for k, v in record.items():
                if k in table_fields or isinstance(v, list):
                    # Child table field
                    table_name = k
                    if table_name not in child_tables:
                        child_tables[table_name] = []

                    rows = v if isinstance(v, list) else []
                    normalized_rows = []
                    for row in rows:
                        if isinstance(row, dict):
                            row_copy = dict(row)
                            # Ensure relational links are preserved
                            if "parent" not in row_copy:
                                row_copy["parent"] = doc_name
                            if "parenttype" not in row_copy:
                                row_copy["parenttype"] = doctype
                            if "parentfield" not in row_copy:
                                row_copy["parentfield"] = table_name
                            normalized_rows.append(row_copy)
                            child_tables[table_name].append(row_copy)
                    doc_tables[table_name] = normalized_rows
                else:
                    parent_dict[k] = v

            parent_records.append(parent_dict)
            normalized_documents.append(
                {
                    "name": doc_name,
                    "parent": parent_dict,
                    "tables": doc_tables,
                }
            )

        # Generate summary of counts
        child_table_counts = {
            tf: len(rows) for tf, rows in child_tables.items()
        }

        return {
            "doctype": doctype,
            "schema": schema,
            "table_fields": table_fields,
            "parent_records": parent_records,
            "child_tables": child_tables,
            "documents": normalized_documents,
            "summary": {
                "total_documents": len(parent_records),
                "child_table_counts": child_table_counts,
            },
        }

    @staticmethod
    def to_dataframe(
        data: Any, table_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Converts extracted dataset objects, reshaped structures, or report objects into a Pandas DataFrame.

        Args:
            data (Any): Dataset object, reshaped dataset dictionary, Query Report dict, or list of dicts.
            table_name (Optional[str]): If specified, extracts that child table as a DataFrame.
                                        If None, extracts parent/main records as a DataFrame.

        Returns:
            pd.DataFrame: Converted DataFrame.
        """
        if isinstance(data, pd.DataFrame):
            return data

        if isinstance(data, dict):
            # Query Report object format (from run_query_report)
            if data.get("source_type") == "query_report" and "records" in data:
                return pd.DataFrame(data["records"])

            # Reshaped dataset format
            if "parent_records" in data and "child_tables" in data:
                if table_name is None:
                    return pd.DataFrame(data["parent_records"])
                else:
                    return pd.DataFrame(
                        data["child_tables"].get(table_name, [])
                    )

            # Raw dataset object format (from get_dataset_object)
            if "records" in data:
                if table_name is None:
                    tf_set = set(data.get("table_fields", {}).keys())
                    clean_parents = [
                        {
                            k: v
                            for k, v in r.items()
                            if k not in tf_set and not isinstance(v, list)
                        }
                        for r in data["records"]
                    ]
                    return pd.DataFrame(clean_parents)
                else:
                    all_child_rows = []
                    for r in data["records"]:
                        rows = r.get(table_name, [])
                        if isinstance(rows, list):
                            all_child_rows.extend(rows)
                    return pd.DataFrame(all_child_rows)

        if isinstance(data, list):
            return pd.DataFrame(data)

        return pd.DataFrame()


# Standalone functional convenience helpers
reshape_dataset = DataShaper.reshape_dataset
to_dataframe = DataShaper.to_dataframe
