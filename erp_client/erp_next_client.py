import requests
import pandas as pd
from typing import Dict

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
    
    def login(self, username: str, password: str) -> None:
        """
        Logs into the ERPNext system.

        Args:
            username (str): The username for login.
            password (str): The password for login.

        Raises:
            HTTPError: If the login request fails.
        """
        login_url = f"{self.base_url}/api/method/login"
        response = self.session.post(login_url, data={'usr': username, 'pwd': password})
        response.raise_for_status()
    
    def get_dataset(self, dataset_id: str) -> pd.DataFrame:
        """
        Retrieves a dataset from the ERPNext system.

        Args:
            dataset_id (str): The ID of the dataset to retrieve.

        Returns:
            pd.DataFrame: A DataFrame containing the dataset records.

        Raises:
            HTTPError: If the request for the dataset fails.
        """
        endpoint = f"{self.base_url}/api/resource/{dataset_id}"
        response = self.session.get(endpoint)
        response.raise_for_status()
        data = response.json()
        records = data['data']
        return pd.DataFrame(records)
    
    def sync_pull_dataset(self, dataset_id: str, last_index: int) -> pd.DataFrame:
        """
        Synchronizes and pulls a dataset from the ERPNext system starting from a specific index.

        Args:
            dataset_id (str): The ID of the dataset to retrieve.
            last_index (int): The index to start pulling records from.

        Returns:
            pd.DataFrame: A DataFrame containing the pulled dataset records.

        Raises:
            HTTPError: If the request for the dataset fails.
        """
        endpoint = f"{self.base_url}/api/resource/{dataset_id}"
        response = self.session.get(endpoint, params={'limit_start': last_index, 'limit_page_length': 1000})
        response.raise_for_status()
        data = response.json()
        records = data['data']
        return pd.DataFrame(records)
    
    def get_dataset_schema(self, dataset_id: str) -> Dict:
        """
        Retrieves the schema of a dataset from the ERPNext system.

        Args:
            dataset_id (str): The ID of the dataset to retrieve the schema for.

        Returns:
            Dict: A dictionary mapping field names to field types.

        Raises:
            HTTPError: If the request for the dataset schema fails.
        """
        endpoint = f"{self.base_url}/api/resource/DocType/{dataset_id}"
        response = self.session.get(endpoint)
        response.raise_for_status()
        data = response.json()
        schema = {field['fieldname']: field['fieldtype'] for field in data['data']['fields']}
        return schema
