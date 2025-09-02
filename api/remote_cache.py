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
        self.known_files = set()
        self._known_files_inited = False
        self.s3 = boto3.client(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=KEY_ID,
            aws_secret_access_key=APP_KEY,
        )

    def known_files_init(self):
        """warm up the filename cache, but only once"""
        if self._known_files_inited:
            return
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix="tiles/"):
            for obj in page.get("Contents", []):
                self.known_files.add(obj["Key"])
        self._known_files_inited = True


    def file_exists(self, remote_name: str) -> bool:
        """file exists check"""
        self.known_files_init()
        return remote_name in self.known_files


    def upload_file(self, local_path: str, remote_name: str):
        """file upload"""
        self.known_files_init()
        self.s3.upload_file(local_path, BUCKET, remote_name)
        self.known_files.add(remote_name)


    def download_file(self, remote_name: str, local_path: str):
        """file download"""
        self.s3.download_file(BUCKET, remote_name, local_path)
