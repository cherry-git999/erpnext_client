import requests
from erp_client.erp_next_client import ERPNextClient


if __name__ == "__main__":
    """
    Main execution block for interacting with the ERPNext system.
    
    This script initializes the ERPNext client, logs into the system, 
    and performs various operations such as retrieving a dataset, 
    synchronizing and pulling a dataset, and retrieving the dataset schema.
    """
    client = ERPNextClient(base_url="https://erp.fpohub.com")
    username = "ads@aegiondynamic.com"
    password = "Csa@2025"
    client.login(username, password)
    
    dataset_id = 'Purchase Invoice'
    print(f"Trying to access dataset: {dataset_id}")
    
    try:
        dataset = client.get_dataset(dataset_id)
        print(f"Dataset {dataset_id}:", dataset.head())
    except requests.exceptions.HTTPError as e:
        print(f"Failed to access dataset {dataset_id}: {e}")
    
    try:
        sync_data = client.sync_pull_dataset(dataset_id, last_index=0)
        print(f"Sync Data for {dataset_id}:", sync_data.head())
    except requests.exceptions.HTTPError as e:
        print(f"Failed to sync pull dataset {dataset_id}: {e}")
    
    try:
        schema = client.get_dataset_schema(dataset_id)
        print(f"Schema for {dataset_id}:", schema)
    except requests.exceptions.HTTPError as e:
        print(f"Failed to get dataset schema for {dataset_id}: {e}")
