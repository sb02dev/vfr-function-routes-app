"""A remote cache interface for the tile renderer"""

import abc

class IRemoteCache(abc.ABC):
    """A remote cache interface for tile renderer"""

    @abc.abstractmethod
    def file_exists(self, remote_name: str) -> bool:
        """An abstract method defining the interface for a file exists check"""

    @abc.abstractmethod
    def upload_file(self, local_path: str, remote_name: str):
        """An abstract method defining the interface for a file upload"""

    @abc.abstractmethod
    def download_file(self, remote_name: str, local_path: str):
        """An abstract method defining the interface for a file download"""
