import json
from typing import Any, Dict, List, Optional, Union
import pandas as pd
import requests


class ERPNextClient:
    """
    A client to interact with an ERPNext system.

    Attributes:
        base_url (str): The base URL of the ERPNext instance.
        session (requests.Session): A session object to handle requests.
    """

    def __init__(self, base_url: str):
        """
        Initializes the ERPNextClient with a base URL.

        Args:
            base_url (str): The base URL of the ERPNext instance.
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _validate_response(
        self, response: requests.Response, context: str = "API request"
    ) -> Dict[str, Any]:
        """
        Validates the HTTP response and checks for the presence of the 'data' or expected payload.

        Args:
            response (requests.Response): The response object from requests.
            context (str): Contextual description for error messages.

        Returns:
            Dict[str, Any]: The parsed JSON response.

        Raises:
            requests.HTTPError: If HTTP status is not ok.
            ValueError: If response is not valid JSON or lacks expected structure.
        """
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            raise requests.HTTPError(
                f"HTTP error during {context} [{response.status_code}]: {response.text}"
            ) from e

        try:
            data = response.json()
        except Exception as e:
            raise ValueError(
                f"Invalid JSON response during {context}: {response.text}"
            ) from e

        return data

    def login(self, username: str, password: str) -> None:
        """
        Logs into the ERPNext system using session authentication.

        Args:
            username (str): The username for login.
            password (str): The password for login.

        Raises:
            HTTPError: If the login request fails.
        """
        login_url = f"{self.base_url}/api/method/login"
        response = self.session.post(
            login_url, data={"usr": username, "pwd": password}
        )
        self._validate_response(response, context="Login")

    def _get_doctype_meta(self, dataset_id: str) -> Dict[str, Any]:
        """
        Retrieves the raw DocType metadata definition from ERPNext.

        Args:
            dataset_id (str): The DocType name.

        Returns:
            Dict[str, Any]: DocType metadata dictionary.
        """
        endpoint = f"{self.base_url}/api/resource/DocType/{dataset_id}"
        response = self.session.get(endpoint)
        data = self._validate_response(
            response, context=f"DocType meta for '{dataset_id}'"
        )
        if "data" not in data:
            raise ValueError(
                f"Expected 'data' key in DocType response for '{dataset_id}'"
            )
        return data["data"]

    def get_dataset_schema(self, dataset_id: str) -> Dict[str, str]:
        """
        Retrieves the field schema mapping (fieldname -> fieldtype) for a DocType.

        Args:
            dataset_id (str): The ID/name of the DocType to retrieve the schema for.

        Returns:
            Dict[str, str]: A dictionary mapping field names to field types.

        Raises:
            HTTPError: If the request for the dataset schema fails.
        """
        meta = self._get_doctype_meta(dataset_id)
        fields = meta.get("fields", [])
        return {
            field["fieldname"]: field["fieldtype"]
            for field in fields
            if "fieldname" in field and "fieldtype" in field
        }

    def get_detailed_schema(
        self, dataset_id: str, fetch_child_schemas: bool = False
    ) -> Dict[str, Any]:
        """
        Retrieves comprehensive schema metadata including child-table associations.

        Args:
            dataset_id (str): The ID/name of the DocType.
            fetch_child_schemas (bool): Whether to fetch schemas of child DocTypes.

        Returns:
            Dict[str, Any]: Detailed schema with fields, table_fields mapping, and child schemas.
        """
        meta = self._get_doctype_meta(dataset_id)
        fields = meta.get("fields", [])

        fields_dict = {}
        table_fields = {}

        for f in fields:
            fname = f.get("fieldname")
            if not fname:
                continue
            ftype = f.get("fieldtype", "")
            foptions = f.get("options")
            fields_dict[fname] = {
                "label": f.get("label"),
                "fieldtype": ftype,
                "options": foptions,
                "reqd": f.get("reqd", 0),
                "default": f.get("default"),
                "is_child_table": (ftype == "Table"),
            }
            if ftype == "Table" and foptions:
                table_fields[fname] = foptions

        child_schemas = {}
        if fetch_child_schemas:
            for fname, child_doctype in table_fields.items():
                try:
                    child_meta = self._get_doctype_meta(child_doctype)
                    child_fields = child_meta.get("fields", [])
                    child_schemas[child_doctype] = {
                        cf.get("fieldname"): cf.get("fieldtype")
                        for cf in child_fields
                        if cf.get("fieldname") and cf.get("fieldtype")
                    }
                except Exception:
                    child_schemas[child_doctype] = {}

        return {
            "doctype": dataset_id,
            "fields": fields_dict,
            "table_fields": table_fields,
            "child_schemas": child_schemas,
        }

    def _fetch_record_list(
        self,
        dataset_id: str,
        limit_start: int = 0,
        limit_page_length: int = 1000,
        fetch_all: bool = False,
        fields: Optional[List[str]] = None,
        filters: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Internal pagination helper to retrieve record lists from /api/resource/{doctype}.

        Args:
            dataset_id (str): The DocType name.
            limit_start (int): Starting record offset.
            limit_page_length (int): Number of records per page.
            fetch_all (bool): If True, loops through all pages until no records remain.
            fields (Optional[List[str]]): List of field names to retrieve.
            filters (Optional[Any]): ERPNext filters to apply.

        Returns:
            List[Dict[str, Any]]: List of record dictionaries.
        """
        endpoint = f"{self.base_url}/api/resource/{dataset_id}"
        all_records: List[Dict[str, Any]] = []
        current_start = limit_start

        while True:
            params: Dict[str, Any] = {
                "limit_start": current_start,
                "limit_page_length": limit_page_length,
            }
            if fields:
                params["fields"] = json.dumps(fields)
            if filters:
                params["filters"] = json.dumps(filters)

            response = self.session.get(endpoint, params=params)
            data = self._validate_response(
                response, context=f"Record list for '{dataset_id}'"
            )
            if "data" not in data or not isinstance(data["data"], list):
                raise ValueError(
                    f"Expected 'data' array in response for '{dataset_id}'"
                )

            page_records = data["data"]
            all_records.extend(page_records)

            if (
                not fetch_all
                or len(page_records) < limit_page_length
                or len(page_records) == 0
            ):
                break

            current_start += limit_page_length

        return all_records

    def get_document(
        self, dataset_id: str, document_name: str
    ) -> Dict[str, Any]:
        """
        Retrieves a single complete ERPNext document including all populated child-table data.

        Args:
            dataset_id (str): The DocType name.
            document_name (str): The unique name/ID of the document.

        Returns:
            Dict[str, Any]: The full document dictionary.

        Raises:
            HTTPError: If the request fails.
            ValueError: If the response is malformed.
        """
        endpoint = f"{self.base_url}/api/resource/{dataset_id}/{document_name}"
        response = self.session.get(endpoint)
        data = self._validate_response(
            response,
            context=f"Document '{document_name}' of DocType '{dataset_id}'",
        )
        if "data" not in data:
            raise ValueError(
                f"Expected 'data' key in response for document '{document_name}'"
            )
        return data["data"]

    def get_dataset(
        self,
        dataset_id: str,
        limit_start: int = 0,
        limit_page_length: int = 1000,
        fetch_all: bool = True,
        fields: Optional[List[str]] = None,
        filters: Optional[Any] = None,
    ) -> pd.DataFrame:
        """
        Retrieves a dataset from ERPNext as a Pandas DataFrame for backward compatibility.

        Args:
            dataset_id (str): The ID/name of the dataset/DocType.
            limit_start (int): Starting offset.
            limit_page_length (int): Page size for pagination.
            fetch_all (bool): Whether to retrieve all records across pages.
            fields (Optional[List[str]]): Specific fields to retrieve.
            filters (Optional[Any]): Filters to apply.

        Returns:
            pd.DataFrame: A DataFrame containing the retrieved dataset records.
        """
        records = self._fetch_record_list(
            dataset_id,
            limit_start=limit_start,
            limit_page_length=limit_page_length,
            fetch_all=fetch_all,
            fields=fields,
            filters=filters,
        )
        return pd.DataFrame(records)

    def sync_pull_dataset(
        self,
        dataset_id: str,
        last_index: int = 0,
        limit_page_length: int = 1000,
    ) -> pd.DataFrame:
        """
        Synchronizes and pulls a dataset from ERPNext starting from a specific index offset.

        Maintains backward compatibility with existing callers.

        Args:
            dataset_id (str): The ID of the dataset to retrieve.
            last_index (int): The starting index/offset to pull records from.
            limit_page_length (int): Maximum records to pull in this sync batch.

        Returns:
            pd.DataFrame: A DataFrame containing the pulled dataset records.
        """
        records = self._fetch_record_list(
            dataset_id,
            limit_start=last_index,
            limit_page_length=limit_page_length,
            fetch_all=False,
        )
        return pd.DataFrame(records)

    def get_dataset_object(
        self,
        dataset_id: str,
        limit_start: int = 0,
        limit_page_length: int = 100,
        fetch_all: bool = True,
        include_child_tables: bool = True,
        fields: Optional[List[str]] = None,
        filters: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves a structured dataset object containing schema, actual parent documents,
        and all populated child-table records.

        Args:
            dataset_id (str): The DocType name.
            limit_start (int): Starting record offset.
            limit_page_length (int): Number of records per page batch.
            fetch_all (bool): Whether to fetch all matching records.
            include_child_tables (bool): If True, retrieves individual documents to fetch full child-table rows.
            fields (Optional[List[str]]): Specific fields to fetch (for list requests).
            filters (Optional[Any]): Filters to apply.

        Returns:
            Dict[str, Any]: Structured dataset with schema, table fields, and full records.
        """
        detailed_schema = self.get_detailed_schema(
            dataset_id, fetch_child_schemas=False
        )
        table_fields = detailed_schema.get("table_fields", {})
        simple_schema = {
            fname: finfo["fieldtype"]
            for fname, finfo in detailed_schema.get("fields", {}).items()
        }

        # Retrieve record list
        record_list = self._fetch_record_list(
            dataset_id,
            limit_start=limit_start,
            limit_page_length=limit_page_length,
            fetch_all=fetch_all,
            fields=fields,
            filters=filters,
        )

        full_records: List[Dict[str, Any]] = []

        if include_child_tables:
            for rec in record_list:
                doc_name = rec.get("name")
                if not doc_name:
                    continue
                doc_data = self.get_document(dataset_id, doc_name)
                # Ensure all detected table fields exist as lists, defaulting to [] if empty
                for tf in table_fields:
                    if tf not in doc_data or doc_data[tf] is None:
                        doc_data[tf] = []
                full_records.append(doc_data)
        else:
            full_records = record_list

        return {
            "doctype": dataset_id,
            "schema": simple_schema,
            "table_fields": table_fields,
            "records": full_records,
            "total_records": len(full_records),
        }

    def sync_pull_dataset_object(
        self,
        dataset_id: str,
        last_index: int = 0,
        limit_page_length: int = 1000,
        fetch_all: bool = False,
        include_child_tables: bool = True,
        filters: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Synchronizes and pulls structured dataset records starting from an index offset.
        Follows the exact same data structure and normalization conventions as get_dataset_object().

        Args:
            dataset_id (str): The DocType name.
            last_index (int): Starting record offset.
            limit_page_length (int): Maximum records to pull in this sync batch.
            fetch_all (bool): Whether to retrieve all records starting from last_index.
            include_child_tables (bool): Whether to extract child-table data.
            filters (Optional[Any]): Filters to apply.

        Returns:
            Dict[str, Any]: Structured dataset object identical to get_dataset_object() format.
        """
        return self.get_dataset_object(
            dataset_id=dataset_id,
            limit_start=last_index,
            limit_page_length=limit_page_length,
            fetch_all=fetch_all,
            include_child_tables=include_child_tables,
            filters=filters,
        )

    def reshape_dataset(
        self, dataset_object: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Transforms a raw ERPNext dataset object into a clean, normalized, and predictable structure.

        Separates parent document attributes and child-table records without destroying information,
        allowing seamless downstream mapping to dashboards, JSON, DataFrames, or MongoDB.

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

    def to_dataframe(
        self, data: Any, table_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Converts extracted dataset objects or reshaped structures into a Pandas DataFrame.

        Args:
            data (Any): Dataset object, reshaped dataset dictionary, or list of dictionaries.
            table_name (Optional[str]): If specified, extracts that child table as a DataFrame.
                                        If None, extracts parent records as a DataFrame.

        Returns:
            pd.DataFrame: Converted DataFrame.
        """
        if isinstance(data, pd.DataFrame):
            return data

        if isinstance(data, dict):
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

