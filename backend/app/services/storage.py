import boto3
from botocore.config import Config
from app.config import settings

class StorageService:
    """
    MinIO / S3 Object Storage Client Service.
    Wraps upload, retrieval, and compensating deletion of encrypted documents.
    """
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            config=Config(
                signature_version="s3v4",
                connect_timeout=2
            )
        )
        self.bucket = settings.storage_bucket
        
        # Verify or create the target bucket in development
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except Exception:
                pass

    def put_object(self, object_key: str, data: bytes) -> str:
        """
        Uploads encrypted document bytes to S3.
        Returns the ETag hash confirming verified upload success.
        """
        response = self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data
        )
        etag = response.get("ETag")
        if not etag:
            raise RuntimeError("Object upload completed but S3 server failed to return ETag confirmation.")
        return etag.strip('"')

    def get_object(self, object_key: str) -> bytes:
        """
        Retrieves encrypted document bytes from storage.
        """
        response = self.client.get_object(
            Bucket=self.bucket,
            Key=object_key
        )
        return response["Body"].read()

    def delete_object(self, object_key: str):
        """
        Performs compensating deletion to remove orphaned objects.
        """
        try:
            self.client.delete_object(
                Bucket=self.bucket,
                Key=object_key
            )
        except Exception:
            # Non-blocking log, prevents blocking error handling
            pass
