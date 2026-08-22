import json
from typing import Any, Dict, List, Optional
import pandas as pd
import requests
from .data_shaper import DataShaper


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
        Automatically handles HTTP to HTTPS redirects while preserving POST credentials.

        Args:
            username (str): The username for login.
            password (str): The password for login.

        Raises:
            HTTPError: If the login request fails.
        """
        login_url = f"{self.base_url}/api/method/login"
        response = self.session.post(
            login_url,
            data={"usr": username, "pwd": password},
            allow_redirects=False,
        )

        # Handle 301/302/303/307/308 redirects (e.g., http:// to https://)
        # Standard HTTP client behavior converts POST to GET and drops the body on 301/302.
        # By handling redirects explicitly, we update base_url and re-POST credentials to the target URL.
        if response.status_code in (301, 302, 303, 307, 308):
            redirect_url = response.headers.get("Location")
            if redirect_url:
                if redirect_url.endswith("/api/method/login"):
                    self.base_url = redirect_url[
                        : -len("/api/method/login")
                    ].rstrip("/")
                elif "/api/method/login" in redirect_url:
                    self.base_url = redirect_url.split("/api/method/login")[
                        0
                    ].rstrip("/")

                response = self.session.post(
                    redirect_url,
                    data={"usr": username, "pwd": password},
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

        Delegates to DataShaper.reshape_dataset().

        Args:
            dataset_object (Dict[str, Any]): Structured dataset from get_dataset_object() or sync_pull_dataset_object().

        Returns:
            Dict[str, Any]: Normalized dataset containing parent_records, child_tables, documents, and summary.
        """
        return DataShaper.reshape_dataset(dataset_object)

    def run_query_report(
        self,
        report_name: str,
        filters: Optional[Dict[str, Any]] = None,
        ignore_prepared_report: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes an ERPNext Query Report or Script Report and returns structured report data.

        Args:
            report_name (str): The name of the ERPNext Query Report (e.g. 'Stock Balance').
            filters (Optional[Dict[str, Any]]): Dictionary of report filters (e.g. company, from_date, to_date).
            ignore_prepared_report (bool): If True, executes and returns data directly without background queue.

        Returns:
            Dict[str, Any]: Structured dictionary with columns, records, total_records, and metadata.

        Raises:
            HTTPError: If the report execution fails.
            ValueError: If the response is malformed.
        """
        endpoint = f"{self.base_url}/api/method/frappe.desk.query_report.run"
        payload: Dict[str, Any] = {
            "report_name": report_name,
            "ignore_prepared_report": "True" if ignore_prepared_report else "False",
        }
        if filters:
            payload["filters"] = json.dumps(filters)

        response = self.session.post(endpoint, data=payload)
        data = self._validate_response(
            response, context=f"Query Report '{report_name}'"
        )
        msg = data.get("message", {})

        raw_columns = msg.get("columns", [])
        raw_results = msg.get("result", [])

        # Process columns metadata and fieldnames
        col_meta: List[Dict[str, Any]] = []
        col_fieldnames: List[str] = []
        for col in raw_columns:
            if isinstance(col, dict):
                fname = col.get("fieldname") or col.get("label") or str(col)
                col_fieldnames.append(fname)
                col_meta.append(col)
            else:
                col_fieldnames.append(str(col))
                col_meta.append({"fieldname": str(col), "label": str(col)})

        # Separate data rows from summary/total rows
        clean_records: List[Dict[str, Any]] = []
        total_row: Optional[Dict[str, Any]] = None

        for row in raw_results:
            if isinstance(row, dict):
                clean_records.append(row)
            elif isinstance(row, (list, tuple)):
                row_dict = {col: val for col, val in zip(col_fieldnames, row)}
                # Check if this is the summary Total row
                if row and str(row[0]).strip().lower() == "total":
                    total_row = row_dict
                else:
                    clean_records.append(row_dict)

        return {
            "report_name": report_name,
            "source_type": "query_report",
            "columns": col_meta,
            "column_fieldnames": col_fieldnames,
            "records": clean_records,
            "total_records": len(clean_records),
            "total_row": total_row,
            "chart": msg.get("chart"),
            "report_summary": msg.get("report_summary"),
        }

    def get_query_report(
        self,
        report_name: str,
        filters: Optional[Dict[str, Any]] = None,
        ignore_prepared_report: bool = True,
    ) -> pd.DataFrame:
        """
        Executes an ERPNext Query Report and returns the results as a Pandas DataFrame.

        Args:
            report_name (str): The name of the ERPNext Query Report.
            filters (Optional[Dict[str, Any]]): Dictionary of report filters.
            ignore_prepared_report (bool): If True, bypasses background prepared report queue.

        Returns:
            pd.DataFrame: A DataFrame containing the report rows.
        """
        report_obj = self.run_query_report(
            report_name=report_name,
            filters=filters,
            ignore_prepared_report=ignore_prepared_report,
        )
        return pd.DataFrame(report_obj["records"])

    def get_data(
        self,
        dataset_id: str,
        source_type: str = "doctype",
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Unified data retrieval method supporting both ERPNext DocTypes and Query Reports.

        Args:
            dataset_id (str): The DocType name or Query Report name.
            source_type (str): 'doctype' for DocType resources or 'query_report' for Query Reports.
            filters (Optional[Dict[str, Any]]): Filters to apply.
            **kwargs: Additional parameters passed to underlying retrieval methods.

        Returns:
            pd.DataFrame: Retrieved data as a Pandas DataFrame.

        Raises:
            ValueError: If source_type is unsupported.
        """
        stype = source_type.lower().strip()
        if stype == "doctype":
            return self.get_dataset(dataset_id=dataset_id, filters=filters, **kwargs)
        elif stype in ("query_report", "report"):
            return self.get_query_report(report_name=dataset_id, filters=filters, **kwargs)
        else:
            raise ValueError(
                f"Unsupported source_type '{source_type}'. Expected 'doctype' or 'query_report'."
            )

    def get_data_object(
        self,
        dataset_id: str,
        source_type: str = "doctype",
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Unified structured extraction method returning full dataset/report objects.

        Args:
            dataset_id (str): The DocType name or Query Report name.
            source_type (str): 'doctype' or 'query_report'.
            filters (Optional[Dict[str, Any]]): Filters to apply.
            **kwargs: Additional parameters passed to underlying methods.

        Returns:
            Dict[str, Any]: Structured dictionary representation.

        Raises:
            ValueError: If source_type is unsupported.
        """
        stype = source_type.lower().strip()
        if stype == "doctype":
            return self.get_dataset_object(
                dataset_id=dataset_id, filters=filters, **kwargs
            )
        elif stype in ("query_report", "report"):
            return self.run_query_report(
                report_name=dataset_id, filters=filters, **kwargs
            )
        else:
            raise ValueError(
                f"Unsupported source_type '{source_type}'. Expected 'doctype' or 'query_report'."
            )

    def to_dataframe(
        self, data: Any, table_name: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Converts extracted dataset objects, reshaped structures, or report objects into a Pandas DataFrame.

        Delegates to DataShaper.to_dataframe().

        Args:
            data (Any): Dataset object, reshaped dataset dictionary, Query Report dict, or list of dicts.
            table_name (Optional[str]): If specified, extracts that child table as a DataFrame.
                                        If None, extracts parent/main records as a DataFrame.

        Returns:
            pd.DataFrame: Converted DataFrame.
        """
        return DataShaper.to_dataframe(data, table_name=table_name)

