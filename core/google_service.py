import os
import logging
from typing import Dict, Optional, Any, List

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
import io

class GoogleService:
    """
    Service class for handling Google API operations, primarily Google Drive interactions.
    Provides methods for file operations like listing, downloading, and renaming files.
    """
    
    def __init__(self):
        """Initialize the Google service without credentials."""
        self.drive_service = None
        self.credentials = None
        self.logger = logging.getLogger(__name__)
    
    def set_credentials(self, credentials: Credentials) -> None:
        """
        Set OAuth credentials and initialize the Drive service.
        
        Args:
            credentials: Google OAuth credentials object
        """
        self.credentials = credentials
        self.drive_service = build('drive', 'v3', credentials=credentials)
        self.logger.info("Google Drive service initialized with user credentials")
    
    def set_service_account(self, service_account_file: str) -> None:
        """
        Set service account credentials and initialize the Drive service.
        
        Args:
            service_account_file: Path to the service account JSON file
        """
        scopes = ['https://www.googleapis.com/auth/drive']
        self.credentials = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=scopes)
        self.drive_service = build('drive', 'v3', credentials=self.credentials)
        self.logger.info("Google Drive service initialized with service account")
    
    def list_files(self, folder_name: Optional[str] = None, page_token: Optional[str] = None) -> Dict[str, Any]:
        """
        List files from Google Drive, optionally filtered by folder.
        
        Args:
            folder_name: Optional name of folder to filter results
            page_token: Optional token for pagination
            
        Returns:
            Dict containing files and next page token
        """
        if not self.drive_service:
            raise ValueError("Drive service not initialized. Call set_credentials first.")

        query = "trashed = false and mimeType != 'application/vnd.google-apps.folder'"
        
        if folder_name:
            # First find the folder ID
            folder_query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            folder_results = self.drive_service.files().list(
                q=folder_query,
                fields="files(id, name)"
            ).execute()
            
            folders = folder_results.get('files', [])
            if folders:
                folder_id = folders[0]['id']
                query += f" and '{folder_id}' in parents"
        
        results = self.drive_service.files().list(
            q=query,
            pageSize=50,
            fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime)",
            pageToken=page_token
        ).execute()
        
        return results
    
    def download_file(self, file_id: str, output_path: str) -> str:
        """
        Download a file from Google Drive.
        
        Args:
            file_id: Google Drive file ID
            output_path: Local path to save the file
            
        Returns:
            Path to the downloaded file
        """
        if not self.drive_service:
            raise ValueError("Drive service not initialized. Call set_credentials first.")
        
        request = self.drive_service.files().get_media(fileId=file_id)
        
        with open(output_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                self.logger.debug(f"Download progress: {int(status.progress() * 100)}%")
        
        self.logger.info(f"Downloaded file to {output_path}")
        return output_path
    
    def rename_drive_file(self, file_id: str, new_name: str) -> bool:
        """
        Rename a file in Google Drive.
        
        Args:
            file_id: Google Drive file ID
            new_name: New name for the file
            
        Returns:
            Boolean indicating success
        """
        if not self.drive_service:
            raise ValueError("Drive service not initialized. Call set_credentials first.")
        
        try:
            self.drive_service.files().update(
                fileId=file_id,
                body={'name': new_name}
            ).execute()
            self.logger.info(f"Successfully renamed file {file_id} to '{new_name}'")
            return True
        except Exception as e:
            self.logger.error(f"Error renaming file: {str(e)}")
            return False
    
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Get metadata for a specific file.
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            Dictionary containing file metadata
        """
        if not self.drive_service:
            raise ValueError("Drive service not initialized. Call set_credentials first.")
        
        try:
            return self.drive_service.files().get(
                fileId=file_id, 
                fields="id,name,mimeType,createdTime,modifiedTime"
            ).execute()
        except Exception as e:
            self.logger.error(f"Error getting file metadata: {str(e)}")
            raise
