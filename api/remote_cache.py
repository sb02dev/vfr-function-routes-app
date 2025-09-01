"""A remote cache implementation for tile renderer"""

import os
import boto3

from VFRFunctionRoutes.remote_cache import IRemoteCache

KEY_ID = os.getenv("BLACKBLAZE_KEYID")
APP_KEY = os.getenv("BLACKBLAZE_APPKEY")
ENDPOINT = os.getenv("BLACKBLAZE_ENDPOINT")
BUCKET = os.getenv("BLACKBLAZE_BUCKET")


class S3Cache(IRemoteCache):
    """A remote cache implementation with boto3"""

    def __init__(self):
        self.s3 = boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=KEY_ID,
            aws_secret_access_key=APP_KEY,
        )


    def file_exists(self, remote_name: str) -> bool:
        """file exists check"""
        try:
            self.s3.head_object(Bucket=BUCKET, Key=remote_name)
            return True
        except self.s3.exceptions.ClientError:
            return False


    def upload_file(self, local_path: str, remote_name: str):
        """file upload"""
        self.s3.upload_file(local_path, BUCKET, remote_name)


    def download_file(self, remote_name: str, local_path: str):
        """file download"""
        self.s3.download_file(BUCKET, remote_name, local_path)
